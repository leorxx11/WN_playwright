"""
单个漫画下载功能 - Playwright实现
使用Playwright浏览器自动化技术下载WNACG漫画
"""
import asyncio
import os
import re
import logging

from playwright.async_api import async_playwright, Page, BrowserContext
from config import API_DOMAIN, DIRECTORIES, DOWNLOAD_CONFIG, get_cookie, get_login_config

def setup_comic_logger() -> logging.Logger:
    """设置漫画下载器的日志系统"""
    # 创建logs目录
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 设置日志文件名
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'comic_download_{timestamp}.log')
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
        ]
    )
    
    logger = logging.getLogger('comic_downloader')
    return logger, log_file

# 全局日志器 - 可以被外部传入
_global_logger = None

def set_logger(logger):
    """设置全局日志器"""
    global _global_logger
    _global_logger = logger

def get_logger():
    """获取日志器"""
    global _global_logger
    if _global_logger is None:
        _global_logger, _ = setup_comic_logger()
    return _global_logger

async def save_download_with_progress(download, save_path: str):
    """保存下载文件并显示进度"""
    import time
    logger = get_logger()
    
    logger.info("开始下载文件...")
    start_time = time.time()
    
    # 保存文件
    await download.save_as(save_path)
    
    # 显示下载结果
    if os.path.exists(save_path):
        file_size = os.path.getsize(save_path)
        elapsed_time = time.time() - start_time
        
        # 格式化文件大小
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.2f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.2f} KB"
        else:
            size_str = f"{file_size} B"
 
        if elapsed_time > 0:
            speed = file_size / elapsed_time
            if speed > 1024 * 1024:
                speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
            elif speed > 1024:
                speed_str = f"{speed / 1024:.2f} KB/s"
            else:
                speed_str = f"{speed:.0f} B/s"
        else:
            speed_str = "N/A"
        
        logger.info(f"下载完成: 文件大小={size_str}, 用时={elapsed_time:.2f}秒, 速度={speed_str}")
    else:
        logger.error("下载失败: 文件不存在")

async def load_cookies_from_config(context: BrowserContext) -> bool:
    """从config.py加载Cookie"""
    logger = get_logger()
    try:
        cookie_str = get_cookie()
        if not cookie_str:
            logger.warning("配置文件中没有Cookie")
            return False
        
        # 解析Cookie字符串为Cookie对象列表
        cookies = []
        for cookie_pair in cookie_str.split('; '):
            if '=' in cookie_pair:
                name, value = cookie_pair.split('=', 1)
                cookies.append({
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': f'.{API_DOMAIN}',
                    'path': '/'
                })
        
        if cookies:
            await context.add_cookies(cookies)
            logger.info("Cookie已从配置文件加载")
            return True
        else:
            logger.warning("Cookie格式无效")
            return False
            
    except Exception as e:
        logger.error(f"从配置文件加载Cookie失败: {e}")
        return False

async def check_login_status(page: Page) -> bool:
    """检查当前登录状态"""
    logger = get_logger()
    try:
        await page.goto(f"https://{API_DOMAIN}")
        await page.wait_for_load_state('networkidle', timeout=30000)
        
        # 检查是否登录成功 - 尝试多种成功标志
        success_indicators = [
            'text=退出',
            'text=注销', 
            'text=登出',
            'a[href*="logout"]',
            'a[href*="exit"]',
            'text=个人中心',
            'text=我的',
            'a[href*="users-edit"]'
        ]
        
        for indicator in success_indicators:
            try:
                count = await page.locator(indicator).count()
                if count > 0:
                    logger.info("登录状态检查：已登录")
                    return True
            except:
                continue
        
        logger.info("登录状态检查：未登录")
        return False
    except Exception as e:
        logger.error(f"检查登录状态失败: {e}")
        return False


