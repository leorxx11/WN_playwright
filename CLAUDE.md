# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based WNACG (Chinese manga site) scraper that extracts user shelf information and comic metadata, with automated download capabilities. The project consists of three main components:

- **Shelf scraper**: Extracts comic information from user's organized shelves/bookmarks
- **Comic downloader**: Automated browser-based downloading with Playwright
- **Configuration management**: Handles authentication, API endpoints, and request parameters

## Architecture

### Core Files
- `config.py`: Central configuration management with Cookie authentication, API domains, and request settings
- `get_shelf_info.py`: Async shelf scraping with BeautifulSoup HTML parsing and aiohttp for HTTP requests
- `download_comic.py`: Playwright-based automated comic downloading with SSL warning handling and retry logic
- `需求.md`: Chinese documentation explaining shelf extraction logic and browser automation requirements

### Key Components
- **Authentication**: Cookie-based auth with automatic login fallback
- **Web scraping**: Async HTTP client with BeautifulSoup for HTML parsing  
- **Browser automation**: Playwright for downloading with SSL warning handling and retry mechanisms
- **Data structures**: Dataclasses for Shelf, ComicInFavorite, and GetFavoriteResult
- **File I/O**: JSON export to `search_results/` directory, ZIP downloads to `url/` directory

## Common Commands

Since this is a simple Python project without package management files, run scripts directly:

```bash
# Run shelf information extraction
python get_shelf_info.py

# Download comics (requires comic ID)
python download_comic.py

# Test configuration
python config.py
```

## Development Notes

### Authentication Setup
Configure credentials in `config.py`:
- Set `LOGIN_CONFIG` with username/password, or
- Set `WNACG_COOKIE` with a valid session cookie, or  
- Use environment variables `WNACG_USERNAME`, `WNACG_PASSWORD`, `WNACG_COOKIE`

### API Domain
Current domain is `www.wnacg01.cc` but may change - update `API_DOMAIN` in config.py if needed.

### Output Format
Shelf data exports to `search_results/shelf_{name}_{timestamp}.json` with structure:
```json
{
  "comics": [...],
  "total_comics": int,
  "shelf_metadata": {
    "shelf_id": int,
    "shelf_name": str,
    "export_time": "ISO timestamp",
    "source": "shelf_info"
  }
}
```

### Download Configuration
Comic downloads are optimized with:
- **Long timeouts**: 2-minute page timeout, 10-minute download timeout for slow networks
- **No auto-extraction**: ZIP files remain compressed after download
- **No confirmations**: Downloads proceed automatically without user prompts
- **Retry mechanism**: Failed downloads retry up to 3 times with 5-second delays
- **SSL handling**: Automatically bypasses certificate warnings

Downloads are stored in the `url/` directory organized by comic title.

### Dependencies
Install required packages:
```bash
pip install aiohttp beautifulsoup4 requests playwright
playwright install chromium
```