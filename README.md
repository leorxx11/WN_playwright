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
页面按「找漫画 → 下载 → 整理」排列，顶栏显示登录状态和下载进度，导航上的数字是等待下载的部数和待整理的文件数：

- **找漫画**：左侧选来源，右侧是同一个勾选列表，勾选后「下载选中」加入下载队列。
  - **搜索**：关键词或标签（可设最多翻几页，搜索中可取消）。搜完可以「追更这个搜索」。
  - **追更**：保存的搜索，记住上次的结果。点「刷新」重新搜索，左侧显示还有几部没下载。每个追更可以设状态：追更中 / 暂停 / 已完结，「全部刷新」只依次刷新追更中的，暂停和已完结的排在后面、保留结果，也能手动刷新；结果里出现「完結」时会提示标记为已完结。可以设「整理到 class/…」，以后在「整理」页这些漫画会默认放进这个文件夹。第一次打开时会把 `search_results/` 里旧的搜索导出（`search_*.json`）导入为追更（原文件保留，旧导出没记录搜索方式，按关键词导入，可在页面上改成标签）。追更保存在 `follows.json`。
  - **书架**：读取收藏的书架，点开读取全部漫画。
  - 列表支持点行切换、按住拖动连续切换、Shift+点击选一段，关键词/话数筛选、隐藏已下载、只选未下载，快捷键 `j`/`k`/空格/`a`/`i`/`u`。标题以 `[作者]` 开头的漫画有「搜作者」，点了直接搜这个作者。下载成功的漫画 ID 记录在 `download_history.json`，用于标记已下载。
- **下载**：下载队列。下载进行中也能继续追加，同一次浏览器会话里接着下；每部显示从哪里加入的（如「追更：玩轉學姊」）。可以暂停/继续、重试失败的、移除等待中的、清除已完成的，也能粘贴漫画 ID 或 `photos-index-aid-123.html` 网址直接加入。队列保存在 `download_queue.json`，服务重启后还在（不会自动开始）。下载结束后如果有待整理的文件会提示去整理。
  - **下载额度**：站点限制每个 IP 24 小时内只能下载 100 个文件。页面按下载记录显示近 24 小时用了多少、还剩多少（同一 IP 在别处的下载不计入，只是估算），加入队列超出剩余额度时会提醒。站点提示额度用完时队列自动暂停，当前和后面的漫画保持等待（不算失败），额度恢复后点「开始下载」继续。命令行 `batch_download.py` 遇到同样提示也会停下。
- **整理**：预览 `downloads/` 里的 zip 会归到 `class/` 的哪个文件夹：设置了文件夹的追更里的漫画放进那个文件夹，其次匹配 `name.csv` 的已知作者、≥2 本的新作者（可勾选加入 `name.csv`），其余归入 `other`（没有作者前缀的按作品名分组，可一键改用作品名做文件夹）。每组可取消、改文件夹名、展开后逐个取消文件，确认后才移动；目标已存在的文件不会覆盖。下载进行中不能整理。
- **账号**：查看用户名、域名、cookie 生成时间，检查登录状态，一键重新登录（正在下载时会等下载结束再登录）。

cookie 过期时搜索、追更和书架会提示去「账号」页重新登录。网页下载时不要同时运行命令行下载脚本（共用 `.playwright_profile/`）。下面的命令行脚本仍然可用，`batch_download.py` 仍可读取 `search_results/` 里的 JSON。

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