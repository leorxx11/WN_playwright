#!/usr/bin/env python3
"""
ZIP文件按作者分类脚本
将downloads目录下的ZIP文件按作者分类到class目录下的不同文件夹中
基于name.csv中的作者列表进行匹配，支持模糊匹配
"""

import os
import re
import csv
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Set
from difflib import SequenceMatcher

def extract_author_from_filename(filename: str) -> Optional[str]:
    """
    从ZIP文件名中提取作者名
    
    Args:
        filename: ZIP文件名
        
    Returns:
        作者名，如果无法提取则返回None
    """
    # 移除文件扩展名
    name = filename.replace('.zip', '')
    
    # 处理以()开头的情况，如: (C101) [タニシ屋 (たにし)]
    if name.startswith('('):
        # 找到第一个)后的内容
        closing_paren = name.find(')')
        if closing_paren != -1:
            remaining = name[closing_paren + 1:].strip()
            # 在剩余部分找第一个[]
            if remaining.startswith('['):
                end_bracket = remaining.find(']')
                if end_bracket != -1:
                    author_part = remaining[1:end_bracket]
                    # 返回完整的作者信息，保留团体名称
                    return author_part.strip() if author_part.strip() else None
    
    # 处理直接以[开头的情况
    elif name.startswith('['):
        # 第一个[]中的内容一定是作者名
        first_bracket_end = name.find(']')
        if first_bracket_end != -1:
            first_part = name[1:first_bracket_end]  # 第一个[]内的内容
            return first_part.strip() if first_part.strip() else None
        
    
    return None

def load_known_authors(csv_path: Path) -> Set[str]:
    """
    从name.csv文件中加载已知作者列表
    
    Args:
        csv_path: name.csv文件路径
        
    Returns:
        已知作者名称的集合
    """
    known_authors = set()
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                author_name = row['Name'].strip()
                if author_name and author_name != 'other':
                    known_authors.add(author_name)
    except Exception as e:
        print(f"警告: 无法读取name.csv文件: {e}")
    
    return known_authors

def similarity(a: str, b: str) -> float:
    """
    计算两个字符串的相似度
    
    Args:
        a, b: 要比较的字符串
        
    Returns:
        相似度分数 (0.0-1.0)
    """
    return SequenceMatcher(None, a, b).ratio()

def normalize_author_name(author: str) -> str:
    """
    标准化作者名称以便更好地匹配
    
    Args:
        author: 原始作者名
        
    Returns:
        标准化后的作者名
    """
    # 处理常见的字符变体
    char_variants = {
        '倶': '俱',  # 俱乐部的变体字
        '楽': '乐',  # 乐的简繁变体
        '學': '学',  # 学的繁简变体
        '會': '会',  # 会的繁简变体
    }
    
    normalized = author
    for variant, standard in char_variants.items():
        normalized = normalized.replace(variant, standard)
    
    return normalized

 

def extract_author_variants(author: str) -> List[str]:
    """
    提取作者名称的所有可能变体，用于匹配别名
    
    Args:
        author: 原始作者字符串
        
    Returns:
        作者名称变体列表
    """
    variants = [author]  # 原始名称
    
    # 处理汉化组前缀格式：[汉化组][作者] 或 汉化组][作者
    if '][' in author:
        # 提取'][' 后的部分
        after_group = author.split('][')[-1]
        if after_group:
            variants.append(after_group.strip())
    
    # 如果包含括号，提取括号内外的内容
    if '(' in author and ')' in author:
        # 提取括号外的部分（通常是社团名）
        circle_match = re.match(r'^(.+?)\s*\([^)]*\)', author)
        if circle_match:
            circle_name = circle_match.group(1).strip()
            variants.append(circle_name)
        
        # 提取括号内的部分（通常是个人作者名）
        author_match = re.search(r'\(([^)]+)\)', author)
        if author_match:
            inner_author = author_match.group(1).strip()
            variants.append(inner_author)
    
    # 如果包含全角括号
    if '（' in author and '）' in author:
        # 提取全角括号外的部分
        circle_match = re.match(r'^(.+?)（[^）]*）', author)
        if circle_match:
            circle_name = circle_match.group(1).strip()
            variants.append(circle_name)
        
        # 提取全角括号内的部分
        author_match = re.search(r'（([^）]+)）', author)
        if author_match:
            inner_author = author_match.group(1).strip()
            variants.append(inner_author)
    
    # 去重并过滤空字符串
    unique_variants = []
    for variant in variants:
        if variant and variant not in unique_variants:
            unique_variants.append(variant)
    
    return unique_variants

