"""
WNACG 配置文件
管理认证、API域名和下载配置
"""
import os
import json
import requests
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright

# 加载.env文件中的环境变量
load_dotenv()

# User-Agent配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Cookie文件路径
COOKIE_FILE = "cookie.json"

# Playwright持久化浏览器目录（与下载脚本共用，保留登录和Cloudflare验证状态）
PLAYWRIGHT_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.playwright_profile')

# 登录页等待时间(毫秒)：留出手动通过Cloudflare验证的时间
LOGIN_FORM_WAIT_MS = 120000
# 提交登录后等待跳转的时间(毫秒)
LOGIN_RESULT_WAIT_MS = 15000

# 未登录时收藏页的提示文字
NOT_LOGGED_IN_MARKER = "您沒有權限，需要登錄"

# API域名配置（支持通过环境变量覆盖）
DEFAULT_API_DOMAIN = "wnacg.com"
FALLBACK_API_DOMAINS = [
    "wnacg.com",
    "www.wn10.cfd",
    "www.wn03.cfd",
    "www.wnacg01.cc",
]


class BrowserSetupError(Exception):
    """Playwright浏览器无法启动（未安装或profile被占用），不应回退到requests登录"""


class LoginCredentialError(Exception):
    """用户名或密码错误"""


def _load_domain_from_cookie_file():
    """从cookie文件读取最近一次成功登录的域名"""
    if not os.path.exists(COOKIE_FILE):
        return None

    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            domain = data.get('domain')
            return domain if domain else None
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_active_domain(seed_domain):
    """
    解析当前可用域名。
    站点会频繁 301 到新域名，不能固定写死。
    """
    def _is_login_page_valid(html_text):
        markers = [
            'name="login_name"',
            "name='login_name'",
            'users-check_login.html',
            '用戶登錄',
            '用户登录',
        ]
        return any(marker in html_text for marker in markers)

    candidates = [seed_domain] + [d for d in FALLBACK_API_DOMAINS if d != seed_domain]

    for candidate in candidates:
        try:
            resp = requests.get(
                f"https://{candidate}/users-login.html",
                headers={'User-Agent': USER_AGENT},
                timeout=8,
                allow_redirects=True
            )
            parsed = urlparse(resp.url)
            final_domain = parsed.netloc or candidate

            if _is_login_page_valid(resp.text):
                return final_domain
        except requests.RequestException:
            continue

    return seed_domain


# 优先级：环境变量 > cookie文件缓存域名 > 默认域名，然后解析实际重定向域名
_env_domain = os.environ.get('WNACG_API_DOMAIN')
_seed_domain = _env_domain or _load_domain_from_cookie_file() or DEFAULT_API_DOMAIN
API_DOMAIN = _env_domain or _resolve_active_domain(_seed_domain)

# 登录配置现在完全通过环境变量 WNACG_USERNAME 和 WNACG_PASSWORD 管理


# Cookie现在自动管理，不需要手动配置
# 运行 python config.py 自动登录并生成cookie

# 下载配置
DOWNLOAD_CONFIG = {
    "page_timeout": 120000,  # 页面加载超时(毫秒)
    "download_timeout": 600000,  # 下载超时(毫秒)
    "max_retries": 3,  # 最大重试次数
    "retry_delay": 5,  # 重试间隔(秒)
}

# 搜索配置
REQUEST_CONFIG = {
    "timeout": 30,  # 请求超时时间(秒)
    "max_retries": 3,  # 最大重试次数
    "max_pages": 20,  # 默认搜索最大页数
}

# 搜索匹配配置
SEARCH_CONFIG = {
    "min_similarity": 0.3,  # 最小匹配相似度
}

# 目录配置
DIRECTORIES = {
    "search_results": "search_results",  # 书架信息存储目录
    "downloads": "downloads",  # 漫画下载目录
}

def load_cookie_from_file():
    """从JSON文件加载cookie"""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 检查cookie是否过期（24小时有效期）
                created_time = datetime.fromisoformat(data['created_at'])
                if (datetime.now() - created_time).total_seconds() < 24 * 3600:
                    return data['cookie']
                else:
                    print("Cookie已过期，需要重新获取")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Cookie文件格式错误: {e}")
    return None

def save_cookie_to_file(cookie, domain=None):
    """保存cookie到JSON文件"""
    data = {
        'cookie': cookie,
        'created_at': datetime.now().isoformat(),
        'domain': domain or API_DOMAIN
    }
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Cookie已保存到 {COOKIE_FILE}")

