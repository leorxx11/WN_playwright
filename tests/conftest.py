import os
import sys

# 固定域名，避免导入config时去探测站点
os.environ.setdefault('WNACG_API_DOMAIN', 'example.test')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