def find_best_author_match(extracted_author: str, known_authors: Set[str], threshold: float = 0.6) -> Optional[str]:
    """
    在已知作者中找到最佳匹配，增强别名匹配能力
    
    Args:
        extracted_author: 从文件名中提取的作者名
        known_authors: 已知作者集合
        threshold: 匹配阈值，降低到0.6以处理更多变体
        
    Returns:
        最佳匹配的作者名，如果没有找到则返回None
    """
    best_match = None
    best_score = 0.0
    
    # 提取所有可能的变体
    extracted_variants = extract_author_variants(extracted_author)
    
    for known_author in known_authors:
        known_variants = extract_author_variants(known_author)
        
        # 第一轮：精确匹配
        for ext_variant in extracted_variants:
            for known_variant in known_variants:
                # 直接匹配
                if ext_variant == known_variant:
                    return known_author
                
                # 标准化后匹配
                normalized_ext = normalize_author_name(ext_variant)
                normalized_known = normalize_author_name(known_variant)
                if normalized_ext == normalized_known:
                    return known_author
        
        # 第二轮：包含关系匹配（特别处理作者别名）
        for ext_variant in extracted_variants:
            for known_variant in known_variants:
                normalized_ext = normalize_author_name(ext_variant)
                normalized_known = normalize_author_name(known_variant)
                
                # 包含关系匹配（长度限制避免误匹配）
                if len(normalized_ext) > 2 and len(normalized_known) > 2:
                    if normalized_ext in normalized_known or normalized_known in normalized_ext:
                        return known_author
        
        # 第三轮：相似度匹配
        max_similarity = 0.0
        for ext_variant in extracted_variants:
            for known_variant in known_variants:
                # 计算多种相似度
                scores = [
                    similarity(ext_variant, known_variant),
                    similarity(normalize_author_name(ext_variant), normalize_author_name(known_variant))
                ]
                
                current_max = max(scores)
                if current_max > max_similarity:
                    max_similarity = current_max
        
        # 更新最佳匹配
        if max_similarity > best_score and max_similarity >= threshold:
            best_score = max_similarity
            best_match = known_author
    
    return best_match

def group_files_by_author(url_dir: Path, known_authors: Set[str]):
    """
    按作者对文件进行分组
    
    Args:
        url_dir: downloads目录路径
        known_authors: 已知作者集合
        
    Returns:
        tuple: (已知作者分组, 未知作者分组, 无法识别作者的文件)
    """
    known_author_groups = defaultdict(list)  # 已知作者的分组
    unknown_author_groups = defaultdict(list)  # 未知作者的分组
    unclassified = []  # 无法识别作者的文件
    
    # 获取所有ZIP文件
    zip_files = [f for f in os.listdir(url_dir) if f.endswith('.zip')]
    
    print(f"发现 {len(zip_files)} 个ZIP文件")
    print(f"已知作者数量: {len(known_authors)}")
    
    # 按作者分组
    for filename in zip_files:
        author = extract_author_from_filename(filename)
        if author:
            # 尝试匹配已知作者
            matched_author = find_best_author_match(author, known_authors)
            
            if matched_author:
                known_author_groups[matched_author].append(filename)
                print(f"文件: {filename[:50]}... -> 作者: {author} -> 匹配: {matched_author}")
            else:
                unknown_author_groups[author].append(filename)
                print(f"文件: {filename[:50]}... -> 作者: {author} -> 未知作者")
        else:
            unclassified.append(filename)
            print(f"文件: {filename[:50]}... -> 无法识别作者")
    
    print(f"\n匹配到已知作者: {len(known_author_groups)} 个")
    print(f"发现未知作者: {len(unknown_author_groups)} 个")  
    print(f"无法分类的文件: {len(unclassified)} 个")
    
    return dict(known_author_groups), dict(unknown_author_groups), unclassified

def update_name_csv(csv_path: Path, new_authors: Set[str]) -> bool:
    """
    更新name.csv文件，添加新作者
    
    Args:
        csv_path: name.csv文件路径
        new_authors: 要添加的新作者集合
        
    Returns:
        是否成功更新
    """
    if not new_authors:
        return True
        
    try:
        # 读取现有数据
        existing_data = []
        max_id = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_data.append(row)
                max_id = max(max_id, int(row['ID']))
        
        # 添加新作者
        for author in new_authors:
            max_id += 1
            existing_data.append({'ID': str(max_id), 'Name': author})
        
        # 写回文件
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            fieldnames = ['ID', 'Name']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in existing_data:
                writer.writerow(row)
        
        print(f"已更新name.csv，添加了 {len(new_authors)} 个新作者")
        return True
        
    except Exception as e:
        print(f"更新name.csv失败: {e}")
        return False

