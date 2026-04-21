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
from playwright.sync_api import sync_playwright

# 加载.env文件中的环境变量
load_dotenv()

# User-Agent配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Cookie文件路径
COOKIE_FILE = "cookie.json"

# API域名配置（支持通过环境变量覆盖）
DEFAULT_API_DOMAIN = "wnacg.com"
FALLBACK_API_DOMAINS = [
    "wnacg.com",
    "www.wn03.cfd",
    "www.wnacg01.cc",
]


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
        raise ValueError('无法获取有效的Cookie，请检查登录配置')

def login_and_get_cookie():
    """自动登录获取cookie（优先使用Playwright完整浏览器流程）"""
    username, password = get_login_config()
    active_seed_domain = _resolve_active_domain(API_DOMAIN)

    print("正在通过Playwright浏览器登录...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            login_url = f"https://{active_seed_domain}/users-login.html"
            print(f"访问登录页面: {login_url}")
            page.goto(login_url, timeout=60000, wait_until='domcontentloaded')

            parsed = urlparse(page.url)
            active_domain = parsed.netloc or API_DOMAIN

            # 填写登录信息（兼容多种表单命名）
            username_selectors = [
                'input[name="login_name"]',
                'input[name="username"]',
                'input[type="text"]',
            ]
            password_selectors = [
                'input[name="login_pass"]',
                'input[name="password"]',
                'input[type="password"]',
            ]

            username_locator = None
            for selector in username_selectors:
                if page.locator(selector).count() > 0:
                    username_locator = page.locator(selector).first
                    break

            password_locator = None
            for selector in password_selectors:
                if page.locator(selector).count() > 0:
                    password_locator = page.locator(selector).first
                    break

            if not username_locator or not password_locator:
                raise Exception("未找到登录输入框，当前域名可能不是有效登录页")

            username_locator.fill(username, timeout=10000)
            password_locator.fill(password, timeout=10000)

            # 触发登录提交（兼容按钮和input提交）
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("登錄")',
                'button:has-text("登录")',
            ]
            submitted = False
            for selector in submit_selectors:
                if page.locator(selector).count() > 0:
                    page.locator(selector).first.click()
                    submitted = True
                    break

            if not submitted:
                page.keyboard.press('Enter')

            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                page.wait_for_timeout(3000)

            cookies = context.cookies()
            domain_key = active_domain.split(':')[0]

            filtered_pairs = []
            for cookie in cookies:
                cookie_domain = cookie.get('domain', '').lstrip('.')
                if cookie_domain.endswith(domain_key):
                    filtered_pairs.append(f"{cookie['name']}={cookie['value']}")

            if not filtered_pairs:
                filtered_pairs = [f"{cookie['name']}={cookie['value']}" for cookie in cookies]

            cookie_string = '; '.join(filtered_pairs)
            print(f"获取到cookie: {cookie_string[:100]}{'...' if len(cookie_string) > 100 else ''}")

            browser.close()

            if len(cookie_string) > 50:
                print("登录成功，获取到cookie！")
                return cookie_string, active_domain

            raise Exception("Playwright登录后未获取到有效cookie")

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
