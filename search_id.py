import requests
from bs4 import BeautifulSoup
import time
import sys
from urllib.parse import quote
import re
from difflib import SequenceMatcher
import json
from datetime import datetime
import os

# 从配置文件导入
from config import (
    API_DOMAIN, get_headers, REQUEST_CONFIG, SEARCH_CONFIG, 
    DIRECTORIES
)

class SearchError(Exception):
    """搜索相关的异常"""
    pass

def parse_search_result(html, is_tag=False):
    soup = BeautifulSoup(html, "html.parser")
    comics = []
    for li in soup.select(".li.gallary_item"):
        try:
            title_a = li.select_one(".title > a")
            if not title_a:
                continue
            comic_id = int(title_a["href"].replace("/photos-index-aid-", "").replace(".html", ""))
            title_html = title_a.get("title", "").strip()
            title = ''.join(title_a.stripped_strings)
            img_tag = li.select_one("img")
            cover = "https:" + img_tag["src"] if img_tag else ""
            info_col = li.select_one(".info_col")
            additional_info = info_col.get_text(strip=True) if info_col else ""
            
            comics.append({
                "id": comic_id,
                "title_html": title_html,
                "title": title,
                "cover": cover,
                "additional_info": additional_info,
            })
        except (ValueError, TypeError, KeyError) as e:
            print(f"解析漫画项目失败: {e}")
            continue

    current_page = 1
    thispage = soup.select_one(".thispage")
    if thispage:
        try:
            current_page = int(thispage.get_text())
        except ValueError:
            pass

    if is_tag:
        total_page = 1
        paginator_links = soup.select(".f_left.paginator > a")
        if paginator_links:
            try:
                total_page = int(paginator_links[-1].get_text())
            except (ValueError, IndexError):
                pass
        total_page = max(total_page, current_page)
    else:
        total_page = 1
        result_elem = soup.select_one("#bodywrap .result > b")
        if result_elem:
            try:
                total = int(result_elem.get_text().replace(",", ""))
                PAGE_SIZE = 24
                total_page = (total + PAGE_SIZE - 1) // PAGE_SIZE
            except ValueError:
                pass

    return {
        "comics": comics,
        "current_page": current_page,
        "total_page": total_page,
        "is_search_by_tag": is_tag,
    }

def make_request(url, params=None, max_retries=None):
    """发送HTTP请求，包含重试机制"""
    if max_retries is None:
        max_retries = REQUEST_CONFIG['max_retries']
    
    headers = get_headers()
    timeout = REQUEST_CONFIG['timeout']
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise SearchError(f"请求失败: {e}")
            print(f"请求失败，{2**attempt}秒后重试... ({attempt + 1}/{max_retries})")
            time.sleep(2**attempt)

def search_by_keyword(keyword, page_num=1):
    """根据关键词搜索"""
    params = {
        "q": keyword,
        "syn": "yes",
        "f": "_all",
        "s": "create_time_DESC",
        "p": page_num,
    }
    url = f"https://{API_DOMAIN}/search/index.php"
    resp = make_request(url, params=params)
    return parse_search_result(resp.text, is_tag=False)

def search_by_tag(tag_name, page_num=1):
    """根据标签搜索"""
    encoded_tag = quote(tag_name, safe='')
    url = f"https://{API_DOMAIN}/albums-index-page-{page_num}-tag-{encoded_tag}.html"
    resp = make_request(url)
    return parse_search_result(resp.text, is_tag=True)

