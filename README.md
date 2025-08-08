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
├── config.py               # 配置管理和认证设置
├── get_shelf_info.py       # 书架信息爬取脚本
├── search_id.py            # 站内搜索与结果保存（关键词/标签）
├── comic_downloader.py     # 单个漫画下载（Playwright）
├── batch_download.py       # 批量下载（基于书架 JSON）
├── classify_by_author.py   # 按作者对已下载 ZIP 分类
├── requirements.txt        # 依赖包列表
├── CLAUDE.md               # 项目开发与维护说明
└── name.csv                # 作者名称数据（CSV，列：ID, Name）
```

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

可选（建议使用虚拟环境）：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用: .venv\\Scripts\\activate
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

注意：
- 不要在仓库中提交真实账号/密码或 Cookie。推荐使用环境变量。
- 运行 `python config.py` 可尝试自动登录并在本地生成 `cookie.json`；若站点策略变更导致失败，请手动设置有效 Cookie。
- 为安全起见，日志中不会打印完整 Cookie；请妥善保管 `cookie.json`。

### 使用方法

**提取书架信息:**
```bash
python get_shelf_info.py
```
书架数据将导出到 `search_results/shelf_{name}_{timestamp}.json`

**站内搜索（关键词/标签）并保存结果:**
```bash
# 交互模式（推荐）
python search_id.py interactive

# 命令行
python search_id.py keyword "<关键词>" [页码]
python search_id.py tag "<标签>" [页码]
```
搜索结果可按匹配度展示，并可保存为与书架一致结构的 JSON（位于 `search_results/`）。

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
- 如遇证书警告，Playwright 已做处理；仍可在浏览器上下文启用 `ignore_https_errors=True`（代码中已有处理路径）。
- 建议适当控制请求频率，避免过快访问导致风控。

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

Optionally use a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
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

**Search by keyword or tag and save results:**
```bash
# Interactive mode
python search_id.py interactive

# CLI
python search_id.py keyword "<keyword>" [page]
python search_id.py tag "<tag>" [page]
```
Search results can be saved as JSON in the same structure as shelf data under `search_results/`.

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
- Avoid committing real credentials or cookies; prefer environment variables. `python config.py` can help generate `cookie.json` locally.
- Consider rate limiting to avoid being flagged by anti-bot measures.

### License

This project is for educational and research purposes only. Please comply with the relevant website's terms of service.