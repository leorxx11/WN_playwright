"""
批量下载漫画脚本
从get_shelf_info.py生成的JSON文件中读取漫画信息，并逐个顺序下载
支持进度追踪、断点续传和详细日志记录
"""
import asyncio
import json
import os
import glob
import logging
import re
from typing import List, Dict
from datetime import datetime

from playwright.async_api import async_playwright
from comic_downloader import download_comic, login_with_cookies, DOWNLOAD_CONFIG
from config import DIRECTORIES, get_cookie, get_login_config


def setup_logging() -> logging.Logger:
    """设置日志系统"""
    # 创建logs目录
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 设置日志文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'batch_download_{timestamp}.log')
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
        ]
    )
    
    logger = logging.getLogger('batch_download')
    return logger, log_file


class BatchDownloadManager:
    def __init__(self, logger):
        self.successful_downloads = []
        self.failed_downloads = []
        self.total_comics = 0
        self.current_index = 0
        self.start_time = None
        self.logger = logger

    def print_progress(self, comic_title: str, comic_id: int):
        """简化的进度显示"""
        progress_percent = (self.current_index / self.total_comics * 100) if self.total_comics > 0 else 0
        elapsed = datetime.now() - self.start_time if self.start_time else 0
        
        # 终端只显示简要信息
        print(f"[{self.current_index}/{self.total_comics}] ({progress_percent:.1f}%) 下载: [{comic_id}] {comic_title[:50]}{'...' if len(comic_title) > 50 else ''}")
        
        # 详细信息记录到日志
        self.logger.info(f"Progress: {self.current_index}/{self.total_comics} ({progress_percent:.1f}%)")
        self.logger.info(f"Current download: [{comic_id}] {comic_title}")
        if elapsed:
            self.logger.info(f"Elapsed time: {elapsed}")

    def print_summary(self):
        """简化的下载总结"""
        total_elapsed = datetime.now() - self.start_time if self.start_time else 0
        
        # 终端只显示统计信息
        print(f"\n批量下载完成! 成功:{len(self.successful_downloads)} 失败:{len(self.failed_downloads)} 用时:{total_elapsed}")
        
        # 详细信息记录到日志
        self.logger.info(f"Batch download completed!")
        self.logger.info(f"Total comics: {self.total_comics}")
        self.logger.info(f"Successful downloads: {len(self.successful_downloads)}")
        self.logger.info(f"Failed downloads: {len(self.failed_downloads)}")
        self.logger.info(f"Total time: {total_elapsed}")
        
        if self.successful_downloads:
            self.logger.info(f"Successful downloads:")
            for comic in self.successful_downloads:
                self.logger.info(f"  - [{comic['id']}] {comic['title']}")
        
        if self.failed_downloads:
            self.logger.info(f"Failed downloads:")
            for comic in self.failed_downloads:
                self.logger.info(f"  - [{comic['id']}] {comic['title']}")


def find_shelf_json_files() -> List[str]:
    """查找search_results目录下的所有书架JSON文件"""
    search_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIRECTORIES['search_results'])
    pattern = os.path.join(search_dir, "shelf_*.json")
    json_files = glob.glob(pattern)
    return sorted(json_files, key=os.path.getmtime, reverse=True)  # 按修改时间排序，最新的在前