async def login_to_site(page: Page) -> bool:
    """使用Playwright登录到WNACG"""
    logger = get_logger()
    try:
        logger.info("开始登录到WNACG")
        
        # 设置更大的超时和重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await page.goto(f"https://{API_DOMAIN}", timeout=60000)
                
                # 点击登录按钮
                await page.click('a[href*="users-login"]')
                await page.wait_for_load_state('networkidle', timeout=60000)
                break
            except Exception as e:
                logger.warning(f"访问登录页面尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt == max_retries - 1:
                    raise
                await page.wait_for_timeout(2000)  # 等待2秒后重试
        
        # 等待登录表单加载并尝试多种可能的选择器
        logger.info("等待登录表单加载...")
        await page.wait_for_timeout(3000)  # 等待3秒确保表单完全加载
        
        # 等待输入框出现
        try:
            await page.wait_for_selector('input[name="login_name"]', timeout=10000)
            logger.info("用户名输入框已加载")
        except:
            logger.warning("用户名输入框加载超时，继续尝试...")
            
        try:
            await page.wait_for_selector('input[name="login_pass"]', timeout=10000) 
            logger.info("密码输入框已加载")
        except:
            logger.warning("密码输入框加载超时，继续尝试...")
        
        # 尝试多种可能的用户名输入框选择器
        username_selectors = [
            'input[name="login_name"]',
            'input[name="username"]', 
            'input[name="user"]',
            'input[type="text"]',
            'input[placeholder*="用户"]',
            'input[placeholder*="账号"]',
            '#username',
            '#login_name'
        ]
        
        username_input = None
        for selector in username_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    username_input = page.locator(selector).first
                    logger.info(f"找到用户名输入框: {selector}")
                    break
            except:
                continue
        
        if not username_input:
            logger.error("无法找到用户名输入框")
            return False
        
        # 尝试多种可能的密码输入框选择器
        password_selectors = [
            'input[name="login_pass"]',
            'input[name="password"]',
            'input[name="pass"]',
            'input[type="password"]',
            'input[placeholder*="密码"]',
            '#password',
            '#login_pass'
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    password_input = page.locator(selector).first
                    logger.info(f"找到密码输入框: {selector}")
                    break
            except:
                continue
        
        if not password_input:
            logger.error("无法找到密码输入框")
            return False
        
        # 获取登录配置
        try:
            username, password = get_login_config()
        except ValueError as e:
            logger.error(f"获取登录配置失败: {e}")
            return False
        
        # 输入用户名和密码 - 添加重试机制
        logger.info("正在输入登录信息...")
        
        # 填写用户名 - 重试机制
        for attempt in range(3):
            try:
                logger.info(f"填写用户名: {username} (尝试 {attempt + 1}/3)")
                await username_input.click()  # 先点击聚焦
                await page.wait_for_timeout(500)
                await username_input.clear()
                await username_input.type(username, delay=100)  # 逐字符输入，更慢
                await page.wait_for_timeout(1000)
                
                # 验证是否填写成功
                current_value = await username_input.input_value()
                if current_value == username:
                    logger.info("用户名填写成功")
                    break
                else:
                    logger.warning(f"用户名填写验证失败，期望: '{username}', 实际: '{current_value}'")
            except Exception as e:
                logger.error(f"用户名填写失败 (尝试 {attempt + 1}): {e}")
                if attempt == 2:
                    logger.error("用户名填写最终失败")
                await page.wait_for_timeout(1000)
        
        # 填写密码 - 重试机制
        for attempt in range(3):
            try:
                logger.info(f"填写密码: {'*' * len(password)} (尝试 {attempt + 1}/3)")
                await password_input.click()  # 先点击聚焦
                await page.wait_for_timeout(500)
                await password_input.clear()
                await password_input.type(password, delay=100)  # 逐字符输入，更慢
                await page.wait_for_timeout(1000)
                
                # 验证是否填写成功
                current_value = await password_input.input_value()
                if len(current_value) == len(password):
                    logger.info("密码填写成功")
                    break
                else:
                    logger.warning(f"密码填写验证失败，期望长度: {len(password)}, 实际长度: {len(current_value)}")
            except Exception as e:
                logger.error(f"密码填写失败 (尝试 {attempt + 1}): {e}")
                if attempt == 2:
                    logger.error("密码填写最终失败")
                await page.wait_for_timeout(1000)
        
        logger.info("账号密码填写完成")
        
        # 尝试多种可能的提交按钮选择器
        submit_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'input[value*="登录"]',
            'button:has-text("登录")',
            'input[value*="login"]',
            '.login-btn',
            '#login-btn'
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    submit_button = page.locator(selector).first
                    logger.info(f"找到提交按钮: {selector}")
                    break
            except:
                continue
        
        if not submit_button:
            logger.error("无法找到提交按钮")
            return False
        
        # 点击登录
        logger.info("提交登录表单...")
        await submit_button.click()
        
        # 等待更长时间，因为登录可能需要时间
        logger.info("等待登录完成...")
        await page.wait_for_timeout(3000)  # 等待3秒
        await page.wait_for_load_state('networkidle', timeout=60000)  # 增加超时时间
        
        # 打印当前页面URL用于调试
        current_url = page.url
        logger.info(f"当前页面URL: {current_url}")
        
        # 检查是否登录成功 - 尝试多种成功标志
        success_indicators = [
            'text=退出',
            'text=注销', 
            'text=登出',
            'a[href*="logout"]',
            'a[href*="exit"]',
            'text=个人中心',
            'text=我的',
            'a[href*="users-edit"]'
        ]
        
        logger.info("检查登录状态...")
        for indicator in success_indicators:
            try:
                count = await page.locator(indicator).count()
                logger.info(f"检查 '{indicator}': 找到 {count} 个匹配")
                if count > 0:
                    logger.info("登录成功")
                    # Cookie已由config.py统一管理
                    return True
            except Exception as e:
                logger.warning(f"检查 '{indicator}' 时出错: {e}")
                continue
        
        # 如果没有找到明确的成功标志，检查是否有错误信息
        error_indicators = [
            'text=用户名或密码错误',
            'text=登录失败',
            'text=验证码',
            '.error',
            '.alert'
        ]
        
        for error_indicator in error_indicators:
            try:
                if await page.locator(error_indicator).count() > 0:
                    error_text = await page.locator(error_indicator).first.text_content()
                    logger.error(f"发现错误信息: {error_text}")
            except:
                continue
        
        logger.error("登录失败")
        return False
            
    except Exception as e:
        logger.error(f"登录过程中发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def login_with_cookies(page: Page) -> bool:
    """使用config.py中的Cookie登录，如果Cookie无效则重新登录"""
    logger = get_logger()
    try:
        # 首先尝试从配置文件加载Cookie
        cookie_loaded = await load_cookies_from_config(page.context)
        
        if cookie_loaded:
            # 检查Cookie是否有效
            if await check_login_status(page):
                return True
            else:
                logger.info("Cookie已失效，需要重新登录")
        
        # Cookie无效或不存在，进行正常登录
        return await login_to_site(page)
        
    except Exception as e:
        logger.error(f"使用Cookie登录失败: {e}")
        return await login_to_site(page)







async def handle_ssl_warning(page: Page) -> bool:
    """处理SSL证书警告页面"""
    logger = get_logger()
    try:
        # 检测是否是SSL证书警告页面
        ssl_warning_indicators = [
            'text=您的连接不是私密连接',
            'text=您的連接不是私密連接', 
            'text=Your connection is not private',
            'text=继续前往',
            'text=繼續前往',
            'text=Proceed to',
            'text=NET::ERR_CERT_DATE_INVALID',
            'text=继续前往v1.wzip.download',
            'button:has-text("高级")',
            'button:has-text("Advanced")',
            'a:has-text("继续前往")',
            'a:has-text("Proceed to")'
        ]
        
        # 检查是否在SSL警告页面
        is_ssl_warning = False
        for indicator in ssl_warning_indicators:
            try:
                if await page.locator(indicator).count() > 0:
                    is_ssl_warning = True
                    logger.info(f"检测到SSL证书警告页面: {indicator}")
                    break
            except:
                continue
        
        if not is_ssl_warning:
            return False
        
        logger.info("处理SSL证书警告...")
        
        # 方法1: 先点击"高级"按钮，再点击"继续前往" - 这是正确的顺序
        try:
            advanced_selectors = [
                'button:has-text("高级")',
                'button:has-text("Advanced")',
                '#details-button',
                'button[id*="details"]'
            ]
            
            advanced_clicked = False
            for selector in advanced_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        logger.info(f"找到高级按钮: {selector}")
                        await page.locator(selector).click()
                        logger.info("已点击高级按钮")
                        await page.wait_for_timeout(2000)  # 等待展开详细信息
                        advanced_clicked = True
                        break
                except Exception as e:
                    logger.warning(f"点击高级按钮失败 {selector}: {e}")
                    continue
            
            if not advanced_clicked:
                logger.warning("未找到或无法点击高级按钮")
            else:
                # 高级按钮点击成功后，查找并点击"继续前往"链接
                logger.info("查找继续前往链接...")
                proceed_selectors = [
                    'text=继续前往v1.wzip.download',
                    '#proceed-link', 
                    'a[id*="proceed"]',
                    'a:has-text("继续前往")',
                    'a:has-text("Proceed to")',
                    # 更具体的选择器
                    'a[href*="wzip.download"]',
                    'a[onclick*="proceed"]'
                ]
                
                proceed_clicked = False
                for proceed_selector in proceed_selectors:
                    try:
                        count = await page.locator(proceed_selector).count()
                        if count > 0:
                            logger.info(f"找到继续前往链接: {proceed_selector} (数量: {count})")
                            await page.locator(proceed_selector).first.click()
                            logger.info("已点击继续前往链接")
                            await page.wait_for_load_state('networkidle', timeout=15000)
                            logger.info("SSL警告已处理")
                            logger.info("成功通过SSL警告")
                            proceed_clicked = True
                            return True
                    except Exception as e:
                        logger.warning(f"点击继续前往链接失败 {proceed_selector}: {e}")
                        continue
                
                if not proceed_clicked:
                    logger.warning("高级按钮点击成功，但未找到继续前往链接")
        
        except Exception as e:
            logger.error(f"处理高级选项失败: {e}")
        
        # 方法2: 使用JavaScript绕过SSL警告 - 也要先点击高级按钮
        try:
            logger.info("尝试使用JavaScript绕过SSL警告...")
            # 先点击高级按钮
            js_advanced_code = """
            const advancedButtons = document.querySelectorAll('button, a');
            for (const btn of advancedButtons) {
                const text = btn.textContent || btn.innerText || '';
                if (text.includes('高级') || text.includes('Advanced') || btn.id === 'details-button') {
                    btn.click();
                    return true;
                }
            }
            return false;
            """
            advanced_result = await page.evaluate(js_advanced_code)
            if advanced_result:
                logger.info("JavaScript方式点击高级按钮成功")
                await page.wait_for_timeout(2000)  # 等待详细信息展开
                
                # 再点击继续前往链接
                js_proceed_code = """
                const continueLinks = document.querySelectorAll('a, button');
                for (const link of continueLinks) {
                    const text = link.textContent || link.innerText || '';
                    if (text.includes('继续前往') || text.includes('Proceed to') || 
                        link.id === 'proceed-link' || (link.href && link.href.includes('wzip.download'))) {
                        link.click();
                        return true;
                    }
                }
                return false;
                """
                proceed_result = await page.evaluate(js_proceed_code)
                if proceed_result:
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    logger.info("SSL警告已处理")
                    logger.info("JavaScript方式成功通过SSL警告")
                    return True
                else:
                    logger.warning("JavaScript方式点击继续前往链接失败")
            else:
                logger.warning("JavaScript方式点击高级按钮失败")
        except Exception as e:
            logger.error(f"JavaScript绕过SSL警告失败: {e}")
        
        logger.error("无法自动处理SSL证书警告")
        return False
        
    except Exception as e:
        logger.error(f"处理SSL证书警告时出错: {e}")
        return False

async def download_comic_with_retry(page: Page, comic_id: int, download_dir: str = None) -> bool:
    """带重试机制的下载整个漫画"""
    logger = get_logger()
    max_retries = DOWNLOAD_CONFIG["max_retries"]
    retry_delay = DOWNLOAD_CONFIG["retry_delay"]
    
    for attempt in range(max_retries):
        logger.info(f"下载中... (尝试 {attempt + 1}/{max_retries})")
        logger.info(f"=== 下载尝试 {attempt + 1}/{max_retries} ===")
        try:
            result = await download_comic_single_attempt(page, comic_id, download_dir)
            if result:
                logger.info("下载成功完成！")
                return True
            else:
                logger.error(f"第{attempt + 1}次尝试失败")
        except Exception as e:
            logger.error(f"第{attempt + 1}次尝试出现异常: {e}")
        
        # 如果不是最后一次尝试，等待后重试
        if attempt < max_retries - 1:
            logger.info(f"等待{retry_delay/1000}秒后重试...")
            await page.wait_for_timeout(retry_delay)
    
    logger.error(f"{max_retries}次尝试后仍然失败")
    return False

async def download_comic_single_attempt(page: Page, comic_id: int, download_dir: str = None) -> bool:
    """单次下载尝试 - 使用网站的下载按钮"""
    logger = get_logger()
    if download_dir is None:
        download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIRECTORIES['downloads'])
    
    try:
        # 导航到漫画详情页
        url = f"https://{API_DOMAIN}/photos-index-aid-{comic_id}.html"
        logger.info(f"正在访问漫画详情页: {url}")
        await page.goto(url)
        await page.wait_for_load_state('networkidle')
        
        # 获取漫画标题
        title_elem = page.locator('h2').first
        title = await title_elem.text_content() if await title_elem.count() > 0 else f"Comic_{comic_id}"
        title = title.strip()
        logger.info(f"漫画标题: {title}")
        
        # 确保下载目录存在
        os.makedirs(download_dir, exist_ok=True)
        
        # 生成安全的文件名
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        
        # 寻找下载按钮 - 简化选择器，减少误伤
        download_selectors = [
            'a:has-text("下载漫画")',
            'a:has-text("下載漫畫")', 
            'a:has-text("下载")',
            'a:has-text("下載")',
            'button:has-text("下載漫畫")',
            'button:has-text("下载漫画")',
            '.download-btn',
            'a[href*="download"]',
            # 备用选择器
            'text=下載漫畫',
            'text=下载漫画', 
            'text=下載',
            'text=下载'
        ]
        
        
        download_button = None
        for selector in download_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    download_button = page.locator(selector).first
                    logger.info(f"找到下载按钮: {selector}")
                    break
            except:
                continue
        
        if not download_button:
            logger.error("未找到下载按钮")
            return False
        
        # 点击下载按钮，跳转到下载页面 - 改进逻辑避免广告重定向
        logger.info("正在点击下载按钮...")
        
        # 获取下载按钮的href属性，如果是链接的话
        button_href = None
        try:
            button_href = await download_button.get_attribute('href')
            logger.info(f"下载按钮链接: {button_href}")
        except:
            pass
        
        # 使用更安全的点击方式
        try:
            # 检查是否是明显的广告链接，只有明确的广告链接才跳过
            is_obvious_ad = button_href and (
                'ad.' in button_href.lower() or 
                'ads.' in button_href.lower() or
                'advertisement' in button_href.lower() or
                'adnxs.com' in button_href.lower() or
                'googlesyndication.com' in button_href.lower() or
                'doubleclick.net' in button_href.lower()
            )
            
            if is_obvious_ad:
                logger.error("检测到明显的广告链接，跳过点击")
                return False
            
            # 如果有href属性且看起来像下载链接，直接导航
            if button_href and ('download' in button_href.lower() or 'photos' in button_href.lower()):
                if not button_href.startswith('http'):
                    button_href = f"https://{API_DOMAIN}{button_href}"
                logger.info(f"直接导航到下载页面: {button_href}")
                await page.goto(button_href)
            else:
                # 使用JavaScript点击避免被广告脚本劫持
                logger.info("使用JavaScript点击下载按钮...")
                await page.evaluate('(element) => element.click()', await download_button.element_handle())
        except Exception as click_error:
            logger.error(f"点击下载按钮失败: {click_error}")
            # 不要立即跳转到传统下载，先尝试常规点击
            try:
                logger.info("尝试常规点击...")
                await download_button.click()
            except Exception as regular_click_error:
                logger.error(f"常规点击也失败: {regular_click_error}")
                return False
        
        # 等待页面跳转到下载页面 - 增加超时和重试逻辑
        logger.info("等待跳转到下载页面...")
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
                await page.wait_for_timeout(3000)  # 额外等待3秒确保页面完全加载
                
                # 检查是否跳转到了下载页面
                current_url = page.url
                logger.info(f"当前页面URL: {current_url}")
                
                # 更精确的广告页面检测
                is_ad_page = (
                    'ad.' in current_url.lower() or
                    'ads.' in current_url.lower() or  
                    'advertisement' in current_url.lower() or
                    'adnxs.com' in current_url.lower() or
                    'googlesyndication.com' in current_url.lower() or
                    'doubleclick.net' in current_url.lower() or
                    # 检查页面内容是否包含明显的广告标识
                    (await page.locator('text=广告').count() > 0 and 
                     await page.locator('text=下载').count() == 0) or
                    (await page.locator('text=Advertisement').count() > 0 and 
                     await page.locator('text=download').count() == 0)
                )
                
                if is_ad_page:
                    logger.error("页面被重定向到广告页面，下载失败")
                    return False
                
                break
                
            except Exception as wait_error:
                logger.warning(f"等待页面加载失败 (尝试 {retry_count + 1}/{max_retries}): {wait_error}")
                retry_count += 1
                if retry_count < max_retries:
                    await page.wait_for_timeout(2000)  # 等待2秒后重试
                else:
                    logger.error("页面加载超时")
                    return False
        
        
        # 在下载页面寻找实际的下载链接 - 基于截图更新选择器，简化避免误伤
        download_link_selectors = [
            # 根据截图，优先查找"本地下载一"按钮
            'a:has-text("本地下载一")',
            'a:has-text("本地下載一")',
            'button:has-text("本地下载一")',
            'button:has-text("本地下載一")',
            # 也支持"本地下载二"作为备选
            'a:has-text("本地下载二")',
            'a:has-text("本地下載二")', 
            'button:has-text("本地下载二")',
            'button:has-text("本地下載二")',
            # 通用下载链接选择器
            'text=本地下載一',
            'text=本地下载一',
            'text=本地下載二', 
            'text=本地下载二',
            'text=下載一',
            'text=下载一',
            'a:has-text("下載一")',
            'a:has-text("下载一")',
            # 如果上面的找不到，尝试通用的下载链接
            'a[href*=".zip"]',
            'a[href*=".rar"]',
            'a[href*="download"]'
        ]
        
        download_link = None
        for selector in download_link_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    download_link = page.locator(selector).first
                    logger.info(f"找到下载链接: {selector}")
                    break
            except:
                continue
        
        if not download_link:
            logger.error("未找到下载链接")
            return False
        
        # 检查下载链接是否指向广告 - 使用更精确的检测
        download_href = None
        try:
            download_href = await download_link.get_attribute('href')
            logger.info(f"下载链接URL: {download_href}")
            
            # 只有明确的广告域名才被认为是广告
            is_ad_link = download_href and (
                'ad.' in download_href.lower() or
                'ads.' in download_href.lower() or
                'advertisement' in download_href.lower() or
                'adnxs.com' in download_href.lower() or
                'googlesyndication.com' in download_href.lower() or
                'doubleclick.net' in download_href.lower()
            )
            
            if is_ad_link:
                logger.error("下载链接指向明确的广告页面")
                return False
        except:
            pass
        
        # 设置下载监听并点击下载链接
        logger.info("设置下载监听并点击下载链接...")
        try:
            async with page.expect_download() as download_info:
                # 点击下载链接
                try:
                    await page.evaluate('(element) => element.click()', await download_link.element_handle())
                    logger.info("已点击下载链接")
                except Exception as js_click_error:
                    logger.warning(f"JavaScript点击失败，尝试常规点击: {js_click_error}")
                    await download_link.click()
                    logger.info("已点击下载链接")
                
                # 等待一下，检查是否出现SSL警告
                await page.wait_for_timeout(2000)
                
                # 检查是否出现SSL证书警告页面
                ssl_handled = await handle_ssl_warning(page)
                if ssl_handled:
                    logger.info("已处理SSL证书警告，下载应该会继续...")
                    # SSL警告处理后，下载应该会自动继续，不需要重新点击
            
            # 获取下载对象
            logger.info("等待下载开始...")
            download = await download_info.value
            
            # 获取建议的文件名
            suggested_filename = download.suggested_filename
            if not suggested_filename:
                suggested_filename = f"{safe_title}.zip"
            
            download_path = os.path.join(download_dir, suggested_filename)
            logger.info(f"正在下载文件: {suggested_filename}")
            
            # 保存下载的文件，并监听进度
            await save_download_with_progress(download, download_path)
            
            # 检查文件是否存在且有内容
            if os.path.exists(download_path) and os.path.getsize(download_path) > 0:
                file_size = os.path.getsize(download_path)
                logger.info(f"下载完成！文件大小: {file_size} bytes")
                logger.info(f"保存位置: {download_path}")
                logger.info(f"ZIP文件保留: {os.path.basename(download_path)}")
                
                return True
            else:
                logger.error("下载的文件为空或不存在")
                return False
                
        except Exception as download_error:
            logger.error(f"下载过程出错: {download_error}")
            return False
            
    except Exception as e:
        logger.error(f"下载漫画失败: {e}")
        return False

# 为了兼容性，保留原有函数名
async def download_comic(page: Page, comic_id: int, download_dir: str = None) -> bool:
    """下载整个漫画 - 带重试机制"""
    return await download_comic_with_retry(page, comic_id, download_dir)

async def main():
    """主函数 - 演示下载单个漫画"""
    # 设置日志系统
    logger, log_file = setup_comic_logger()
    print(f"详细日志将保存到: {log_file}")
    
    try:
        # 检查登录配置
        try:
            get_login_config()
        except ValueError as e:
            error_msg = f"错误: {e}"
            print(error_msg)
            logger.error(error_msg)
            return
        
        # 获取要下载的漫画ID
        comic_id = input("请输入要下载的漫画ID: ").strip()
        if not comic_id.isdigit():
            error_msg = "无效的漫画ID"
            print(error_msg)
            logger.error(error_msg)
            return
        
        comic_id = int(comic_id)
        logger.info(f"用户输入漫画ID: {comic_id}")
        
        print(f"🚀 开始下载漫画 [{comic_id}]...")
        
        async with async_playwright() as p:
            # 启动浏览器
            print("启动浏览器...")
            profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.playwright_profile')
            context = await p.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
            )
            page = await context.new_page()
            # 设置页面超时
            page.set_default_timeout(DOWNLOAD_CONFIG["page_timeout"])
            
            try:
                # 使用Cookie登录
                print("正在登录...")
                login_success = await login_with_cookies(page)
                if not login_success:
                    error_msg = "❌ 登录失败，无法继续"
                    print(error_msg)
                    logger.error(error_msg)
                    return
                
                print("✅ 登录成功")
                
                # 下载漫画
                print(f"📥 正在下载漫画 [{comic_id}]...")
                logger.info(f"开始下载漫画 ID: {comic_id}")
                success = await download_comic(page, comic_id)
                
                if success:
                    print("✅ 下载完成!")
                    logger.info("下载完成!")
                else:
                    print("❌ 下载失败")
                    logger.error("下载失败")
                    
            finally:
                await context.close()
                
    except KeyboardInterrupt:
        msg = "下载被用户取消"
        print(f"\n{msg}")
        logger.warning(msg)
    except Exception as e:
        error_msg = f"下载过程中发生错误: {e}"
        print(error_msg)
        logger.error(error_msg)

if __name__ == "__main__":
    print("=== WNACG 单个漫画下载工具 ===")
    asyncio.run(main())