def normalize_title(title):
    """标准化标题，去除多余的空格和符号"""
    # 统一全角半角字符
    title = title.replace('（', '(').replace('）', ')')
    title = title.replace('【', '[').replace('】', ']')
    # 去除多余空格
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def extract_chapter_info(title):
    """提取章节信息"""
    # 匹配各种章节格式
    patterns = [
        r'(\d+)-(\d+)話',
        r'(\d+)-(\d+)话',
        r'第(\d+)-(\d+)話',
        r'第(\d+)-(\d+)话',
        r'(\d+)~(\d+)話',
        r'(\d+)~(\d+)话',
        r'(\d+)-(\d+)',

        r'第(\d+)話',
        r'第(\d+)话',
        r'(\d+)話',
        r'(\d+)话',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            if len(match.groups()) == 2:
                return f"{match.group(1)}-{match.group(2)}"
            else:
                return match.group(1)
    return None

def calculate_similarity(query, title):
    """计算查询词与标题的相似度"""
    query_norm = normalize_title(query.lower())
    title_norm = normalize_title(title.lower())
    
    # 基础相似度
    similarity = SequenceMatcher(None, query_norm, title_norm).ratio()
    
    # 如果查询词完全包含在标题中，提高相似度
    if query_norm in title_norm:
        similarity += 0.3
    
    # 如果标题包含查询词的主要关键词，提高相似度
    query_words = set(query_norm.split())
    title_words = set(title_norm.split())
    common_words = query_words.intersection(title_words)
    if common_words and len(common_words) >= len(query_words) * 0.7:
        similarity += 0.2
    
    return min(similarity, 1.0)

def smart_match_titles(query, comics, min_similarity=None):
    """智能匹配标题"""
    if min_similarity is None:
        min_similarity = SEARCH_CONFIG['min_similarity']
    
    matched_comics = []
    
    for comic in comics:
        title = comic['title']
        similarity = calculate_similarity(query, title)
        
        if similarity >= min_similarity:
            comic_copy = comic.copy()
            comic_copy['similarity'] = similarity
            comic_copy['chapter_info'] = extract_chapter_info(title)
            matched_comics.append(comic_copy)
    
    # 按相似度排序
    matched_comics.sort(key=lambda x: x['similarity'], reverse=True)
    return matched_comics

def get_all_search_results(search_func, query, max_pages=None):
    """获取所有搜索结果"""
    if max_pages is None:
        max_pages = REQUEST_CONFIG['max_pages']
    
    all_comics = []
    current_page = 1
    
    print("正在获取搜索结果...")
    
    while current_page <= max_pages:
        try:
            print(f"正在获取第 {current_page} 页...", end='', flush=True)
            results = search_func(query, current_page)
            
            if not results['comics']:
                print(" 无结果")
                break
            
            all_comics.extend(results['comics'])
            print(f" 获取到 {len(results['comics'])} 个结果")
            
            if current_page >= results['total_page']:
                break
            
            current_page += 1
            time.sleep(0.5)  # 避免请求过于频繁
            
        except SearchError as e:
            print(f"\n获取第 {current_page} 页时出错: {e}")
            break
        except Exception as e:
            print(f"\n未知错误: {e}")
            break
    
    print(f"总共获取到 {len(all_comics)} 个结果")
    return all_comics

def display_category(title, comics_list):
        if not comics_list:
            return
        
        print(f"\n=== {title} ({len(comics_list)}个) ===")
        for i, comic in enumerate(comics_list, 1):
            similarity_percent = int(comic['similarity'] * 100)
            print(f"\n{i}. ID: {comic['id']} (匹配度: {similarity_percent}%)")
            print(f"   标题: {comic['title']}")
            
            if comic.get('chapter_info'):
                print(f"   章节: {comic['chapter_info']}")
            
            if comic['additional_info']:
                print(f"   信息: {comic['additional_info']}")
            
            print(f"   封面: {comic['cover']}")

def display_smart_results(query, comics, show_all=False):
    """智能显示搜索结果"""
    if not comics:
        print("没有找到相关结果")
        return
    
    # 智能匹配
    matched_comics = smart_match_titles(query, comics)
    
    if not matched_comics:
        print("没有找到匹配的结果")
        return
    
    # 分类显示
    high_match = [c for c in matched_comics if c['similarity'] >= 0.8]
    medium_match = [c for c in matched_comics if 0.5 <= c['similarity'] < 0.8]
    low_match = [c for c in matched_comics if c['similarity'] < 0.5]
    
    # 显示结果
    if high_match:
        display_category("高度匹配", high_match)
    
    if medium_match and (show_all or not high_match):
        display_category("中等匹配", medium_match)
    
    if low_match and show_all:
        display_category("低匹配度", low_match)
    
    # 显示统计信息
    total_shown = len(high_match)
    if show_all or not high_match:
        total_shown += len(medium_match)
    if show_all:
        total_shown += len(low_match)
    
    print("\n=== 搜索统计 ===")
    print(f"总结果数: {len(comics)}")
    print(f"匹配结果数: {len(matched_comics)}")
    print(f"显示结果数: {total_shown}")
    
    if not show_all and (medium_match or low_match):
        print("\n提示: 输入 'all' 可显示所有匹配结果")

def save_results_to_json(results, filename):
    """保存结果到JSON文件"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {filename}")
        return True
    except Exception as e:
        print(f"保存JSON文件失败: {e}")
        return False

def group_results_by_manga_name(comics):
    """按漫画名字分组结果"""
    manga_groups = {}
    
    for comic in comics:
        title = comic.get('title', '')
        
        # 提取基础漫画名（去除章节信息）
        base_name = title
        
        # 尝试移除章节信息来获取基础名称
        chapter_patterns = [
            r'\s+\d+-\d+話$',
            r'\s+\d+-\d+话$', 
            r'\s+第\d+-\d+話$',
            r'\s+第\d+-\d+话$',
            r'\s+\d+~\d+話$',
            r'\s+\d+~\d+话$',
            r'\s+第\d+話$',
            r'\s+第\d+话$',
            r'\s+\d+話$',
            r'\s+\d+话$',
            r'\s+\(\d+-\d+\)$',
            r'\s+\[\d+-\d+\]$',
        ]
        
        for pattern in chapter_patterns:
            match = re.search(pattern, base_name)
            if match:
                base_name = base_name[:match.start()].strip()
                break
        
        # 进一步清理基础名称
        base_name = re.sub(r'\s+', ' ', base_name).strip()
        
        if base_name not in manga_groups:
            manga_groups[base_name] = []
        
        manga_groups[base_name].append(comic)
    
    return manga_groups

def save_grouped_results(comics, query, save_format='json'):
    """按漫画名字保存分组结果，使用统一的书架格式"""
    if not comics:
        print("没有结果可保存")
        return False
    
    # 创建保存目录
    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DIRECTORIES['search_results'])
    os.makedirs(save_dir, exist_ok=True)
    
    # 按漫画名分组
    manga_groups = group_results_by_manga_name(comics)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_query = clean_filename(query)
    
    saved_files = []
    
    if save_format.lower() == 'grouped':
        # 每个漫画系列保存为单独文件
        for manga_name, manga_comics in manga_groups.items():
            clean_manga_name = clean_filename(manga_name)
            filename = f"search_{clean_query}_{clean_manga_name}_{timestamp}.json"
            filepath = os.path.join(save_dir, filename)
            
            # 转换为统一格式
            converted_comics = [convert_search_result_to_shelf_format(comic, query) for comic in manga_comics]
            
            save_data = {
                'comics': converted_comics,
                'total_comics': len(converted_comics),
                'search_metadata': {
                    'search_query': query,
                    'manga_name': manga_name,
                    'search_time': datetime.now().isoformat(),
                    'search_type': 'grouped'
                }
            }
            
            if save_results_to_json(save_data, filepath):
                saved_files.append(filepath)
    else:
        # 保存所有结果到单个JSON文件
        filename = f"search_{clean_query}_all_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)
        
        # 转换为统一格式
        converted_comics = [convert_search_result_to_shelf_format(comic, query) for comic in comics]
        
        save_data = {
            'comics': converted_comics,
            'total_comics': len(converted_comics),
            'search_metadata': {
                'search_query': query,
                'search_time': datetime.now().isoformat(),
                'manga_groups': {name: len(group) for name, group in manga_groups.items()},
                'search_type': 'all'
            }
        }
        
        success = save_results_to_json(save_data, filepath)
        if success:
            saved_files.append(filepath)
    
    # 显示分组统计
    if manga_groups:
        print("\n=== 按漫画名分组统计 ===")
        for manga_name, manga_comics in sorted(manga_groups.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"{manga_name}: {len(manga_comics)}个结果")
    
    print("\n格式说明: 已转换为与书架信息相同的JSON格式，保存在search_results目录下")
    print("可使用get_url.py自动扫描该目录并选择文件获取下载链接")
    
    return len(saved_files) > 0

def ask_save_results(comics, query):
    """询问是否保存结果"""
    if not comics:
        return
    
    save_choice = input(f"\n是否保存搜索结果? ({len(comics)}个结果) (y/N): ").strip().lower()
    if save_choice != 'y':
        return
    
    print("正在保存结果...")
    # 直接保存为单个JSON文件，不再询问保存方式
    success = save_grouped_results(comics, query, save_format='json')
    
    if success:
        print("保存完成!")
    else:
        print("保存失败!")

def clean_filename(filename):
    """清理文件名，移除不合法字符"""
    # 移除或替换不合法的文件名字符
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # 限制文件名长度
    if len(filename) > 200:
        filename = filename[:200]
    return filename.strip()

def convert_search_result_to_shelf_format(comic, search_query=""):
    """将搜索结果转换为书架格式"""
    return {
        "id": comic.get("id"),
        "title": comic.get("title", ""),
        "cover": comic.get("cover", ""),
        "favorite_time": "",  # 搜索结果没有收藏时间
        "shelf": {
            "id": 0,  # 搜索结果没有书架ID
            "name": f"搜索结果-{search_query}" if search_query else "搜索结果"
        },
        # 搜索结果的额外信息
        "search_info": {
            "title_html": comic.get("title_html", ""),
            "additional_info": comic.get("additional_info", ""),
            "similarity": comic.get("similarity", 0),
            "chapter_info": comic.get("chapter_info", ""),
            "search_query": search_query
        }
    }

def interactive_search():
    """交互式搜索界面"""
    print("=== WNACG 智能搜索工具 ===")
    print("支持的搜索类型:")
    print("1. 关键词搜索")
    print("2. 标签搜索")
    print("特色功能:")
    print("- 智能匹配章节格式 (如: 19-20話)")
    print("- 自动获取所有页面结果")
    print("- 按匹配度排序显示")
    print("- 按漫画名字保存结果")
    print("- 生成与书架格式统一的JSON，可直接用于get_url.py")
    print("输入 'quit' 或 'q' 退出")
    
    while True:
        try:
            print("\n" + "="*50)
            search_type = input("请选择搜索类型 (1/2) 或输入 'q' 退出: ").strip()
            
            if search_type.lower() in ['q', 'quit']:
                print("再见!")
                break
            
            if search_type not in ['1', '2']:
                print("无效的选择，请输入 1 或 2")
                continue
            
            query = input("请输入搜索内容: ").strip()
            if not query:
                print("搜索内容不能为空")
                continue
            
            # 询问最大页面数
            max_pages = input("最大页面数 (默认20): ").strip()
            try:
                max_pages = int(max_pages) if max_pages else 20
            except ValueError:
                max_pages = 20
            
            print(f"\n开始智能搜索: {query}")
            
            # 直接获取所有页面结果
            if search_type == '1':
                all_comics = get_all_search_results(search_by_keyword, query, max_pages)
            else:
                all_comics = get_all_search_results(search_by_tag, query, max_pages)
            
            # 直接显示所有匹配度的结果
            display_smart_results(query, all_comics, show_all=True)
            
            # 询问是否保存结果
            ask_save_results(all_comics, query)
                        
        except KeyboardInterrupt:
            print("\n\n程序被中断，再见!")
            break
        except SearchError as e:
            print(f"搜索出错: {e}")
        except Exception as e:
            print(f"发生未知错误: {e}")

def search_command_line():
    """命令行参数搜索"""
    if len(sys.argv) < 3:
        print("用法:")
        print("  python search_id.py keyword <关键词> [页码]")
        print("  python search_id.py tag <标签名> [页码]")
        print("  python search_id.py interactive  # 交互模式")
        return
    
    search_type = sys.argv[1].lower()
    query = sys.argv[2]
    page = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    try:
        if search_type == 'keyword':
            results = search_by_keyword(query, page)
            comics = results['comics']
        elif search_type == 'tag':
            results = search_by_tag(query, page)
            comics = results['comics']
        else:
            print("无效的搜索类型，请使用 'keyword' 或 'tag'")
            return
        
        display_smart_results(query, comics)
        ask_save_results(comics, query)
        
    except SearchError as e:
        print(f"搜索失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'interactive':
        interactive_search()
    elif len(sys.argv) > 1:
        search_command_line()
    else:
        interactive_search()