def get_cookie():
    """获取Cookie，优先级：JSON文件 > 自动登录获取"""
    global API_DOMAIN

    # 先尝试从文件加载
    cookie = load_cookie_from_file()
    if cookie:
        return cookie
    
    # 如果没有有效cookie，尝试自动登录获取
    print("没有有效的cookie，尝试自动登录...")
    try:
        cookie, domain = login_and_get_cookie()
        API_DOMAIN = domain
        save_cookie_to_file(cookie, domain)
        return cookie
    except Exception as e:
        print(f"自动登录失败: {e}")
        raise ValueError(f'无法获取有效的Cookie: {e}') from e

def _launch_login_context(playwright) -> BrowserContext:
    """启动与下载脚本共用的持久化浏览器，启动失败时给出明确原因"""
    try:
        return playwright.chromium.launch_persistent_context(
            PLAYWRIGHT_PROFILE_DIR,
            headless=False,
        )
    except Exception as e:
        message = str(e)
        if "Executable doesn't exist" in message:
            raise BrowserSetupError(
                "未安装Playwright Chromium，请运行: playwright install chromium"
            ) from e
        if "ProcessSingleton" in message or "already in use" in message:
            raise BrowserSetupError(
                f"浏览器profile正被占用，请先关闭正在运行的下载脚本: {PLAYWRIGHT_PROFILE_DIR}"
            ) from e
        raise BrowserSetupError(f"Playwright浏览器启动失败: {e}") from e


def _is_logged_in(page: Page, domain: str) -> bool:
    """访问收藏页判断当前浏览器是否已登录"""
    page.goto(
        f"https://{domain}/users-users_fav-page-1-c-0.html",
        timeout=60000,
        wait_until='domcontentloaded',
    )
    if 'users-login' in page.url:
        return False
    if page.locator('input[name="login_name"], input[type="password"]').count() > 0:
        return False
    content = page.content()
    # Cloudflare验证页也不包含未登录提示，需要排除
    if 'challenge-platform' in content or 'cf-chl' in content:
        return False
    return NOT_LOGGED_IN_MARKER not in content


def _wait_for_login_form(page: Page) -> tuple[Locator, Locator]:
    """等待登录表单出现；遇到Cloudflare验证时提示在浏览器中手动完成"""
    username_selector = 'input[name="login_name"], input[name="username"]'
    password_selector = 'input[name="login_pass"], input[name="password"], input[type="password"]'

    if page.locator(username_selector).count() == 0:
        print(f"未检测到登录表单，如出现Cloudflare验证请在打开的浏览器中手动完成"
              f"（最多等待{LOGIN_FORM_WAIT_MS // 1000}秒）...")
    try:
        page.wait_for_selector(username_selector, timeout=LOGIN_FORM_WAIT_MS)
    except Exception as e:
        raise Exception("未找到登录输入框，当前域名可能不是有效登录页") from e

    return page.locator(username_selector).first, page.locator(password_selector).first


def _submit_login_form(page: Page, username: str, password: str) -> None:
    """填写并提交登录表单，等待页面离开登录页"""
    username_locator, password_locator = _wait_for_login_form(page)
    username_locator.fill(username, timeout=10000)
    password_locator.fill(password, timeout=10000)

    # 触发登录提交（兼容按钮和input提交）
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("登錄")',
        'button:has-text("登录")',
    ]
    for selector in submit_selectors:
        if page.locator(selector).count() > 0:
            page.locator(selector).first.click()
            break
    else:
        password_locator.press('Enter')

    try:
        page.wait_for_url(
            lambda url: 'users-login' not in url and 'check_login' not in url,
            timeout=LOGIN_RESULT_WAIT_MS,
        )
    except Exception:
        # 部分页面用ajax登录不跳转，交给后续的登录状态检查判断
        pass

    content = page.content()
    if any(marker in content for marker in ("登錄失敗", "密碼錯誤", "用戶名或密碼")):
        raise LoginCredentialError("用户名或密码错误")


def _collect_cookie_string(context: BrowserContext, domain: str) -> str:
    """从浏览器上下文中提取当前站点的cookie字符串"""
    domain_key = domain.split(':')[0]
    cookies = context.cookies()

    filtered_pairs = [
        f"{cookie['name']}={cookie['value']}"
        for cookie in cookies
        if domain_key.endswith(cookie.get('domain', '').lstrip('.'))
    ]
    if not filtered_pairs:
        filtered_pairs = [f"{cookie['name']}={cookie['value']}" for cookie in cookies]

    return '; '.join(filtered_pairs)


