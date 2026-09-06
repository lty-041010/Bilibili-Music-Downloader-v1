import requests
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import qrcode
from qrcode.image.pil import PilImage
import io
import os
import shutil
import tempfile
import re
import yt_dlp

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
}

LIGHT_THEME = {
    "bg": "#f5f6fa",
    "fg": "#2c3e50",
    "primary": "#3498db",
    "primary_dark": "#2980b9",
    "success": "#27ae60",
    "warning": "#f39c12",
    "danger": "#e74c3c",
    "font_family": "Microsoft YaHei",
    "font_size": 10,
    "heading_font_size": 12,
    "listbox_bg": "#ffffff",
    "tree_bg": "#ffffff",
    "tree_heading_bg": "#ecf0f1",
    "tree_selected_bg": "#d6eaf8",
}

DARK_THEME = {
    "bg": "#2b2b2b",
    "fg": "#ffffff",
    "primary": "#ff6b6b",
    "primary_dark": "#ee5253",
    "success": "#1dd1a1",
    "warning": "#feca57",
    "danger": "#ff6b6b",
    "font_family": "Microsoft YaHei",
    "font_size": 10,
    "heading_font_size": 12,
    "listbox_bg": "#3c3f41",
    "tree_bg": "#3c3f41",
    "tree_heading_bg": "#4e5254",
    "tree_selected_bg": "#555555",
}

COOKIES_FILE = "bili_cookies.json"
DOWNLOAD_DIR = "downloads"

