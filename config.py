"""
WNACG 配置文件
管理认证、API域名和下载配置
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# API域名配置
API_DOMAIN = "www.wnacg01.cc"

# 登录配置现在完全通过环境变量 WNACG_USERNAME 和 WNACG_PASSWORD 管理


# Cookie现在自动管理，不需要手动配置
# 运行 python config.py 自动登录并生成cookie


# User-Agent配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

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

# Cookie文件路径
COOKIE_FILE = "cookie.json"

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

def save_cookie_to_file(cookie):
    """保存cookie到JSON文件"""
    data = {
        'cookie': cookie,
        'created_at': datetime.now().isoformat(),
        'domain': API_DOMAIN
    }
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Cookie已保存到 {COOKIE_FILE}")

def get_cookie():
    """获取Cookie，优先级：JSON文件 > 自动登录获取"""
    # 先尝试从文件加载
    cookie = load_cookie_from_file()
    if cookie:
        return cookie
    
    # 如果没有有效cookie，尝试自动登录获取
    print("没有有效的cookie，尝试自动登录...")
    try:
        cookie = login_and_get_cookie()
        save_cookie_to_file(cookie)
        return cookie
    except Exception as e:
        print(f"自动登录失败: {e}")
        raise ValueError('无法获取有效的Cookie，请检查登录配置')

def login_and_get_cookie():
    """自动登录获取cookie"""
    username, password = get_login_config()
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Referer': f'https://{API_DOMAIN}/'
    })
    
    # 首先获取登录页面
    login_url = f"https://{API_DOMAIN}/users-login.html"
    print(f"访问登录页面: {login_url}")
    
    try:
        response = session.get(login_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"无法访问登录页面: {e}")
    
    # 准备正确的登录数据
    login_data = {
        'login_name': username,
        'login_pass': password,
        'normal': '1',
        'submit': '登錄'
    }
    
    # 发送登录请求到正确的URL
    login_check_url = f"https://{API_DOMAIN}/users-check_login.html"
    print("正在登录...")
    
    try:
        login_response = session.post(login_check_url, data=login_data, timeout=10)
        login_response.raise_for_status()
        
        # 获取所有cookie
        cookie_dict = session.cookies.get_dict()
        cookie_string = '; '.join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        print(f"获取到cookie: {cookie_string[:100]}{'...' if len(cookie_string) > 100 else ''}")
        
        # 检查cookie是否有效
        if len(cookie_string) > 50:  # 确保cookie不为空
            print("登录成功，获取到cookie！")
            return cookie_string
        else:
            # 查看响应内容以确定登录状态
            if "登錄失敗" in login_response.text or "密碼錯誤" in login_response.text:
                raise Exception("用户名或密码错误")
            else:
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