def create_author_directories(url_dir: Path, class_dir: Path, known_author_groups: Dict[str, List[str]], 
                            unknown_author_groups: Dict[str, List[str]], unclassified: List[str]) -> int:
    """
    创建作者目录并移动文件到class目录
    
    Args:
        url_dir: downloads目录路径
        class_dir: class目录路径  
        known_author_groups: 已知作者分组
        unknown_author_groups: 未知作者分组
        unclassified: 无法识别作者的文件
        
    Returns:
        移动的文件总数
    """
    moved_count = 0
    
    # 确保class目录存在
    class_dir.mkdir(exist_ok=True)
    
    # 处理已知作者的文件
    for author, files in known_author_groups.items():
        # 为已知作者创建文件夹
        safe_author_name = re.sub(r'[<>:"/\\|?*]', '_', author)
        author_dir = class_dir / safe_author_name
        author_dir.mkdir(exist_ok=True)
        
        print(f"\n为已知作者 '{author}' 创建文件夹: {safe_author_name}")
        print(f"移动 {len(files)} 个文件:")
        
        for filename in files:
            src_path = url_dir / filename
            dst_path = author_dir / filename
            
            if src_path.exists() and not dst_path.exists():
                shutil.move(str(src_path), str(dst_path))
                print(f"  移动: {filename}")
                moved_count += 1
            elif dst_path.exists():
                print(f"  跳过: {filename} (目标已存在)")
            else:
                print(f"  错误: {filename} (源文件不存在)")
    
    # 处理未知作者的文件
    new_authors_to_add = set()
    other_dir = class_dir / "other"
    
    for author, files in unknown_author_groups.items():
        if len(files) >= 2:  # 多本漫画，创建作者文件夹并添加到name.csv
            safe_author_name = re.sub(r'[<>:"/\\|?*]', '_', author)
            author_dir = class_dir / safe_author_name
            author_dir.mkdir(exist_ok=True)
            new_authors_to_add.add(author)
            
            print(f"\n为新作者 '{author}' 创建文件夹: {safe_author_name}")
            print(f"移动 {len(files)} 个文件:")
            
            for filename in files:
                src_path = url_dir / filename
                dst_path = author_dir / filename
                
                if src_path.exists() and not dst_path.exists():
                    shutil.move(str(src_path), str(dst_path))
                    print(f"  移动: {filename}")
                    moved_count += 1
                elif dst_path.exists():
                    print(f"  跳过: {filename} (目标已存在)")
                else:
                    print(f"  错误: {filename} (源文件不存在)")
        else:  # 单本漫画，归入other文件夹
            other_dir.mkdir(exist_ok=True)
            
            print(f"\n作者 '{author}' 只有 {len(files)} 个文件，归入other文件夹:")
            
            for filename in files:
                src_path = url_dir / filename
                dst_path = other_dir / filename
                
                if src_path.exists() and not dst_path.exists():
                    shutil.move(str(src_path), str(dst_path))
                    print(f"  移动: {filename}")
                    moved_count += 1
                elif dst_path.exists():
                    print(f"  跳过: {filename} (目标已存在)")
                else:
                    print(f"  错误: {filename} (源文件不存在)")
    
    # 处理无法识别作者的文件，归入other文件夹
    if unclassified:
        other_dir.mkdir(exist_ok=True)
        print(f"\n将 {len(unclassified)} 个无法识别作者的文件归入other文件夹:")
        
        for filename in unclassified:
            src_path = url_dir / filename
            dst_path = other_dir / filename
            
            if src_path.exists() and not dst_path.exists():
                shutil.move(str(src_path), str(dst_path))
                print(f"  移动: {filename}")
                moved_count += 1
            elif dst_path.exists():
                print(f"  跳过: {filename} (目标已存在)")
            else:
                print(f"  错误: {filename} (源文件不存在)")
    
    return moved_count, new_authors_to_add

