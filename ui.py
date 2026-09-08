# ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
import json
import shutil
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import LIGHT_THEME, DARK_THEME, CONFIG_FILE, COOKIES_FILE, HEADERS, DEFAULT_DOWNLOAD_DIR
from bili_api import BiliAPI
from downloader import Downloader
from frames.login_frame import LoginFrame
from frames.main_frame import MainFrame


class BiliApp:
    def __init__(self, root):
        self.root = root
        self.root.title("B站收藏夹管理器")
        self.root.geometry("1600x800")
        self.is_dark = False
        self.theme = LIGHT_THEME.copy()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # 配置重试适配器（最多重试3次，退避因子0.5，对连接错误和5xx状态码重试）
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.api = BiliAPI(self.session)
        self.uid = None
        self.all_data = {}
        self.user_info = None
        self.cancel_download = False
        self.download_status_var = tk.StringVar(value="就绪")
        self.lyrics_lang = tk.StringVar(value="simplified")  # 默认简体

        # 路径配置读取
        self.config_file = CONFIG_FILE
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.download_dir = self.config.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        else:
            self.config = {}
            self.download_dir = DEFAULT_DOWNLOAD_DIR
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        # 检测 ffmpeg
        self.ffmpeg_path = None
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(base_dir, 'ffmpeg.exe')) and os.path.exists(
                os.path.join(base_dir, 'ffprobe.exe')):
            self.ffmpeg_path = base_dir
        else:
            ffmpeg_exe = shutil.which('ffmpeg')
            if ffmpeg_exe:
                self.ffmpeg_path = os.path.dirname(ffmpeg_exe)
        if not self.ffmpeg_path:
            self.root.after(500, lambda: messagebox.showwarning(
                "缺少 ffmpeg",
                "未找到 ffmpeg 和 ffprobe，下载音频时将无法转换为 MP3。"
            ))

        # 实例化下载器
        self.downloader = Downloader(
            download_dir=self.download_dir,
            ffmpeg_path=self.ffmpeg_path,
            session=self.session,
            progress_callback=self.update_download_status,
            root=self.root,
            lyrics_lang=self.lyrics_lang
        )

        # 绑定窗口关闭事件（防止线程泄漏）
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.apply_theme()
        if self.try_auto_login():
            self.show_main_frame()
        else:
            self.show_login_frame()

    # ---------- 窗口关闭处理 ----------
    def on_close(self):
        """窗口关闭时清理所有待处理的重复文件查询事件，避免线程泄漏"""
        import log_manager
        import queue as q
        while True:
            try:
                msg_type, *data = log_manager.ui_queue.get_nowait()
                if msg_type == "QUERY_DUP":
                    result_box = data[3]
                    event = data[4]
                    result_box[0] = None
                    event.set()
            except q.Empty:
                break
        self.root.destroy()

    # ---------- 主题管理 ----------
    def apply_theme(self):
        self.theme = DARK_THEME.copy() if self.is_dark else LIGHT_THEME.copy()
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except:
            pass
        style.configure('.', background=self.theme['bg'], foreground=self.theme['fg'],
                        font=(self.theme['font_family'], self.theme['font_size']))
        style.configure('TLabel', background=self.theme['bg'])
        style.configure('Header.TLabel', font=(self.theme['font_family'], self.theme['heading_font_size'], 'bold'))
        style.configure('TButton', background=self.theme['primary'], foreground='white', borderwidth=0,
                        focusthickness=3, focuscolor=self.theme['primary_dark'])
        style.map('TButton',
                  background=[('active', self.theme['primary_dark']), ('pressed', self.theme['primary_dark'])])
        style.configure('TListbox', background=self.theme['listbox_bg'], foreground=self.theme['fg'])
        style.configure('Treeview', background=self.theme['tree_bg'], foreground=self.theme['fg'],
                        fieldbackground=self.theme['tree_bg'])
        style.configure('Treeview.Heading', background=self.theme['tree_heading_bg'], foreground=self.theme['fg'])
        style.map('Treeview', background=[('selected', self.theme['tree_selected_bg'])])
        style.configure('TProgressbar', background=self.theme['primary'], troughcolor=self.theme['bg'])
        self.root.configure(bg=self.theme['bg'])

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.apply_theme()
        if hasattr(self, 'current_frame') and hasattr(self.current_frame, 'on_theme_changed'):
            self.current_frame.on_theme_changed()

    # ---------- Cookie 管理（使用 COOKIES_FILE） ----------
    def save_cookies(self):
        """将 session cookies 保存到 COOKIES_FILE"""
        cookies_dict = self.session.cookies.get_dict()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies_dict, f, ensure_ascii=False, indent=2)

    def load_cookies(self):
        """从 COOKIES_FILE 加载 cookies"""
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies_dict = json.load(f)
            self.session.cookies.update(cookies_dict)
            return True
        except Exception:
            return False

    def clear_cookies(self):
        """清除 cookies 文件并清空 session"""
        if os.path.exists(COOKIES_FILE):
            try:
                os.remove(COOKIES_FILE)
            except OSError:
                pass
        self.session.cookies.clear()

    def try_auto_login(self):
        if not self.load_cookies():
            return False
        try:
            nav_resp = self.session.get('https://api.bilibili.com/x/web-interface/nav', timeout=10)
            nav_data = nav_resp.json()
            if nav_data['code'] == 0 and nav_data['data'].get('isLogin'):
                self.uid = nav_data['data']['mid']
                return True
        except:
            pass
        return False

    # ---------- 界面切换 ----------
    def show_login_frame(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.current_frame = LoginFrame(self)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_main_frame(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.current_frame = MainFrame(self)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    # ---------- 状态回调 ----------
    def update_download_status(self, text):
        self.root.after(0, lambda: self.download_status_var.set(text))

    # ---------- 公共下载方法（供子 frame 调用） ----------
    def start_download(self, bvid, audio_only, title):
        import threading
        def download_thread():
            try:
                self.downloader.download_video(bvid, audio_only)
                self.root.after(0, lambda: self.download_status_var.set(f"下载完成: {title}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("下载失败", f"{title}: {str(e)}"))

        threading.Thread(target=download_thread, daemon=True).start()


if __name__ == '__main__':
    root = tk.Tk()
    app = BiliApp(root)
    root.mainloop()