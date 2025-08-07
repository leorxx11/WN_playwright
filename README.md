# WN_playwright

[中文](#中文文档) | [English](#english-documentation)

## 中文文档

一个基于 Python 的 WNACG 漫画网站爬虫工具，用于提取用户书架信息和自动下载漫画。

### 功能特性

- **书架信息提取**: 异步爬取用户书架中的漫画信息
- **单个下载**: 基于 Playwright 的浏览器自动化下载单部漫画
- **批量下载**: 从书架JSON文件批量下载多部漫画，支持断点续传
- **配置管理**: 支持 Cookie 认证和 API 配置
- **日志系统**: 详细的日志记录，支持进度追踪和错误排查
- **数据导出**: JSON 格式导出书架数据

### 项目结构

```
├── config.py              # 配置管理和认证设置
├── get_shelf_info.py      # 书架信息爬取脚本
├── comic_downloader.py    # 漫画下载脚本
├── batch_download.py      # 批量下载脚本
├── classify_by_author.py  # 按作者分类脚本
├── requirements.txt       # 依赖包列表
├── CLAUDE.md             # 项目开发指南
├── 需求.md               # 中文需求文档
└── name.csv              # 作者名称数据
```

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 配置认证

在 `config.py` 中配置认证信息：

```python
# 方式1: 用户名密码
LOGIN_CONFIG = {
    "username": "your_username",
    "password": "your_password"
}

# 方式2: Cookie (推荐)
WNACG_COOKIE = "your_session_cookie"
```

或使用环境变量：
```bash
export WNACG_USERNAME="your_username"
export WNACG_PASSWORD="your_password"
export WNACG_COOKIE="your_cookie"
```

### 使用方法

**提取书架信息:**
```bash
python get_shelf_info.py
```
书架数据将导出到 `search_results/shelf_{name}_{timestamp}.json`

**按作者分类:**
```bash
python classify_by_author.py
```

**下载漫画:**
```bash
# 单个下载
python comic_downloader.py

# 批量下载
python batch_download.py
```
下载的文件将保存到 `url/` 目录

### 输出格式

书架数据 JSON 结构：
```json
{
  "comics": [...],
  "total_comics": 123,
  "shelf_metadata": {
    "shelf_id": 456,
    "shelf_name": "我的收藏",
    "export_time": "2024-01-01T12:00:00Z",
    "source": "shelf_info"
  }
}
```

### 注意事项

- 当前 API 域名为 `www.wnacg01.cc`，如有变更请更新 `config.py` 中的 `API_DOMAIN`
- 下载功能包含重试机制和 SSL 警告处理
- 所有敏感文件已在 `.gitignore` 中排除

---

## English Documentation

A Python-based WNACG manga site scraper that extracts user shelf information and comic metadata with automated download capabilities.

### Features

- **Shelf Information Extraction**: Asynchronously scrape comic information from user shelves/bookmarks
- **Single Comic Download**: Browser automation-based downloading using Playwright for individual comics
- **Batch Download**: Automated batch downloading from shelf JSON files with progress tracking and resume capability
- **Configuration Management**: Support for Cookie authentication and API endpoint configuration
- **Logging System**: Comprehensive logging for both single and batch downloads with detailed progress tracking
- **Data Export**: JSON format export of shelf data

### Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

### Authentication Setup

Configure credentials in `config.py`:

```python
# Option 1: Username/Password
LOGIN_CONFIG = {
    "username": "your_username", 
    "password": "your_password"
}

# Option 2: Cookie (Recommended)
WNACG_COOKIE = "your_session_cookie"
```

Or use environment variables:
```bash
export WNACG_USERNAME="your_username"
export WNACG_PASSWORD="your_password" 
export WNACG_COOKIE="your_cookie"
```

### Usage

**Extract shelf information:**
```bash
python get_shelf_info.py
```
Shelf data will be exported to `search_results/shelf_{name}_{timestamp}.json`

**Classify by author:**
```bash
python classify_by_author.py
```

**Download comics:**
```bash
# Single download
python comic_downloader.py

# Batch download
python batch_download.py
```
Downloaded files will be saved to the `url/` directory

### Output Format

Shelf data JSON structure:
```json
{
  "comics": [...],
  "total_comics": 123,
  "shelf_metadata": {
    "shelf_id": 456,
    "shelf_name": "My Collection",
    "export_time": "2024-01-01T12:00:00Z", 
    "source": "shelf_info"
  }
}
```

### Important Notes

- Current API domain is `www.wnacg01.cc` - update `API_DOMAIN` in config.py if it changes
- Download functionality includes retry mechanisms and SSL warning handling
- All sensitive files are excluded in `.gitignore`
- Downloads are optimized with long timeouts for slow networks
- Comprehensive logging system with separate log files for single and batch downloads

### License

This project is for educational and research purposes only. Please comply with the relevant website's terms of service.