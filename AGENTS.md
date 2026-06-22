# Repository Guidelines

## Project Structure & Module Organization
- `config.py`: authentication, cookie management (`cookie.json`).
- `comic_downloader.py`, `batch_download.py`: single/bulk downloads.
- `get_shelf_info.py`: bookshelf metadata export.
- `search_id.py`: keyword/tag search (interactive mode supported).
- `name.csv`: author list used by `classify_by_author.py`.
- `class/`: shared helpers; `logs/`: runtime logs; `downloads/`: saved content; `search_results/`: exported results.
- `.playwright_profile/`: persistent Playwright browser profile for download sessions; do not commit it.
- `.env.example`: environment template; do not commit `.env`, `cookie.json`, or browser profile data.

## Build, Test, and Development Commands
- Environment setup:
  ```bash
  pip install -r requirements.txt
  playwright install chromium
  cp .env.example .env  # then edit creds
  ```
- Auth/cookie bootstrap: `python config.py`
- Run tools:
  ```bash
  python get_shelf_info.py
  python search_id.py interactive
  python comic_downloader.py
  python batch_download.py
  python classify_by_author.py
  ```
- `comic_downloader.py` and `batch_download.py` share `.playwright_profile/`; if Cloudflare prompts appear, solve them manually in the opened Playwright browser and keep reusing that profile.

## Coding Style & Naming Conventions
- Python, 4-space indent, PEP 8; use type hints for new/changed functions.
- Files/functions: `snake_case`; classes: `CapWords`; constants: `UPPER_SNAKE_CASE`.
- Prefer `logging` over `print`; keep logs under `logs/` and avoid secrets.
- No enforced formatter in-repo; if used locally, prefer Black/isort and avoid unrelated reformatting.

## Testing Guidelines
- No formal suite yet; prefer `pytest` for new tests.
- Place tests in `tests/`, name `test_*.py`; isolate I/O and mock network/Playwright.
- Suggested commands:
  ```bash
  pytest -q
  ```
- Aim to cover: URL building, retry/backoff, parsing, and file write paths.

## Commit & Pull Request Guidelines
- Follow Conventional Commits where possible: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`.
- Write imperative, concise subjects (≤72 chars). Example: `feat: optimize batch downloader retries`.
- PRs should include: purpose, key changes, how to run/verify, logs or screenshots (if CLI output), and linked issues.
- Before opening a PR: run the scripts you touched, update README when behavior changes, and ensure `.env`/cookies aren’t tracked.

## Security & Configuration Tips
- Store credentials in `.env`; never hardcode or commit secrets.
- Regenerate cookies via `python config.py` if auth fails.
- Keep `.playwright_profile/` local; it may contain login/session and Cloudflare verification state.
- Respect target site rate limits; tune concurrency responsibly to avoid rate limiting.

## Classification Notes
- `classify_by_author.py` matches zip filenames against `name.csv`; filenames with `[author]` or `(event) [author]` prefixes classify best.
- When filenames have multiple leading bracket blocks such as `[group][author]`, prefer the block that matches `name.csv`.
- Files without an author prefix should be treated as unclassified and moved to `class/other` after preview confirmation.
