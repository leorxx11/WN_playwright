import asyncio
from dataclasses import dataclass, asdict
from typing import List
import json
import re
from datetime import datetime
import os

import aiohttp
from bs4 import BeautifulSoup

# 从配置文件导入
from config import API_DOMAIN, get_cookie, get_request_headers_with_cookie, DIRECTORIES

@dataclass
class Shelf:
    id: int
    name: str

@dataclass
class ComicInFavorite:
    id: int
    title: str
    cover: str
    favorite_time: str
    shelf: Shelf

@dataclass
class GetFavoriteResult:
    comics: List[ComicInFavorite]
    current_page: int
    total_page: int
    shelf: Shelf

async def get_favorite(session: aiohttp.ClientSession, cookie: str, shelf_id: int, page_num: int) -> GetFavoriteResult:
    url = f"https://{API_DOMAIN}/users-users_fav-page-{page_num}-c-{shelf_id}.html"
    headers = get_request_headers_with_cookie(cookie)
    async with session.get(url, headers=headers) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"Unexpected status {resp.status}: {text}")
    return parse_get_favorite(text)

def parse_get_favorite(html: str) -> GetFavoriteResult:
    soup = BeautifulSoup(html, "html.parser")
    comics = [parse_comic(div) for div in soup.select('.asTB')]

    page_span = soup.select_one('.thispage')
    current_page = int(page_span.get_text()) if page_span else 1

    page_links = soup.select('.f_left.paginator > a')
    total_page = int(page_links[-1].get_text()) if page_links else 1

    shelf = parse_shelf(soup.select_one('.cur'))

    return GetFavoriteResult(comics, current_page, total_page, shelf)

def parse_comic(div):
    a = div.select_one('.l_title > a')
    href = a['href']
    id = int(href.split('aid-')[1].split('.html')[0])
    title = a.get_text(strip=True)
    img = div.select_one('.asTBcell.thumb img')['src']
    cover = f"https:{img}"
    fav_span = div.select_one('.l_catg > span')
    favorite_time = fav_span.get_text(strip=True).replace('創建時間：', '') if fav_span else ''
    shelf = parse_shelf(div.select_one('.l_catg > a'))
    return ComicInFavorite(id, title, cover, favorite_time, shelf)

def parse_shelf(a):
    if not a:
        return Shelf(0, '')
    href = a.get('href', '')
    if not href:
        return Shelf(0, a.get_text(strip=True))
    
    # 处理不同的 href 格式
    if 'c-' in href:
        try:
            id = int(href.split('c-')[1].split('.html')[0])
        except (IndexError, ValueError):
            id = 0
    else:
        # 如果没有 c- 模式，默认为 0
        id = 0
    
    name = a.get_text(strip=True)
    return Shelf(id, name)

async def get_shelves(session: aiohttp.ClientSession, cookie: str) -> List[Shelf]:
    """获取所有书架列表"""
    url = f"https://{API_DOMAIN}/users-users_fav-page-1-c-0.html"
    headers = get_request_headers_with_cookie(cookie)
    async with session.get(url, headers=headers) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"Unexpected status {resp.status}: {text}")
    
    soup = BeautifulSoup(text, "html.parser")
    shelves = [parse_shelf(a) for a in soup.select('.nav_list > a')]
    return shelves

async def get_all_comics_from_shelf(session: aiohttp.ClientSession, cookie: str, shelf_id: int) -> List[ComicInFavorite]:
    """获取指定书架的所有书籍（所有分页）"""
    all_comics = []
    
    # 先获取第一页来确定总页数
    first_page_result = await get_favorite(session, cookie, shelf_id, 1)
    all_comics.extend(first_page_result.comics)
    total_pages = first_page_result.total_page
    
    print(f"书架 '{first_page_result.shelf.name}' 共有 {total_pages} 页")
    
    # 获取剩余页面
    if total_pages > 1:
        tasks = []
        for page in range(2, total_pages + 1):
            task = get_favorite(session, cookie, shelf_id, page)
            tasks.append(task)
        
        print(f"正在获取第 2-{total_pages} 页...")
        results = await asyncio.gather(*tasks)
        
        for result in results:
            all_comics.extend(result.comics)
    
    return all_comics

async def main(cookie: str, shelf_id: int = None):
    async with aiohttp.ClientSession() as session:
        # 如果没有指定书架ID，先获取书架列表让用户选择
        if shelf_id is None:
            print("正在获取书架列表...")
            shelves = await get_shelves(session, cookie)
            
            print("\n可用的书架:")
            for i, shelf in enumerate(shelves):
                print(f"{i}: {shelf.name} (ID: {shelf.id})")
            
            try:
                choice = input("\n请选择书架编号 (直接回车选择'全部'): ").strip()
                if choice == "":
                    shelf_id = 0  # 默认选择全部
                else:
                    shelf_index = int(choice)
                    if 0 <= shelf_index < len(shelves):
                        shelf_id = shelves[shelf_index].id
                    else:
                        print("无效的选择，使用默认书架'全部'")
                        shelf_id = 0
            except (ValueError, KeyboardInterrupt):
                print("无效输入或取消操作，使用默认书架'全部'")
                shelf_id = 0
        
        # 获取所有书籍
        all_comics = await get_all_comics_from_shelf(session, cookie, shelf_id)
        
        # 构造结果
        result = {
            "comics": [asdict(comic) for comic in all_comics],
            "total_comics": len(all_comics),
            "shelf_metadata": {
                "shelf_id": shelf_id,
                "shelf_name": all_comics[0].shelf.name if all_comics else "empty",
                "export_time": datetime.now().isoformat(),
                "source": "shelf_info"
            }
        }
        
        # 创建search_results目录（与搜索结果统一）
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIRECTORIES['search_results'])
        os.makedirs(save_dir, exist_ok=True)
        
        # 保存到文件
        shelf_name = all_comics[0].shelf.name if all_comics else "empty"
        # 替换文件名中的非法字符
        safe_shelf_name = re.sub(r'[<>:"/\\|?*]', '_', shelf_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"shelf_{safe_shelf_name}_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"书架信息已保存到文件: {filepath}")
        print(f"共获取到 {len(all_comics)} 本漫画")
        print("格式说明: 已保存为统一JSON格式，保存在search_results目录下")
        print("可使用get_url.py自动扫描该目录并选择文件获取下载链接")

if __name__ == "__main__":
    try:
        # 从配置文件获取cookie
        ck = get_cookie()
        # 运行主程序
        asyncio.run(main(ck))
    except ValueError as e:
        print(f"配置错误: {e}")
        print("请检查config.py文件中的WNACG_COOKIE设置")
