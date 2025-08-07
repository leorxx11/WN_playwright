# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based WNACG (Chinese manga site) scraper that extracts user shelf information and comic metadata, with automated download capabilities. The project consists of five main components:

- **Shelf scraper**: Extracts comic information from user's organized shelves/bookmarks
- **Comic downloader**: Automated browser-based downloading with Playwright for single comics
- **Batch downloader**: Automated batch downloading from shelf JSON files with progress tracking
- **Author classifier**: Organizes and classifies comics by author information from CSV data
- **Configuration management**: Handles authentication, API endpoints, and request parameters

## Architecture

### Core Files
- `config.py`: Central configuration management with Cookie authentication, API domains, and request settings
- `get_shelf_info.py`: Async shelf scraping with BeautifulSoup HTML parsing and aiohttp for HTTP requests
- `comic_downloader.py`: Playwright-based automated comic downloading with SSL warning handling and retry logic
- `batch_download.py`: Batch comic downloading from shelf JSON files with progress tracking and logging
- `classify_by_author.py`: Author-based classification and organization of comic data from CSV files
- `需求.md`: Chinese documentation explaining shelf extraction logic and browser automation requirements
- `name.csv`: Author name data for classification purposes

### Key Components
- **Authentication**: Cookie-based auth with automatic login fallback
- **Web scraping**: Async HTTP client with BeautifulSoup for HTML parsing  
- **Browser automation**: Playwright for downloading with SSL warning handling and retry mechanisms
- **Batch processing**: Automated batch downloads with resume capability and progress tracking
- **Logging system**: Comprehensive logging for both single and batch downloads with separate log files
- **Data structures**: Dataclasses for Shelf, ComicInFavorite, and GetFavoriteResult
- **File I/O**: JSON export to `search_results/` directory, ZIP downloads to `url/` directory

## Common Commands

Since this is a simple Python project without package management files, run scripts directly:

```bash
# Run shelf information extraction
python get_shelf_info.py

# Download single comic (requires comic ID)
python comic_downloader.py

# Batch download comics from shelf JSON
python batch_download.py

# Classify comics by author from CSV data
python classify_by_author.py

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
- **Logging system**: Comprehensive logging for both single downloads and batch processing
- **Progress tracking**: Real-time progress display and detailed logging for batch downloads
- **Resume capability**: Batch downloads can skip already downloaded comics

Downloads are stored in the `url/` directory organized by comic title.

### Logging
- Single downloads: Logs saved to `logs/comic_download_{timestamp}.log`
- Batch downloads: Logs saved to `logs/batch_download_{timestamp}.log`
- Console output shows minimal progress information
- Detailed information including errors and debug info are written to log files

### Dependencies
Install required packages:
```bash
pip install aiohttp beautifulsoup4 requests playwright
playwright install chromium
```