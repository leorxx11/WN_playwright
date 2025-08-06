# WN_playwright

一个基于 Python 的 WNACG 漫画网站爬虫工具，用于提取用户书架信息和自动下载漫画。

## 功能特性

- **书架信息提取**: 异步爬取用户书架中的漫画信息
- **单个下载**: 基于 Playwright 的浏览器自动化下载单部漫画
- **批量下载**: 从书架JSON文件批量下载多部漫画，支持断点续传
- **配置管理**: 支持 Cookie 认证和 API 配置
- **日志系统**: 详细的日志记录，支持进度追踪和错误排查
- **数据导出**: JSON 格式导出书架数据

## 项目结构

```
├── config.py              # 配置管理和认证设置
├── get_shelf_info.py      # 书架信息爬取脚本
├── comic_downloader.py    # 漫画下载脚本
├── batch_download.py      # 批量下载脚本
├── requirements.txt       # 依赖包列表
└── CLAUDE.md             # 项目开发指南
```

## 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

## 配置认证

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

## 使用方法

### 提取书架信息

```bash
python get_shelf_info.py
```

书架数据将导出到 `search_results/shelf_{name}_{timestamp}.json`

### 下载漫画

单个下载：
```bash
python comic_downloader.py
```

批量下载：
```bash
python batch_download.py
```

下载的文件将保存到 `url/` 目录

## 输出格式

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

## 注意事项

- 当前 API 域名为 `www.wnacg01.cc`，如有变更请更新 `config.py` 中的 `API_DOMAIN`
- 下载功能包含重试机制和 SSL 警告处理
- 所有敏感文件已在 `.gitignore` 中排除

## 许可证

本项目仅供学习和研究使用，请遵守相关网站的服务条款。