class BiliApp:
    def __init__(self, root):
        self.root = root
        self.root.title("B站收藏夹管理器")
        self.root.geometry("1200x800")
        self.is_dark = False
        self.theme = LIGHT_THEME.copy()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.uid = None
        self.all_data = {}
        self.qrcode_key = None
        self.login_thread = None
        self.stop_login_poll = False
        self.user_info = None
        self.download_status_var = tk.StringVar()
        self.download_status_var.set("就绪")
        self.cancel_download = False
        self.search_scope_var = tk.StringVar(value="B站搜索")
        self.apply_theme()

        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)

        # 检测 ffmpeg
        self.ffmpeg_path = None
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(base_dir, 'ffmpeg.exe')) and os.path.exists(os.path.join(base_dir, 'ffprobe.exe')):
            self.ffmpeg_path = base_dir
        else:
            ffmpeg_exe = shutil.which('ffmpeg')
            if ffmpeg_exe:
                self.ffmpeg_path = os.path.dirname(ffmpeg_exe)
        if not self.ffmpeg_path:
            self.root.after(500, lambda: messagebox.showwarning(
                "缺少 ffmpeg",
                "未找到 ffmpeg 和 ffprobe，下载音频时将无法转换为 MP3。\n请将 ffmpeg.exe 和 ffprobe.exe 放在程序目录或加入系统 PATH。"
            ))

        if self.try_auto_login():
            self.load_favorites_ui()
        else:
            self.show_login_frame()

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
        style.map('TButton', background=[('active', self.theme['primary_dark']), ('pressed', self.theme['primary_dark'])])
        style.configure('TListbox', background=self.theme['listbox_bg'], foreground=self.theme['fg'],
                        borderwidth=1, relief='solid')
        style.configure('Treeview', background=self.theme['tree_bg'], foreground=self.theme['fg'],
                        fieldbackground=self.theme['tree_bg'], borderwidth=0)
        style.configure('Treeview.Heading', background=self.theme['tree_heading_bg'], foreground=self.theme['fg'],
                        font=(self.theme['font_family'], self.theme['font_size'], 'bold'))
        style.map('Treeview', background=[('selected', self.theme['tree_selected_bg'])],
                  foreground=[('selected', self.theme['fg'])])
        style.configure('TProgressbar', background=self.theme['primary'], troughcolor=self.theme['bg'], borderwidth=0)
        self.root.configure(bg=self.theme['bg'])
        if hasattr(self, 'folder_listbox'):
            self.folder_listbox.config(bg=self.theme['listbox_bg'], fg=self.theme['fg'],
                                       selectbackground=self.theme['tree_selected_bg'])

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.apply_theme()

    # ---------- Cookie 持久化 ----------
    def save_cookies(self):
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.session.cookies.get_dict(), f, ensure_ascii=False, indent=2)

    def load_cookies(self):
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            self.session.cookies.update(cookies)
            return True
        except:
            return False

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

    def clear_cookies(self):
        try:
            if os.path.exists(COOKIES_FILE):
                os.remove(COOKIES_FILE)
        except:
            pass
        self.session.cookies.clear()

    # ---------- 登录界面 ----------
    def show_login_frame(self):
        if hasattr(self, 'main_frame'):
            self.main_frame.destroy()
        self.login_frame = ttk.Frame(self.root, padding=20)
        self.login_frame.pack(fill=tk.BOTH, expand=True)
        self.status_label = ttk.Label(self.login_frame, text="正在生成二维码...", style='Header.TLabel')
        self.status_label.pack(pady=10)
        self.qr_label = ttk.Label(self.login_frame)
        self.qr_label.pack(pady=10)
        btn_frame = ttk.Frame(self.login_frame)
        btn_frame.pack(pady=10)
        self.refresh_qr_btn = ttk.Button(btn_frame, text="刷新二维码", command=self.refresh_qrcode, state=tk.DISABLED)
        self.refresh_qr_btn.pack(side=tk.LEFT, padx=5)
        self.theme_btn_login = ttk.Button(btn_frame, text="切换主题", command=self.toggle_theme)
        self.theme_btn_login.pack(side=tk.LEFT, padx=5)
        self.generate_qrcode()

    def generate_qrcode(self):
        try:
            url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
            resp = self.session.get(url)
            data = resp.json()
            if data['code'] != 0:
                raise Exception(f"获取二维码失败: {data['message']}")
            self.qrcode_key = data['data']['qrcode_key']
            qr_url = data['data']['url']
            qr_img = qrcode.make(qr_url, image_factory=PilImage, box_size=6, border=2)
            img_bytes = io.BytesIO()
            qr_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            pil_image = Image.open(img_bytes)
            self.tk_image = ImageTk.PhotoImage(pil_image)
            self.qr_label.config(image=self.tk_image)
            self.status_label.config(text="请使用B站手机客户端扫描二维码")
            self.refresh_qr_btn.config(state=tk.NORMAL)
            self.stop_login_poll = False
            self.login_thread = threading.Thread(target=self.poll_login, daemon=True)
            self.login_thread.start()
        except Exception as e:
            self.status_label.config(text=f"错误: {e}")
            messagebox.showerror("错误", str(e))

    def refresh_qrcode(self):
        self.stop_login_poll = True
        if self.login_thread and self.login_thread.is_alive():
            self.login_thread.join(timeout=1)
        self.generate_qrcode()

    def poll_login(self):
        url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
        params = {'qrcode_key': self.qrcode_key}
        last_status = None
        while not self.stop_login_poll:
            try:
                resp = self.session.get(url, params=params)
                data = resp.json()
                if data['code'] != 0:
                    status = data['code']
                    if status != last_status:
                        if status == 86038:
                            self.update_status("二维码已失效，请刷新")
                            self.refresh_qr_btn.config(state=tk.NORMAL)
                            break
                        elif status == 86090:
                            self.update_status("二维码已扫描，等待确认...")
                        elif status == 86101:
                            self.update_status("未扫描，请使用B站客户端扫码")
                        else:
                            self.update_status(f"状态码: {status} - {data['message']}")
                        last_status = status
                else:
                    self.verify_and_login()
                    break
                time.sleep(2)
            except Exception as e:
                self.update_status(f"轮询异常: {e}")
                time.sleep(2)

    def verify_and_login(self):
        uid = self.session.cookies.get('DedeUserID')
        if not uid:
            try:
                nav_resp = self.session.get('https://api.bilibili.com/x/web-interface/nav')
                nav_data = nav_resp.json()
                if nav_data['code'] == 0 and nav_data['data'].get('isLogin'):
                    uid = nav_data['data']['mid']
            except:
                pass
        if uid:
            self.uid = uid
            self.save_cookies()
            self.update_status(f"登录成功！UID: {uid}")
            self.root.after(500, self.load_favorites_ui)
        else:
            self.update_status("登录确认中，请稍候...")
            self.poll_login()

    def update_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    # ---------- 收藏夹数据界面 ----------
    def load_favorites_ui(self):
        if hasattr(self, 'login_frame'):
            self.login_frame.destroy()
        self.main_frame = ttk.Frame(self.root, padding=5)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.grid_rowconfigure(2, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # 用户信息栏
        user_frame = ttk.Frame(self.main_frame, padding=5)
        user_frame.grid(row=0, column=0, sticky='ew')
        self.user_avatar_label = ttk.Label(user_frame)
        self.user_avatar_label.pack(side=tk.LEFT, padx=5)
        self.user_name_label = ttk.Label(user_frame, text="加载中...", style='Header.TLabel')
        self.user_name_label.pack(side=tk.LEFT, padx=5)

        # 搜索栏（关键词/BV号/链接 + 搜索范围选择 + 搜索按钮 + 下载MP4/MP3按钮）
        search_frame = ttk.Frame(self.main_frame, padding=5)
        search_frame.grid(row=1, column=0, sticky='ew')
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame, width=35)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        # 搜索范围下拉框
        search_scope_combo = ttk.Combobox(search_frame, textvariable=self.search_scope_var,
                                          values=["B站搜索", "收藏夹搜索"], width=10, state="readonly")
        search_scope_combo.pack(side=tk.LEFT, padx=2)
        self.search_btn = ttk.Button(search_frame, text="搜索/解析", command=self.search_video)
        self.search_btn.pack(side=tk.LEFT, padx=5)
        self.download_mp4_btn_s = ttk.Button(search_frame, text="下载MP4", command=lambda: self.download_input(False))
        self.download_mp4_btn_s.pack(side=tk.LEFT, padx=2)
        self.download_mp3_btn_s = ttk.Button(search_frame, text="下载MP3", command=lambda: self.download_input(True))
        self.download_mp3_btn_s.pack(side=tk.LEFT, padx=2)

        # 主体：左右分栏
        body_frame = ttk.Frame(self.main_frame, padding=5)
        body_frame.grid(row=2, column=0, sticky='nsew')
        body_frame.grid_rowconfigure(0, weight=1)
        body_frame.grid_columnconfigure(1, weight=1)

        left_frame = ttk.Frame(body_frame, padding=5)
        left_frame.grid(row=0, column=0, sticky='ns')
        ttk.Label(left_frame, text="收藏夹列表", style='Header.TLabel').pack()
        self.folder_listbox = tk.Listbox(left_frame, width=30, height=25,
                                         bg=self.theme['listbox_bg'], fg=self.theme['fg'],
                                         selectbackground=self.theme['tree_selected_bg'],
                                         font=(self.theme['font_family'], self.theme['font_size']))
        self.folder_listbox.pack(fill=tk.Y, expand=True)

        right_frame = ttk.Frame(body_frame, padding=5)
        right_frame.grid(row=0, column=1, sticky='nsew')
        columns = ('index', 'title', 'up', 'duration', 'favorite_time', 'bvid')
        self.tree = ttk.Treeview(right_frame, columns=columns, show='headings', height=25, selectmode='extended')
        self.tree.heading('index', text='序号')
        self.tree.heading('title', text='标题')
        self.tree.heading('up', text='UP主')
        self.tree.heading('duration', text='时长')
        self.tree.heading('favorite_time', text='收藏时间')
        self.tree.heading('bvid', text='BV号')
        self.tree.column('index', width=50, anchor='center')
        self.tree.column('title', width=300)
        self.tree.column('up', width=100)
        self.tree.column('duration', width=80)
        self.tree.column('favorite_time', width=140)
        self.tree.column('bvid', width=120)
        scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # 底部按钮栏
        bottom_frame = ttk.Frame(self.main_frame, padding=5)
        bottom_frame.grid(row=3, column=0, sticky='ew')
        self.export_btn = ttk.Button(bottom_frame, text="导出 JSON", command=self.save_json)
        self.export_btn.pack(side=tk.RIGHT, padx=5)
        self.refresh_btn = ttk.Button(bottom_frame, text="刷新数据", command=self.start_refresh_data)
        self.refresh_btn.pack(side=tk.RIGHT, padx=5)
        self.theme_btn = ttk.Button(bottom_frame, text="切换主题", command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=5)
        self.switch_account_btn = ttk.Button(bottom_frame, text="切换账号", command=self.switch_account)
        self.switch_account_btn.pack(side=tk.RIGHT, padx=5)
        self.download_mp4_btn = ttk.Button(bottom_frame, text="下载MP4", command=lambda: self.download_selected(False))
        self.download_mp4_btn.pack(side=tk.RIGHT, padx=5)
        self.download_mp3_btn = ttk.Button(bottom_frame, text="下载MP3", command=lambda: self.download_selected(True))
        self.download_mp3_btn.pack(side=tk.RIGHT, padx=5)
        self.cancel_btn = ttk.Button(bottom_frame, text="取消下载", command=self.cancel_download_task)
        self.cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 状态栏
        status_frame = ttk.Frame(self.main_frame, padding=2)
        status_frame.grid(row=4, column=0, sticky='ew')
        ttk.Label(status_frame, text="下载状态:").pack(side=tk.LEFT, padx=5)
        ttk.Label(status_frame, textvariable=self.download_status_var).pack(side=tk.LEFT, padx=5)

        # 加载提示层
        self.loading_overlay = ttk.Frame(self.main_frame)
        self.loading_overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.loading_label = ttk.Label(self.loading_overlay, text="正在获取收藏夹数据，请稍候...", style='Header.TLabel')
        self.loading_label.pack(pady=10)
        self.loading_progress = ttk.Progressbar(self.loading_overlay, mode='indeterminate', length=300)
        self.loading_progress.pack(pady=5)

        self.folder_listbox.bind('<<ListboxSelect>>', self.on_folder_select)
        self.load_user_info()
        self.start_refresh_data()

    # ---------- 用户信息加载（略，同原代码） ----------
    def load_user_info(self):
        def fetch():
            try:
                info = self.get_user_info()
                if info:
                    self.user_info = info
                    self.root.after(0, self.update_user_info_ui)
            except Exception as e:
                print(f"获取用户信息失败: {e}")
        threading.Thread(target=fetch, daemon=True).start()

    def get_user_info(self):
        resp = self.session.get('https://api.bilibili.com/x/web-interface/nav')
        data = resp.json()
        if data['code'] == 0 and data['data'].get('isLogin'):
            return data['data']
        return None

    def update_user_info_ui(self):
        if not self.user_info:
            return
        uname = self.user_info.get('uname', '未知')
        face_url = self.user_info.get('face', '')
        self.user_name_label.config(text=f"{uname} (UID: {self.uid})")
        if face_url:
            threading.Thread(target=self.download_avatar, args=(face_url,), daemon=True).start()

    def download_avatar(self, url):
        try:
            resp = requests.get(url, headers=HEADERS)
            if resp.status_code == 200:
                img_data = resp.content
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((40, 40), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.root.after(0, lambda: self.user_avatar_label.config(image=photo))
                self.user_avatar_label.image = photo
        except Exception as e:
            print(f"头像下载失败: {e}")

    def switch_account(self):
        if messagebox.askyesno("确认", "确定要切换账号吗？将清除当前登录状态。"):
            self.clear_cookies()
            self.uid = None
            self.all_data.clear()
            if hasattr(self, 'main_frame'):
                self.main_frame.destroy()
            self.show_login_frame()

    # ---------- 收藏夹数据获取（同原代码） ----------
    def start_refresh_data(self):
        self.refresh_btn.config(state=tk.DISABLED)
        self.loading_overlay.lift()
        self.loading_overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.loading_progress.start(10)
        self.fetch_thread = threading.Thread(target=self.fetch_data_thread, daemon=True)
        self.fetch_thread.start()

    def fetch_data_thread(self):
        try:
            self.all_data.clear()
            folders = self.get_all_folders()
            total_folders = len(folders)
            for i, folder in enumerate(folders):
                fid = folder['id']
                title = folder['title']
                media_count = folder['media_count']
                videos = self.get_folder_videos(fid)
                self.all_data[title] = {'folder_id': fid, 'media_count': media_count, 'videos': videos}
                progress_text = f"正在获取收藏夹 [{i + 1}/{total_folders}]: {title}"
                self.root.after(0, lambda t=progress_text: self.loading_label.config(text=t))
                time.sleep(0.2)
            self.root.after(0, self.on_data_loaded)
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.on_data_error(error_msg))

    def on_data_loaded(self):
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.folder_listbox.delete(0, tk.END)
        for folder_name, folder_data in self.all_data.items():
            display_name = f"{folder_name} ({len(folder_data['videos'])})"
            self.folder_listbox.insert(tk.END, display_name)
        self.refresh_btn.config(state=tk.NORMAL)
        self.root.title(f"B站收藏夹管理器 - UID: {self.uid} (已加载 {len(self.all_data)} 个收藏夹)")

    def on_data_error(self, error_msg):
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.refresh_btn.config(state=tk.NORMAL)
        messagebox.showerror("错误", f"获取数据失败：{error_msg}")

    def get_all_folders(self):
        url = 'https://api.bilibili.com/x/v3/fav/folder/created/list-all'
        params = {'up_mid': self.uid}
        resp = self.session.get(url, params=params)
        data = resp.json()
        if data['code'] != 0:
            raise Exception(f"获取收藏夹列表失败: {data['message']}")
        return data['data']['list']

    def get_folder_videos(self, media_id):
        videos = []
        page = 1
        page_size = 20
        while True:
            url = 'https://api.bilibili.com/x/v3/fav/resource/list'
            params = {'media_id': media_id, 'pn': page, 'ps': page_size, 'keyword': '',
                      'order': 'mtime', 'type': 0, 'tid': 0, 'platform': 'web'}
            resp = self.session.get(url, params=params)
            data = resp.json()
            if data['code'] != 0:
                print(f"获取收藏夹 {media_id} 第 {page} 页失败: {data['message']}")
                break
            medias = data['data']['medias']
            if not medias:
                break
            for item in medias:
                videos.append({
                    'title': item['title'],
                    'bvid': item['bvid'],
                    'url': f"https://www.bilibili.com/video/{item['bvid']}",
                    'up': item['upper']['name'],
                    'duration': item['duration'],
                    'favorite_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item['fav_time']))
                })
            if not data['data']['has_more']:
                break
            page += 1
            time.sleep(0.3)
        return videos

    def on_folder_select(self, event):
        selection = self.folder_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        folder_name = list(self.all_data.keys())[index]
        folder_data = self.all_data[folder_name]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, video in enumerate(folder_data['videos'], start=1):
            self.tree.insert('', tk.END, values=(
                i, video['title'], video['up'], video['duration'], video['favorite_time'], video['bvid']))

    def save_json(self):
        if not self.all_data:
            messagebox.showwarning("警告", "没有数据可保存")
            return
        output_file = f"bili_favorites_{self.uid}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("成功", f"数据已保存到 {output_file}")

    # ---------- 搜索与下载功能（修改部分） ----------
    def extract_bvid(self, text):
        """从文本中提取 BV 号，支持完整链接、短链接、纯 BV 号"""
        # 匹配 BV 号
        match = re.search(r'BV[0-9A-Za-z]+', text)
        if match:
            return match.group(0)
        # 匹配 av 号（旧版）
        match = re.search(r'av(\d+)', text)
        if match:
            return f"av{match.group(1)}"
        return None

    def download_input(self, audio_only):
        """下载搜索框中输入的内容（仅支持 BV 号、av 号或链接）"""
        text = self.search_entry.get().strip()
        if not text:
            messagebox.showinfo("提示", "请输入BV号、av号或视频链接")
            return
        bvid = self.extract_bvid(text)
        if not bvid:
            messagebox.showwarning("警告", "无法从输入内容中识别视频ID")
            return
        self.start_download(bvid, audio_only, bvid)

    def search_video(self):
        """搜索/解析入口，根据输入内容和搜索范围执行相应操作"""
        keyword = self.search_entry.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入关键词、BV号或链接")
            return

        # 尝试提取视频 ID（BV/av）
        video_id = self.extract_bvid(keyword)
        if video_id:
            # 询问格式并直接下载
            if messagebox.askyesno("下载格式", "选择“是”下载MP4，选择“否”下载MP3"):
                audio_only = False
            else:
                audio_only = True
            self.start_download(video_id, audio_only, video_id)
            return

        # 根据搜索范围处理
        scope = self.search_scope_var.get()
        if scope == "收藏夹搜索":
            self.search_local(keyword)
        else:
            self.search_online(keyword)

    def search_local(self, keyword):
        """在已加载的收藏夹中搜索视频"""
        if not self.all_data:
            messagebox.showinfo("提示", "收藏夹数据尚未加载")
            return
        results = []
        for folder_name, folder_data in self.all_data.items():
            for video in folder_data['videos']:
                if keyword.lower() in video['title'].lower() or keyword.lower() in video['up'].lower():
                    results.append(video)
        if not results:
            messagebox.showinfo("结果", "未在收藏夹中找到匹配视频")
            return
        # 弹出结果窗口
        self.show_search_results_window(results, title=f"收藏夹搜索结果: {keyword}")

    def search_online(self, keyword):
        """在线搜索 B 站视频（原有功能）"""
        search_win = tk.Toplevel(self.root)
        search_win.title(f"B站搜索结果: {keyword}")
        search_win.geometry("800x400")
        search_win.transient(self.root)
        columns = ('title', 'up', 'duration', 'bvid')
        result_tree = ttk.Treeview(search_win, columns=columns, show='headings', height=15, selectmode='browse')
        result_tree.heading('title', text='标题')
        result_tree.heading('up', text='UP主')
        result_tree.heading('duration', text='时长')
        result_tree.heading('bvid', text='BV号')
        result_tree.column('title', width=400)
        result_tree.column('up', width=150)
        result_tree.column('duration', width=80)
        result_tree.column('bvid', width=120)
        result_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        # 绑定右键复制菜单
        self.bind_copy_menu(result_tree)

        btn_frame = ttk.Frame(search_win)
        btn_frame.pack(pady=5)
        mp4_btn = ttk.Button(btn_frame, text="下载MP4", command=lambda: self.download_from_search(result_tree, search_win, False))
        mp4_btn.pack(side=tk.LEFT, padx=5)
        mp3_btn = ttk.Button(btn_frame, text="下载MP3", command=lambda: self.download_from_search(result_tree, search_win, True))
        mp3_btn.pack(side=tk.LEFT, padx=5)

        def fetch_results():
            try:
                url = 'https://api.bilibili.com/x/web-interface/search/type'
                params = {'search_type': 'video', 'keyword': keyword, 'page': 1, 'page_size': 20}
                resp = self.session.get(url, params=params)
                data = resp.json()
                if data['code'] != 0:
                    raise Exception(data['message'])
                results = data['data']['result']
                self.root.after(0, lambda: self.display_search_results(result_tree, results))
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("错误", f"搜索失败: {error_msg}"))

        threading.Thread(target=fetch_results, daemon=True).start()

    def show_search_results_window(self, videos, title="搜索结果"):
        """显示本地搜索结果窗口"""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("800x400")
        win.transient(self.root)
        columns = ('title', 'up', 'duration', 'bvid')
        tree = ttk.Treeview(win, columns=columns, show='headings', height=15, selectmode='browse')
        tree.heading('title', text='标题')
        tree.heading('up', text='UP主')
        tree.heading('duration', text='时长')
        tree.heading('bvid', text='BV号')
        tree.column('title', width=400)
        tree.column('up', width=150)
        tree.column('duration', width=80)
        tree.column('bvid', width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.bind_copy_menu(tree)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=5)
        mp4_btn = ttk.Button(btn_frame, text="下载MP4", command=lambda: self.download_from_search(tree, win, False))
        mp4_btn.pack(side=tk.LEFT, padx=5)
        mp3_btn = ttk.Button(btn_frame, text="下载MP3", command=lambda: self.download_from_search(tree, win, True))
        mp3_btn.pack(side=tk.LEFT, padx=5)

        for video in videos:
            duration = video.get('duration', '--')
            if isinstance(duration, int):
                mins, secs = divmod(duration, 60)
                duration = f"{mins:02d}:{secs:02d}"
            tree.insert('', tk.END, values=(video['title'], video['up'], duration, video['bvid']))

    def bind_copy_menu(self, tree):
        """为 Treeview 绑定右键复制菜单"""
        menu = tk.Menu(tree, tearoff=0)
        menu.add_command(label="复制选中行", command=lambda: self.copy_selected_row(tree))
        menu.add_command(label="复制单元格", command=lambda: self.copy_selected_cell(tree))
        tree.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))

    def copy_selected_row(self, tree):
        selection = tree.selection()
        if not selection:
            return
        item = tree.item(selection[0])
        values = item['values']
        text = "\t".join(str(v) for v in values)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_selected_cell(self, tree):
        selection = tree.selection()
        if not selection:
            return
        # 获取点击的列
        col = tree.identify_column(tree.winfo_pointerx() - tree.winfo_rootx())
        if not col:
            return
        col_index = int(col.replace('#', '')) - 1
        item = tree.item(selection[0])
        value = item['values'][col_index]
        self.root.clipboard_clear()
        self.root.clipboard_append(str(value))

    def display_search_results(self, tree, results):
        for item in tree.get_children():
            tree.delete(item)
        for r in results:
            duration = r.get('duration', '--')
            if isinstance(duration, int):
                mins, secs = divmod(duration, 60)
                duration = f"{mins:02d}:{secs:02d}"
            tree.insert('', tk.END, values=(r.get('title', ''), r.get('author', ''), duration, r.get('bvid', '')))

    def download_from_search(self, tree, parent_win, audio_only):
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个视频")
            return
        item = tree.item(selection[0])
        bvid = item['values'][3]
        title = item['values'][0]
        parent_win.destroy()
        self.start_download(bvid, audio_only, title)

    # ---------- 批量下载（同原代码，略） ----------
    def download_selected(self, audio_only):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先在表格中选择要下载的视频（可多选）")
            return
        bvids, titles = [], []
        for item_id in selected_items:
            values = self.tree.item(item_id, 'values')
            if len(values) >= 6:
                bvids.append(values[5])
                titles.append(values[1])
        if not bvids:
            messagebox.showwarning("警告", "未找到有效的 BV 号")
            return

        self.cancel_download = False

        def batch_download():
            failed = []
            for bvid, title in zip(bvids, titles):
                if self.cancel_download:
                    self.root.after(0, lambda: self.download_status_var.set("下载已取消"))
                    return
                self.root.after(0, lambda t=title: self.download_status_var.set(f"正在下载: {t}"))
                try:
                    self.download_video(bvid, audio_only)
                    self.root.after(0, lambda t=title: self.download_status_var.set(f"下载完成: {t}"))
                except Exception as e:
                    failed.append(f"{title}: {str(e)}")
                    self.root.after(0, lambda t=title: self.download_status_var.set(f"下载失败: {t}"))
                time.sleep(3)
            if failed:
                self.root.after(0, lambda: messagebox.showwarning("部分下载失败", "\n".join(failed)))
            self.root.after(0, lambda: self.download_status_var.set("批量下载完成"))

        threading.Thread(target=batch_download, daemon=True).start()

    def cancel_download_task(self):
        self.cancel_download = True
        self.download_status_var.set("正在取消...")

    def start_download(self, bvid, audio_only, title):
        def download_thread():
            try:
                self.download_video(bvid, audio_only)
                self.root.after(0, lambda: self.download_status_var.set(f"下载完成: {title}"))
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("下载失败", f"{title}: {error_msg}"))
        threading.Thread(target=download_thread, daemon=True).start()

    def download_video(self, bvid, audio_only=False):
        url = f"https://www.bilibili.com/video/{bvid}"

        cookies = self.session.cookies.get_dict()
        tmp_cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
        tmp_cookie_file.write("# Netscape HTTP Cookie File\n")
        for name, value in cookies.items():
            tmp_cookie_file.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
        tmp_cookie_file.close()

        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [self.yt_progress_hook],
            'cookiefile': tmp_cookie_file.name,
            'retries': 5,
            'fragment_retries': 5,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
        }

        if self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        if audio_only:
            if not self.ffmpeg_path:
                raise Exception("未找到 ffmpeg，无法转换为 MP3。请将 ffmpeg.exe 和 ffprobe.exe 放在程序目录或加入系统 PATH。")
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        finally:
            os.unlink(tmp_cookie_file.name)

    def yt_progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '')
            speed = d.get('_speed_str', '')
            self.root.after(0, lambda: self.download_status_var.set(f"下载中: {percent} - {speed}"))
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self.download_status_var.set("下载完成，正在处理..."))


if __name__ == '__main__':
    root = tk.Tk()
    app = BiliApp(root)
    root.mainloop()