def test_author_matching():
    """测试作者匹配算法"""
    print("=== 测试作者匹配算法 ===\n")
    
    # 测试文件名提取
    print("=== 测试文件名提取 ===")
    test_filenames = [
        "[たにし] 潤愛 [中国翻訳].zip",
        "[篆儀通文書坊漢化][たにし] 淫毛.zip", 
        "(C102) [タニシ屋 (奥谷たにし)] 修行なう (Fate／Grand Order) [DL版] [黑锅汉化组].zip",
        "(C101) [タニシ屋 (たにし)] わるいこ♡   おまけペーパー (Fate／Grand Order) [黑锅汉化组].zip"
    ]
    
    for filename in test_filenames:
        extracted = extract_author_from_filename(filename)
        print(f"文件: {filename[:50]}...")
        print(f"提取: '{extracted}'\n")
    
    # 测试用例：提取出的作者名
    print("=== 测试作者匹配 ===")
    test_cases = [
        "たにし",
        "篆儀通文書坊漢化",  # 按你的逻辑，第一个[]是作者
        "タニシ屋 (奥谷たにし)",
        "タニシ屋 (たにし)"
    ]
    
    # 模拟已知作者列表，包含标准作者名和汉化组作者名
    known_authors = {"タニシ屋（奥谷たにし）", "篆儀通文書坊漢化", "其他作者1", "其他作者2"}
    
    print(f"已知作者: {list(known_authors)}\n")
    
    for test_case in test_cases:
        print(f"测试: '{test_case}'")
        
        # 显示变体提取结果
        variants = extract_author_variants(test_case)
        print(f"  变体: {variants}")
        
        # 测试匹配
        match = find_best_author_match(test_case, known_authors, threshold=0.5)
        print(f"  匹配结果: {match}")
        
        print()

def main():
    """主函数"""
    import sys
    
    # 如果传入test参数，运行测试
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_author_matching()
        return
    
    # 获取目录路径
    current_dir = Path(__file__).parent
    url_dir = current_dir / "downloads"
    class_dir = current_dir / "class"
    csv_path = current_dir / "name.csv"
    
    if not url_dir.exists():
        print(f"错误: downloads目录不存在: {url_dir}")
        return
    
    if not csv_path.exists():
        print(f"错误: name.csv文件不存在: {csv_path}")
        return
    
    print(f"开始分析目录: {url_dir}")
    print(f"分类目标目录: {class_dir}")
    
    # 加载已知作者列表
    known_authors = load_known_authors(csv_path)
    print(f"已加载 {len(known_authors)} 个已知作者")
    
    # 按作者分组文件
    known_author_groups, unknown_author_groups, unclassified = group_files_by_author(url_dir, known_authors)
    
    if not known_author_groups and not unknown_author_groups:
        print("没有找到可以分类的文件")
        return
    
    # 显示分组结果
    print("\n=== 分组结果 ===")
    
    if known_author_groups:
        print("\n已知作者:")
        for author_name, files in known_author_groups.items():
            print(f"  {author_name} ({len(files)} 个文件)")
    
    if unknown_author_groups:
        print("\n未知作者:")
        for author_name, files in unknown_author_groups.items():
            status = "新作者(≥2本)" if len(files) >= 2 else "归入other(1本)"
            print(f"  {author_name} ({len(files)} 个文件) - {status}")
    
    if unclassified:
        print(f"\n无法识别作者的文件: {len(unclassified)} 个")
    
    # 统计操作
    known_files = sum(len(files) for files in known_author_groups.values())
    new_author_files = sum(len(files) for _, files in unknown_author_groups.items() if len(files) >= 2)
    other_files = sum(len(files) for _, files in unknown_author_groups.items() if len(files) < 2) + len(unclassified)
    new_authors_count = sum(1 for _, files in unknown_author_groups.items() if len(files) >= 2)
    
    print(f"\n=== 操作预览 ===")
    print(f"已知作者文件: {known_files} 个 -> 各自作者文件夹")
    print(f"新作者文件: {new_author_files} 个 -> 创建新文件夹 ({new_authors_count} 个新作者)")
    print(f"other文件: {other_files} 个 -> other文件夹")
    print(f"总文件数: {known_files + new_author_files + other_files}")
    
    if new_authors_count > 0:
        print(f"\n将向name.csv添加 {new_authors_count} 个新作者")
    
    try:
        response = input("\n是否继续执行分类? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            moved_count, new_authors_to_add = create_author_directories(
                url_dir, class_dir, known_author_groups, unknown_author_groups, unclassified
            )
            
            # 更新name.csv
            if new_authors_to_add:
                if update_name_csv(csv_path, new_authors_to_add):
                    print(f"\n分类完成！总共移动了 {moved_count} 个文件")
                    print(f"添加了 {len(new_authors_to_add)} 个新作者到name.csv")
                else:
                    print(f"\n分类完成，但更新name.csv失败！总共移动了 {moved_count} 个文件")
            else:
                print(f"\n分类完成！总共移动了 {moved_count} 个文件")
        else:
            print("操作已取消")
    except (EOFError, KeyboardInterrupt):
        print("\n操作已取消")

if __name__ == "__main__":
    main()