def load_comics_from_json(json_file_path: str, logger) -> List[Dict]:
    """从JSON文件中加载漫画信息"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        comics = data.get('comics', [])
        shelf_info = data.get('shelf_metadata', {})
        
        # 终端显示简要信息
        print(f"加载了 {len(comics)} 部漫画 from {os.path.basename(json_file_path)}")
        
        # 详细信息记录到日志
        logger.info(f"Loaded {len(comics)} comics from {json_file_path}")
        logger.info(f"Shelf name: {shelf_info.get('shelf_name', 'Unknown')}")
        logger.info(f"Export time: {shelf_info.get('export_time', 'Unknown')}")
        
        return comics
    except Exception as e:
        error_msg = f"Failed to read JSON file {json_file_path}: {e}"
        print(f"❌ {error_msg}")
        logger.error(error_msg)
        return []


def select_json_file(logger) -> str:
    """让用户选择要下载的JSON文件"""
    json_files = find_shelf_json_files()
    
    if not json_files:
        msg = "未找到任何书架JSON文件，请先运行 get_shelf_info.py"
        print(f"❌ {msg}")
        logger.error(msg)
        return None
    
    print("\n可用的书架JSON文件:")
    for i, json_file in enumerate(json_files):
        filename = os.path.basename(json_file)
        # 尝试从文件名解析书架名称和时间
        try:
            parts = filename.replace('.json', '').split('_')
            if len(parts) >= 3:
                shelf_name = '_'.join(parts[1:-2]) if len(parts) > 3 else parts[1]
                timestamp = '_'.join(parts[-2:])
                display_name = f"{shelf_name} ({timestamp})"
            else:
                display_name = filename
        except:
            display_name = filename
        
        print(f"  {i}: {display_name}")
    
    try:
        choice = input(f"\n请选择要下载的书架文件 (0-{len(json_files)-1}): ").strip()
        choice_index = int(choice)
        
        if 0 <= choice_index < len(json_files):
            selected_file = json_files[choice_index]
            logger.info(f"User selected file: {selected_file}")
            return selected_file
        else:
            msg = "Invalid selection"
            print(f"❌ {msg}")
            logger.warning(msg)
            return None
    except (ValueError, KeyboardInterrupt):
        msg = "Invalid input or cancelled"
        print(f"❌ {msg}")
        logger.warning(msg)
        return None


async def download_comics_from_json(json_file_path: str, logger, start_index: int = 0, max_downloads: int = None):
    """从JSON文件中批量下载漫画"""
    
    # 检查登录配置
    try:
        username, password = get_login_config()
    except ValueError as e:
        error_msg = f"登录配置错误: {e}"
        print(f"❌ {error_msg}")
        logger.error(error_msg)
        return
    
    # 加载漫画列表
    comics = load_comics_from_json(json_file_path, logger)
    if not comics:
        msg = "没有找到要下载的漫画"
        print(f"❌ {msg}")
        logger.error(msg)
        return
    
    # 应用起始索引和最大下载数限制
    if start_index > 0:
        comics = comics[start_index:]
        msg = f"从第 {start_index + 1} 部漫画开始下载"
        print(msg)
        logger.info(msg)
    
    if max_downloads and max_downloads > 0:
        comics = comics[:max_downloads]
        msg = f"限制最多下载 {max_downloads} 部漫画"
        print(msg)
        logger.info(msg)
    
    if not comics:
        msg = "应用过滤条件后没有漫画需要下载"
        print(f"❌ {msg}")
        logger.error(msg)
        return
    
    # 初始化下载管理器
    manager = BatchDownloadManager(logger)
    manager.total_comics = len(comics)
    manager.start_time = datetime.now()
    
    print(f"🚀 开始批量下载 {len(comics)} 部漫画")
    logger.info(f"Starting batch download of {len(comics)} comics")
    
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=False)  # 可视化下载过程
        context = await browser.new_context()
        page = await context.new_page()
        
        # 设置页面超时
        page.set_default_timeout(DOWNLOAD_CONFIG["page_timeout"])
        
        try:
            # 首次登录
            print("登录中...")
            logger.info("Attempting to login...")
            login_success = await login_with_cookies(page)
            if not login_success:
                error_msg = "登录失败，无法继续批量下载"
                print(f"❌ {error_msg}")
                logger.error(error_msg)
                return
            
            print("✅ 登录成功")
            logger.info("Login successful")
            
            # 逐个下载漫画
            for i, comic in enumerate(comics):
                manager.current_index = i + 1
                comic_id = comic.get('id')
                comic_title = comic.get('title', f'Comic_{comic_id}')
                
                # 打印进度
                manager.print_progress(comic_title, comic_id)
                
                try:
                    # 检查是否已经下载过（检查压缩包文件）
                    download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIRECTORIES['downloads'])
                    safe_title = comic_title.replace('/', '_').replace('\\', '_').replace(':', '_')
                    safe_title = re.sub(r'[<>:"/\\|?*]', '_', safe_title)
                    potential_zip = os.path.join(download_dir, f"{safe_title}.zip")
                    
                    if os.path.exists(potential_zip):
                        print(f"⚠️  跳过已存在")
                        logger.info(f"Skipping existing comic: [{comic_id}] {comic_title} at {potential_zip}")
                        manager.successful_downloads.append(comic)
                        continue
                    
                    # 下载漫画
                    logger.info(f"Starting download: [{comic_id}] {comic_title}")
                    success = await download_comic(page, comic_id)
                    
                    if success:
                        print(f"✅ 成功")
                        logger.info(f"Download successful: [{comic_id}] {comic_title}")
                        manager.successful_downloads.append(comic)
                    else:
                        print(f"❌ 失败")
                        logger.error(f"Download failed: [{comic_id}] {comic_title}")
                        manager.failed_downloads.append(comic)
                    
                    # 在每次下载后等待一段时间，避免过于频繁的请求
                    if i < len(comics) - 1:  # 不是最后一个
                        wait_time = 3  # 等待3秒
                        print(f"等待{wait_time}秒...")
                        logger.info(f"Waiting {wait_time} seconds before next download...")
                        await asyncio.sleep(wait_time)
                    
                except Exception as e:
                    print(f"❌ 异常")
                    logger.error(f"Exception during download [{comic_id}] {comic_title}: {e}")
                    manager.failed_downloads.append(comic)
                    continue
            
        finally:
            await browser.close()
            
            # 打印下载总结
            manager.print_summary()


async def main():
    """主函数"""
    print("=== WNACG 批量漫画下载脚本 ===")
    
    # 设置日志
    logger, log_file = setup_logging()
    print(f"详细日志将保存到: {log_file}")
    logger.info("Batch download script started")
    
    try:
        # 选择JSON文件
        json_file = select_json_file(logger)
        if not json_file:
            return
        
        print(f"选择的文件: {os.path.basename(json_file)}")
        
        # 可选：设置下载参数
        start_index_input = input("起始位置 (默认0): ").strip()
        start_index = int(start_index_input) if start_index_input.isdigit() else 0
        
        max_downloads_input = input("最大下载数 (留空表示全部): ").strip()
        max_downloads = int(max_downloads_input) if max_downloads_input.isdigit() else None
        
        confirm = input(f"确认开始批量下载? (y/N): ").strip().lower()
        if confirm != 'y':
            print("取消下载")
            logger.info("Download cancelled by user")
            return
        
        # 开始批量下载
        await download_comics_from_json(json_file, logger, start_index, max_downloads)
        
    except KeyboardInterrupt:
        msg = "批量下载被用户取消"
        print(f"\n{msg}")
        logger.warning(msg)
    except Exception as e:
        error_msg = f"批量下载过程中发生错误: {e}"
        print(error_msg)
        logger.error(error_msg)
        logger.error(f"Traceback: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())