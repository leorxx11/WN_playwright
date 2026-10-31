# WN_playwright

基于 Python 的漫画爬虫工具，支持书架信息提取和自动下载。

## 功能特性

- 书架信息异步爬取和导出
- 单个/批量漫画下载（支持断点续传）
- 站内搜索（关键词/标签匹配）
- 按作者分类已下载内容
- Cookie/用户名密码认证

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 配置认证

**推荐方式：环境变量**

1. 复制 `.env.example` 为 `.env`：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件：
```bash
WNACG_USERNAME=your_username
WNACG_PASSWORD=your_password
```

**或直接设置环境变量：**
```bash
export WNACG_USERNAME=your_username
export WNACG_PASSWORD=your_password
```

**生成和验证 Cookie：**
```bash
python config.py  # 自动登录并生成 cookie.json
```

`config.py` 会打开与下载脚本共用的 `.playwright_profile/` 浏览器登录；profile 中已有登录态时直接读取 cookie，遇到 Cloudflare 验证请在浏览器中手动完成（最多等待 120 秒）。运行前需先执行 `playwright install chromium`，且不要同时运行下载脚本（profile 会被占用）。

## 使用方法

**提取书架信息:**
```bash
python get_shelf_info.py
```

**搜索并保存结果:**
```bash
python search_id.py interactive
```

**网页界面（推荐）:**
```bash
python web.py                 # 打开 http://127.0.0.1:8787，端口可用 --port 或 WNACG_WEB_PORT 修改
```
顶栏显示登录状态和下载进度。目前可用的页面：

- **搜索**：关键词或标签搜索（可设最多翻几页，搜索中可取消），结果直接勾选下载，或「保存全部/选中为 JSON」到 `search_results/`（格式与 `search_id.py` 一致）。
- **书架**：读取收藏的书架列表，点开书架读取全部漫画，直接勾选下载，或「导出全部/选中为 JSON」（格式与 `get_shelf_info.py` 一致）。
- **已导出**：打开 `search_results/` 里导出的书架/搜索 JSON，勾选要下载的漫画。点行切换、按住拖动连续切换、Shift+点击选一段，支持关键词/话数筛选、隐藏已下载、只选未下载，快捷键 `j`/`k`/空格/`a`/`i`/`u`。可以「导出选中为 JSON」（生成 `selected_*.json`，`batch_download.py` 也能选它），或直接「下载选中」加入下载队列。下载成功的漫画 ID 记录在 `download_history.json`，用于标记已下载；`batch_download.py` 也会跳过记录里已有的漫画。网页下载时不要同时运行命令行下载脚本（共用 `.playwright_profile/`）。
- **下载**：下载队列。列表页「下载选中」会把漫画加入队列，下载进行中也能继续追加，同一次浏览器会话里接着下。可以暂停/继续、重试失败的（整体或单部）、移除等待中的、清除已完成的；也能粘贴漫画 ID 或 `photos-index-aid-123.html` 网址直接加入。队列保存在 `download_queue.json`，服务重启后还在（不会自动开始，点「开始下载」继续）。下方「最近下载」列出 `download_history.json` 里的记录。
- **分类**：预览 `downloads/` 里的 zip 会归到 `class/` 的哪个文件夹：匹配 `name.csv` 的已知作者、≥2 本的新作者（可勾选加入 `name.csv`），其余归入 `other`（没有作者前缀的按作品名分组，可一键改用作品名做文件夹）。每组可取消、改文件夹名、展开后逐个取消文件，确认后才移动；目标已存在的文件不会覆盖。下载进行中不能分类。
- **账号**：查看用户名、域名、cookie 生成时间，检查登录状态，一键重新登录（正在下载时会等下载结束再登录）。

三个列表页面共用同一套勾选操作。cookie 过期时搜索和书架会提示去「账号」页重新登录。下面的命令行脚本仍然可用。

**下载漫画:**
```bash
python comic_downloader.py    # 单个下载
python batch_download.py      # 批量下载
```

**按作者分类:**
```bash
python classify_by_author.py
```

## 项目结构

```
WN_playwright/
├── config.py              # 配置管理和自动登录
├── get_shelf_info.py       # 书架信息提取
├── search_id.py           # 智能搜索功能
├── comic_downloader.py    # 单个漫画下载
├── batch_download.py      # 批量下载
├── classify_by_author.py  # 按作者分类
├── .env.example          # 环境变量配置示例
├── requirements.txt      # 项目依赖
└── logs/                 # 日志文件目录
```

## 功能详情

### 智能搜索 (search_id.py)
- 支持关键词和标签匹配
- 智能相似度匹配
- 交互式搜索体验
- 搜索结果导出为JSON

### 自动下载系统
- 自动Cookie管理
- 断点续传支持
- 多重错误处理和重试
- 详细下载日志

### 分类管理
- 按作者自动分类已下载内容
- 支持重复文件检测
- 灵活的分类规则

## 注意事项

- ✅ 账号信息通过环境变量安全管理
- ✅ 自动Cookie生成和验证
- ✅ API 域名：自动跟随跳转解析，可用 `WNACG_API_DOMAIN` 环境变量覆盖
- ⚠️ 请适当控制请求频率避免风控
- 📝 详细日志保存在 `logs/` 目录

## 更新日志

- **v2.0** - 环境变量配置，代码重构和优化
- **v1.5** - 智能搜索功能增强
- **v1.0** - 基础爬取和下载功能