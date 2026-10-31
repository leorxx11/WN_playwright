"""
WNACG 网页操作界面

用法:
    python web.py                 # 默认端口 8787，可用 WNACG_WEB_PORT 覆盖
    python web.py --port 9000 --no-browser
"""
import argparse
import os
import threading
import webbrowser

import uvicorn

DEFAULT_PORT = 8787
HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="WNACG 网页操作界面")
    parser.add_argument('--port', type=int, default=int(os.environ.get('WNACG_WEB_PORT', DEFAULT_PORT)))
    parser.add_argument('--no-browser', action='store_true', help="不自动打开浏览器")
    args = parser.parse_args()

    # 导入时会解析站点域名，放在参数解析之后
    from webapp.app import app

    url = f"http://{HOST}:{args.port}"
    print(f"=== WNACG 网页界面 ===\n打开 {url}  (Ctrl+C 退出)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    # Playwright 需要标准asyncio事件循环
    uvicorn.run(app, host=HOST, port=args.port, loop="asyncio", log_level="warning")


if __name__ == "__main__":
    main()
