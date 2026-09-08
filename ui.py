# ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import keyring
import os
import sys
import json
import shutil
import requests
from config import LIGHT_THEME, DARK_THEME, CONFIG_FILE, HEADERS
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
            self.download_dir = self.config.get("download_dir", r"E:\音乐")
        else:
            self.config = {}
            self.download_dir = r"E:\音乐"
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
            root=self.root,  # 传入主线程
            lyrics_lang=self.lyrics_lang
        )

        # 新增：简繁转换开关变量（默认开启转换）
        self.convert_var = tk.BooleanVar(value=True)
        self.downloader.convert_to_simplified = self.convert_var.get()
        self.convert_var.trace_add('write', self._on_convert_changed)

        self.apply_theme()
        if self.try_auto_login():
            self.show_main_frame()
        else:
            self.show_login_frame()

    # ---------- 新增：简繁转换变化回调 ----------
    def _on_convert_changed(self, *args):
        self.downloader.convert_to_simplified = self.convert_var.get()

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

    # ---------- Cookie 管理 ----------
    def save_cookies(self):
        cookies_json = json.dumps(self.session.cookies.get_dict(), ensure_ascii=False)
        keyring.set_password("BiliDownloader", "cookies", cookies_json)

    def load_cookies(self):
        try:
            cookies_json = keyring.get_password("BiliDownloader", "cookies")
            if cookies_json:
                cookies = json.loads(cookies_json)
                self.session.cookies.update(cookies)
                return True
        except:
            pass
        return False

    def clear_cookies(self):
        try:
            keyring.delete_password("BiliDownloader", "cookies")
        except:
            pass
        self.session.cookies.clear()

    def try_auto_login(self):
        if not self.load_cookies():
            return False
        try:
            nav_resp = self.session.get('https://api.bilibili.com/x/web-interface/nav')
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