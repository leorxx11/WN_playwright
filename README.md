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

## 使用方法

**提取书架信息:**
```bash
python get_shelf_info.py
```

**搜索并保存结果:**
```bash
python search_id.py interactive
```

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
- ✅ API 域名：`www.wnacg01.cc`（如有变更请更新 config.py）
- ⚠️ 请适当控制请求频率避免风控
- 📝 详细日志保存在 `logs/` 目录

## 更新日志

- **v2.0** - 环境变量配置，代码重构和优化
- **v1.5** - 智能搜索功能增强
- **v1.0** - 基础爬取和下载功能