def login_and_get_cookie() -> tuple[str, str]:
    """自动登录获取cookie（优先使用Playwright持久化浏览器流程）"""
    username, password = get_login_config()
    active_seed_domain = _resolve_active_domain(API_DOMAIN)

    print("正在通过Playwright浏览器登录...")
    try:
        with sync_playwright() as p:
            context = _launch_login_context(p)
            try:
                page = context.pages[0] if context.pages else context.new_page()

                login_url = f"https://{active_seed_domain}/users-login.html"
                print(f"访问登录页面: {login_url}")
                page.goto(login_url, timeout=60000, wait_until='domcontentloaded')
                active_domain = urlparse(page.url).netloc or active_seed_domain

                if _is_logged_in(page, active_domain):
                    print("浏览器profile中已是登录状态，直接读取cookie")
                else:
                    page.goto(login_url, timeout=60000, wait_until='domcontentloaded')
                    print("正在登录...")
                    _submit_login_form(page, username, password)
                    if not _is_logged_in(page, active_domain):
                        raise Exception("提交登录后仍未登录")

                cookie_string = _collect_cookie_string(context, active_domain)
                print(f"获取到cookie: {cookie_string[:100]}{'...' if len(cookie_string) > 100 else ''}")
                print("登录成功，获取到cookie！")
                return cookie_string, active_domain
            finally:
                context.close()

    except (BrowserSetupError, LoginCredentialError):
        raise
    except Exception as playwright_error:
        print(f"Playwright登录失败，回退requests方式: {playwright_error}")
        return _login_and_get_cookie_via_requests(username, password)


def _login_and_get_cookie_via_requests(username, password):
    """备用方案：通过requests登录获取cookie"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Referer': f'https://{API_DOMAIN}/'
    })

    login_url = f"https://{API_DOMAIN}/users-login.html"
    print(f"访问登录页面: {login_url}")

    try:
        response = session.get(login_url, timeout=10, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"无法访问登录页面: {e}")

    parsed = urlparse(response.url)
    active_domain = parsed.netloc or API_DOMAIN
    session.headers.update({'Referer': f'https://{active_domain}/users-login.html'})

    login_data = {
        'login_name': username,
        'login_pass': password,
        'normal': '1',
        'submit': '登錄'
    }

    login_check_url = f"https://{active_domain}/users-check_login.html"
    print("正在登录...")

    try:
        login_response = session.post(login_check_url, data=login_data, timeout=10)
        login_response.raise_for_status()

        cookie_dict = session.cookies.get_dict()
        cookie_string = '; '.join([f"{k}={v}" for k, v in cookie_dict.items()])

        print(f"获取到cookie: {cookie_string[:100]}{'...' if len(cookie_string) > 100 else ''}")

        if len(cookie_string) > 50:
            print("登录成功，获取到cookie！")
            return cookie_string, active_domain

        if (
            "登錄失敗" in login_response.text
            or "密碼錯誤" in login_response.text
            or "請輸入用戶名" in login_response.text
            or "请输入用户名" in login_response.text
        ):
            raise Exception("用户名或密码错误")

        raise Exception(f"登录后未获取到有效的cookie，响应长度: {len(login_response.text)}")

    except requests.RequestException as e:
        raise Exception(f"登录请求失败: {e}")



def get_login_config():
    """获取登录配置"""
    username = os.environ.get('WNACG_USERNAME')
    password = os.environ.get('WNACG_PASSWORD')
    
    if not username or not password:
        raise ValueError('请设置环境变量WNACG_USERNAME和WNACG_PASSWORD')
    
    return username, password

def get_headers(referer=None):
    """获取标准请求头"""
    headers = {
        "User-Agent": USER_AGENT,
        "referer": referer or f"https://{API_DOMAIN}/",
    }
    return headers

def get_request_headers_with_cookie(cookie=None):
    """获取包含Cookie的请求头"""
    headers = get_headers()
    headers["cookie"] = cookie or get_cookie()
    return headers

if __name__ == "__main__":
    print("=== WNACG Cookie 生成器 ===")
    print(f"API域名: {API_DOMAIN}")
    
    try:
        username, password = get_login_config()
        print(f"登录配置: 用户名={username}, 密码={'*' * len(password)}")
        
        print("\n正在获取Cookie...")
        cookie = get_cookie()
        print(f"Cookie获取成功，长度: {len(cookie)}")
        print(f"Cookie文件: {COOKIE_FILE}")
        
        # 验证cookie是否有效
        print("\n验证Cookie有效性...")
        headers = get_request_headers_with_cookie()
        test_url = f"https://{API_DOMAIN}/users-users_fav-page-1-c-0.html"
        
        response = requests.get(test_url, headers=headers, timeout=10)
        if "您沒有權限，需要登錄" in response.text:
            print("❌ Cookie验证失败，需要重新登录")
        else:
            print("✅ Cookie验证成功")
            
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
    except Exception as e:
        print(f"❌ 操作失败: {e}")
    
    print(f"\n其他配置:")
    print(f"下载目录: {DIRECTORIES['downloads']}")
    print(f"搜索结果目录: {DIRECTORIES['search_results']}")
