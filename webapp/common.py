"""网页后端共用的路径"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_DIR = os.path.join(BASE_DIR, "search_results")
WEB_DIR = os.path.join(BASE_DIR, "web")
