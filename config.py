import os

# 获取系统标准存放配置的路径
appdata_dir = os.getenv('APPDATA', os.path.expanduser("~"))
APP_DIR = os.path.join(appdata_dir, "BiliMusicDownloader")

# 确保目录存在（exist_ok=True 避免并发/已存在文件问题）
os.makedirs(APP_DIR, exist_ok=True)

COOKIES_FILE = os.path.join(APP_DIR, "bili_cookies.json")
CONFIG_FILE = os.path.join(APP_DIR, "bili_config.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
}

LIGHT_THEME = {
    "bg": "#f5f6fa", "fg": "#2c3e50", "primary": "#3498db",
    "primary_dark": "#2980b9", "success": "#27ae60", "warning": "#f39c12",
    "danger": "#e74c3c", "font_family": "Microsoft YaHei", "font_size": 10,
    "heading_font_size": 12, "listbox_bg": "#ffffff", "tree_bg": "#ffffff",
    "tree_heading_bg": "#ecf0f1", "tree_selected_bg": "#d6eaf8",
}

DARK_THEME = {
    "bg": "#2b2b2b", "fg": "#ffffff", "primary": "#ff6b6b",
    "primary_dark": "#ee5253", "success": "#1dd1a1", "warning": "#feca57",
    "danger": "#ff6b6b", "font_family": "Microsoft YaHei", "font_size": 10,
    "heading_font_size": 12, "listbox_bg": "#3c3f41", "tree_bg": "#3c3f41",
    "tree_heading_bg": "#4e5254", "tree_selected_bg": "#555555",
}