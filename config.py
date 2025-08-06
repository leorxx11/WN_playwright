"""
WNACG 配置文件
管理认证、API域名和下载配置
"""
import os

# API域名配置
API_DOMAIN = "www.wnacg01.cc"

# 登录配置
LOGIN_CONFIG = {
    "username": "2233198920",
    "password": "zhaoliyu22",
}

# Cookie配置 - 可以手动填入，也可以留空让程序自动获取
WNACG_COOKIE = "_ym_uid=175438600627215927; _ym_d=1754386006; _ym_isad=1; MPIC_bnS5=04d09JS1iO%2FfpcYN4IDCoi9q1n21%2Fedo3vc5PtwPbUdYCoQnXS6PCjl6EHJYbL6jcLGRAN%2Bc2ZI2ZSz8bhq4e1sOFfg; _ym_visorc=b"

# User-Agent配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# 下载配置
DOWNLOAD_CONFIG = {
    "page_timeout": 120000,  # 页面加载超时(毫秒)
    "download_timeout": 600000,  # 下载超时(毫秒)
    "max_retries": 3,  # 最大重试次数
    "retry_delay": 5,  # 重试间隔(秒)
}

# 目录配置
DIRECTORIES = {
    "search_results": "search_results",  # 书架信息存储目录
    "downloads": "url",  # 漫画下载目录
}

def get_cookie():
    """获取Cookie，优先级：配置文件 > 环境变量"""
    if WNACG_COOKIE:
        return WNACG_COOKIE
    
    env_cookie = os.environ.get('WNACG_COOKIE')
    if env_cookie:
        return env_cookie
    
    raise ValueError('请在config.py中设置WNACG_COOKIE或设置环境变量WNACG_COOKIE')

def get_login_config():
    """获取登录配置"""
    username = os.environ.get('WNACG_USERNAME') or LOGIN_CONFIG.get('username')
    password = os.environ.get('WNACG_PASSWORD') or LOGIN_CONFIG.get('password')
    
    if not username or not password:
        raise ValueError('请在config.py中设置LOGIN_CONFIG或设置环境变量WNACG_USERNAME和WNACG_PASSWORD')
    
    return username, password

def get_headers(referer=None):
    """获取标准请求头"""
    headers = {
        "User-Agent": USER_AGENT,
        "referer": referer or f"https://{API_DOMAIN}/",
    }
    return headers

def get_request_headers_with_cookie():
    """获取包含Cookie的请求头"""
    headers = get_headers()
    headers["cookie"] = get_cookie()
    return headers

if __name__ == "__main__":
    print("=== WNACG 配置检查 ===")
    print(f"API域名: {API_DOMAIN}")
    
    try:
        cookie = get_cookie()
        print(f"Cookie: {'已配置' if cookie else '未配置'}")
    except ValueError as e:
        print(f"Cookie: {e}")
    
    try:
        username, password = get_login_config()
        print(f"登录配置: 用户名={username}, 密码={'*' * len(password)}")
    except ValueError as e:
        print(f"登录配置: {e}")
    
    print(f"下载目录: {DIRECTORIES['downloads']}")
    print(f"搜索结果目录: {DIRECTORIES['search_results']}")