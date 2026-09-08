# frames/main_frame.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import os
import re
import time
import json
import queue
from PIL import Image, ImageTk
import requests


import log_manager
from log_manager import TaskStatus
# HEADERS 直接在文件内定义，避免导入 config 冲突
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/'
}

# 拖拽支持（如果有）
try:
    from tkinterdnd2 import DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


class MainFrame(ttk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.all_data = controller.all_data
        self.uid = controller.uid
        self.user_info = None

        self.search_scope_var = tk.StringVar(value="B站搜索")
        self.path_var = tk.StringVar(value=controller.download_dir)

        self.cancel_download = False   # 本地取消标志

        self.setup_ui()

        self.load_user_info()
        self.start_refresh_data()

        self.after(100, self.process_queue)

    def setup_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---------- 用户信息栏 ----------
        user_frame = ttk.Frame(self, padding=5)
        user_frame.grid(row=0, column=0, sticky='ew')
        self.user_avatar_label = ttk.Label(user_frame)
        self.user_avatar_label.pack(side=tk.LEFT, padx=5)
        self.user_name_label = ttk.Label(user_frame, text="加载中...", style='Header.TLabel')
        self.user_name_label.pack(side=tk.LEFT, padx=5)

        # ---------- 搜索栏 ----------
        search_frame = ttk.Frame(self, padding=5)
        search_frame.grid(row=1, column=0, sticky='ew')
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame, width=35)
        self.search_entry.pack(side=tk.LEFT, padx=5)

        if DND_AVAILABLE:
            self.search_entry.drop_target_register(DND_FILES)
            self.search_entry.dnd_bind('<<Drop>>', self.on_drop)

        search_scope_combo = ttk.Combobox(search_frame, textvariable=self.search_scope_var,
                                          values=["B站搜索", "收藏夹搜索"], width=10, state="readonly")
        search_scope_combo.pack(side=tk.LEFT, padx=2)
        self.search_btn = ttk.Button(search_frame, text="搜索/解析", command=self.search_video)
        self.search_btn.pack(side=tk.LEFT, padx=5)
        self.download_mp4_btn_s = ttk.Button(search_frame, text="下载MP4",
                                             command=lambda: self.download_input(False))
        self.download_mp4_btn_s.pack(side=tk.LEFT, padx=2)
        self.download_mp3_btn_s = ttk.Button(search_frame, text="下载MP3",
                                             command=lambda: self.download_input(True))
        self.download_mp3_btn_s.pack(side=tk.LEFT, padx=2)

        # ---------- 主体 ----------
        body_frame = ttk.Frame(self, padding=5)
        body_frame.grid(row=2, column=0, sticky='nsew')
        body_frame.grid_rowconfigure(0, weight=1)
        body_frame.grid_columnconfigure(1, weight=1)

        left_frame = ttk.Frame(body_frame, padding=5)
        left_frame.grid(row=0, column=0, sticky='ns')
        ttk.Label(left_frame, text="收藏夹列表", style='Header.TLabel').pack()
        self.folder_listbox = tk.Listbox(left_frame, width=30, height=25,
                                         bg=self.controller.theme['listbox_bg'],
                                         fg=self.controller.theme['fg'],
                                         selectbackground=self.controller.theme['tree_selected_bg'],
                                         font=(self.controller.theme['font_family'],
                                               self.controller.theme['font_size']))
        self.folder_listbox.pack(fill=tk.Y, expand=True)

        right_frame = ttk.Frame(body_frame, padding=5)
        right_frame.grid(row=0, column=1, sticky='nsew')
        columns = ('index', 'title', 'up', 'duration', 'favorite_time', 'bvid', 'status')
        self.tree = ttk.Treeview(right_frame, columns=columns, show='headings',
                                 height=25, selectmode='extended')
        self.tree.heading('index', text='序号')
        self.tree.heading('title', text='标题')
        self.tree.heading('up', text='UP主')
        self.tree.heading('duration', text='时长')
        self.tree.heading('favorite_time', text='收藏时间')
        self.tree.heading('bvid', text='BV号')
        self.tree.heading('status', text='状态')
        self.tree.column('index', width=50, anchor='center')
        self.tree.column('title', width=300)
        self.tree.column('up', width=100)
        self.tree.column('duration', width=80)
        self.tree.column('favorite_time', width=140)
        self.tree.column('bvid', width=120)
        self.tree.column('status', width=80, anchor='center')

        scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # ---------- 底部栏 ----------
        bottom_frame = ttk.Frame(self, padding=5)
        bottom_frame.grid(row=3, column=0, sticky='ew')

        # 左侧：保存路径 + 歌词语言下拉框（中文显示）
        path_frame = ttk.Frame(bottom_frame)
        path_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(path_frame, text="保存至:").pack(side=tk.LEFT)
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=30, state='readonly')
        path_entry.pack(side=tk.LEFT, padx=2)
        self.path_btn = ttk.Button(path_frame, text="选择路径", command=self.choose_download_dir)
        self.path_btn.pack(side=tk.LEFT, padx=2)

        # ===== 歌词语言下拉框（中文显示，内部值仍为英文标识） =====
        lang_frame = ttk.Frame(bottom_frame)
        lang_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(lang_frame, text="歌词语言:").pack(side=tk.LEFT)

        # 显示文本 ↔ 内部值映射
        self.lang_mapping = {"none": "不转换", "simplified": "简体", "traditional": "繁体"}
        self.lang_reverse_mapping = {v: k for k, v in self.lang_mapping.items()}

        # 用于显示的 StringVar
        self.lang_display_var = tk.StringVar()
        current_lang = self.controller.lyrics_lang.get()
        display_text = self.lang_mapping.get(current_lang, "不转换")
        self.lang_display_var.set(display_text)

        self.lyrics_lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.lang_display_var,
            values=list(self.lang_mapping.values()),  # 显示中文选项
            state="readonly",
            width=10
        )
        self.lyrics_lang_combo.pack(side=tk.LEFT)
        self.lyrics_lang_combo.bind("<<ComboboxSelected>>", self.on_lyrics_lang_change)

        # 右侧按钮组
        self.open_folder_btn = ttk.Button(bottom_frame, text="打开目录",
                                          command=self.open_download_folder)
        self.open_folder_btn.pack(side=tk.RIGHT, padx=5)

        self.refresh_btn = ttk.Button(bottom_frame, text="刷新数据", command=self.start_refresh_data)
        self.refresh_btn.pack(side=tk.RIGHT, padx=5)
        self.theme_btn = ttk.Button(bottom_frame, text="切换主题",
                                    command=self.controller.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=5)
        self.switch_account_btn = ttk.Button(bottom_frame, text="切换账号",
                                             command=self.switch_account)
        self.switch_account_btn.pack(side=tk.RIGHT, padx=5)
        self.download_mp4_btn = ttk.Button(bottom_frame, text="下载MP4",
                                           command=lambda: self.download_selected(False))
        self.download_mp4_btn.pack(side=tk.RIGHT, padx=5)
        self.download_mp3_btn = ttk.Button(bottom_frame, text="下载MP3",
                                           command=lambda: self.download_selected(True))
        self.download_mp3_btn.pack(side=tk.RIGHT, padx=5)
        self.cancel_btn = ttk.Button(bottom_frame, text="取消下载",
                                     command=self.cancel_download_task)
        self.cancel_btn.pack(side=tk.RIGHT, padx=5)
        self.cancel_all_btn = ttk.Button(bottom_frame, text="全部取消",
                                         command=self.cancel_all_tasks)
        self.cancel_all_btn.pack(side=tk.RIGHT, padx=5)

        # ---------- 状态栏 ----------
        status_frame = ttk.Frame(self, padding=2)
        status_frame.grid(row=4, column=0, sticky='ew')
        ttk.Label(status_frame, text="下载状态:").pack(side=tk.LEFT, padx=5)
        ttk.Label(status_frame, textvariable=self.controller.download_status_var).pack(side=tk.LEFT, padx=5)

        self.bottom_progress = ttk.Progressbar(self, mode='determinate', maximum=100, length=300)
        self.bottom_progress.grid(row=5, column=0, sticky='ew', pady=5)

        self.log_box = scrolledtext.ScrolledText(self, height=8, state='disabled')
        self.log_box.grid(row=6, column=0, sticky='ew', padx=5, pady=5)

        # ---------- 加载覆盖层 ----------
        self.loading_overlay = ttk.Frame(self)
        self.loading_overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.loading_label = ttk.Label(self.loading_overlay, text="正在获取收藏夹数据，请稍候...",
                                       style='Header.TLabel')
        self.loading_label.pack(pady=10)
        self.loading_progress = ttk.Progressbar(self.loading_overlay, mode='determinate',
                                                maximum=100, length=300)
        self.loading_progress.pack(pady=5)

        self.folder_listbox.bind('<<ListboxSelect>>', self.on_folder_select)

    # ---------- 歌词语言切换事件（内部值映射） ----------
    def on_lyrics_lang_change(self, event):
        """将下拉框的中文显示转换为内部英文值并同步到下载器。"""
        display_text = self.lang_display_var.get()
        internal_value = self.lang_reverse_mapping.get(display_text, "none")
        self.controller.lyrics_lang.set(internal_value)
        self.controller.downloader.lyrics_lang = internal_value

    # ---------- 队列处理 ----------
    def process_queue(self):
        while True:
            try:
                msg_type, *data = log_manager.ui_queue.get_nowait()

                if msg_type == "LOG":
                    self.log_box.configure(state='normal')
                    self.log_box.insert(tk.END, data[0] + "\n")
                    self.log_box.see(tk.END)
                    self.log_box.configure(state='disabled')

                elif msg_type == "STATUS":
                    bvid = data[0]
                    status = data[1]
                    for item in self.tree.get_children():
                        if self.tree.item(item)['values'][5] == bvid:
                            self.tree.set(item, 'status', status)
                            break

                elif msg_type == "QUERY_DUP":
                    file_path, title, artist, result_box, event = data
                    choice = messagebox.askyesnocancel(
                        "发现重复文件",
                        f"歌曲已存在！\n\n歌名：{title}\n歌手：{artist}\n\n是否要重新下载并覆盖？\n"
                        f"【是】覆盖当前文件\n【否】跳过当前文件\n【取消】将所有重复文件全部跳过"
                    )
                    result_box[0] = choice
                    event.set()

            except queue.Empty:
                break
        self.after(100, self.process_queue)

    # ---------- 用户信息 ----------
    def load_user_info(self):
        def fetch():
            try:
                info = self.controller.api.get_user_info()
                if info:
                    self.user_info = info
                    self.controller.root.after(0, self.update_user_info_ui)
            except Exception as e:
                print(f"获取用户信息失败: {e}")

        threading.Thread(target=fetch, daemon=True).start()

    def update_user_info_ui(self):
        if not self.user_info:
            return
        uname = self.user_info.get('uname', '未知')
        face_url = self.user_info.get('face', '')
        self.user_name_label.config(text=f"{uname} (UID: {self.uid})")
        if face_url:
            threading.Thread(target=self.download_avatar, args=(face_url,), daemon=True).start()

    def download_avatar(self, url):
        import io
        try:
            resp = requests.get(url, headers=HEADERS)
            if resp.status_code == 200:
                img_data = resp.content
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((40, 40), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.controller.root.after(0, lambda: self.user_avatar_label.config(image=photo))
                self.user_avatar_label.image = photo
        except Exception as e:
            print(f"头像下载失败: {e}")

    # ---------- 切换账号 ----------
    def switch_account(self):
        if messagebox.askyesno("确认", "确定要切换账号吗？将清除当前登录状态。"):
            self.controller.clear_cookies()
            self.controller.uid = None
            self.controller.all_data.clear()
            self.controller.show_login_frame()

    # ---------- 数据获取 ----------
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
            folders = self.controller.api.get_all_folders(self.uid)
            total_folders = len(folders)
            for i, folder in enumerate(folders):
                fid = folder['id']
                title = folder['title']
                media_count = folder['media_count']
                videos = self.controller.api.get_folder_videos(fid)
                self.all_data[title] = {'folder_id': fid, 'media_count': media_count, 'videos': videos}
                progress_text = f"正在获取收藏夹 [{i + 1}/{total_folders}]: {title}"
                self.controller.root.after(0, lambda t=progress_text: self.loading_label.config(text=t))
                time.sleep(0.2)
            self.controller.root.after(0, self.on_data_loaded)
        except Exception as e:
            error_msg = str(e)
            self.controller.root.after(0, lambda: self.on_data_error(error_msg))

    def on_data_loaded(self):
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.folder_listbox.delete(0, tk.END)
        for folder_name, folder_data in self.all_data.items():
            display_name = f"{folder_name} ({len(folder_data['videos'])})"
            self.folder_listbox.insert(tk.END, display_name)
        self.refresh_btn.config(state=tk.NORMAL)
        self.controller.root.title(f"B站收藏夹管理器 - UID: {self.uid} (已加载 {len(self.all_data)} 个收藏夹)")

    def on_data_error(self, error_msg):
        self.loading_progress.stop()
        self.loading_overlay.place_forget()
        self.refresh_btn.config(state=tk.NORMAL)
        messagebox.showerror("错误", f"获取数据失败：{error_msg}")

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
                i, video['title'], video['up'], video['duration'],
                video['favorite_time'], video['bvid'], ''
            ))

    # ---------- 路径相关 ----------
    def choose_download_dir(self):
        dir_path = filedialog.askdirectory(initialdir=self.controller.download_dir,
                                           title="选择音乐保存目录")
        if dir_path:
            self.controller.download_dir = dir_path.replace("/", "\\")
            self.path_var.set(self.controller.download_dir)
            self.controller.config['download_dir'] = self.controller.download_dir
            with open(self.controller.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.controller.config, f, ensure_ascii=False, indent=2)
            if not os.path.exists(self.controller.download_dir):
                os.makedirs(self.controller.download_dir)
            self.controller.downloader.download_dir = self.controller.download_dir

    def open_download_folder(self):
        os.startfile(self.controller.download_dir)

    # ---------- 拖拽 ----------
    def on_drop(self, event):
        data = event.data
        if data.startswith('{') and data.endswith('}'):
            return
        if os.path.exists(data):
            return
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, data.strip())
        self.search_video()

    # ---------- 搜索与下载 ----------
    def extract_bvid(self, text):
        match = re.search(r'BV[0-9A-Za-z]+', text)
        if match:
            return match.group(0)
        match = re.search(r'av(\d+)', text)
        if match:
            return f"av{match.group(1)}"
        return None

    def download_input(self, audio_only):
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
        keyword = self.search_entry.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入关键词、BV号或链接")
            return

        video_id = self.extract_bvid(keyword)
        if video_id:
            if messagebox.askyesno("下载格式", "选择“是”下载MP4，选择“否”下载MP3"):
                audio_only = False
            else:
                audio_only = True
            self.start_download(video_id, audio_only, video_id)
            return

        scope = self.search_scope_var.get()
        if scope == "收藏夹搜索":
            self.search_local(keyword)
        else:
            self.search_online(keyword)

    def search_local(self, keyword):
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
        self.show_search_results_window(results, title=f"收藏夹搜索结果: {keyword}")

    def search_online(self, keyword):
        search_win = tk.Toplevel(self.controller.root)
        search_win.title(f"B站搜索结果: {keyword}")
        search_win.geometry("800x400")
        search_win.transient(self.controller.root)
        columns = ('title', 'up', 'duration', 'bvid')
        result_tree = ttk.Treeview(search_win, columns=columns, show='headings',
                                   height=15, selectmode='browse')
        result_tree.heading('title', text='标题')
        result_tree.heading('up', text='UP主')
        result_tree.heading('duration', text='时长')
        result_tree.heading('bvid', text='BV号')
        result_tree.column('title', width=400)
        result_tree.column('up', width=150)
        result_tree.column('duration', width=80)
        result_tree.column('bvid', width=120)
        result_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.bind_copy_menu(result_tree)

        btn_frame = ttk.Frame(search_win)
        btn_frame.pack(pady=5)
        mp4_btn = ttk.Button(btn_frame, text="下载MP4",
                             command=lambda: self.download_from_search(result_tree, search_win, False))
        mp4_btn.pack(side=tk.LEFT, padx=5)
        mp3_btn = ttk.Button(btn_frame, text="下载MP3",
                             command=lambda: self.download_from_search(result_tree, search_win, True))
        mp3_btn.pack(side=tk.LEFT, padx=5)

        def fetch_results():
            try:
                url = 'https://api.bilibili.com/x/web-interface/search/type'
                params = {'search_type': 'video', 'keyword': keyword, 'page': 1, 'page_size': 20}
                resp = self.controller.session.get(url, params=params)
                data = resp.json()
                if data['code'] != 0:
                    raise Exception(data['message'])
                results = data['data']['result']
                self.controller.root.after(0, lambda: self.display_search_results(result_tree, results))
            except Exception as e:
                self.controller.root.after(0, lambda: messagebox.showerror("错误", f"搜索失败: {str(e)}"))

        threading.Thread(target=fetch_results, daemon=True).start()

    def show_search_results_window(self, videos, title="搜索结果"):
        win = tk.Toplevel(self.controller.root)
        win.title(title)
        win.geometry("800x400")
        win.transient(self.controller.root)
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
        mp4_btn = ttk.Button(btn_frame, text="下载MP4",
                             command=lambda: self.download_from_search(tree, win, False))
        mp4_btn.pack(side=tk.LEFT, padx=5)
        mp3_btn = ttk.Button(btn_frame, text="下载MP3",
                             command=lambda: self.download_from_search(tree, win, True))
        mp3_btn.pack(side=tk.LEFT, padx=5)

        for video in videos:
            duration = video.get('duration', '--')
            if isinstance(duration, int):
                mins, secs = divmod(duration, 60)
                duration = f"{mins:02d}:{secs:02d}"
            tree.insert('', tk.END, values=(video['title'], video['up'], duration, video['bvid']))

    def bind_copy_menu(self, tree):
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
        self.controller.root.clipboard_clear()
        self.controller.root.clipboard_append(text)

    def copy_selected_cell(self, tree):
        selection = tree.selection()
        if not selection:
            return
        col = tree.identify_column(tree.winfo_pointerx() - tree.winfo_rootx())
        if not col:
            return
        col_index = int(col.replace('#', '')) - 1
        item = tree.item(selection[0])
        value = item['values'][col_index]
        self.controller.root.clipboard_clear()
        self.controller.root.clipboard_append(str(value))

    def display_search_results(self, tree, results):
        for item in tree.get_children():
            tree.delete(item)
        for r in results:
            duration = r.get('duration', '--')
            if isinstance(duration, int):
                mins, secs = divmod(duration, 60)
                duration = f"{mins:02d}:{secs:02d}"
            tree.insert('', tk.END, values=(r.get('title', ''), r.get('author', ''),
                                            duration, r.get('bvid', '')))

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

    # ---------- 批量下载 ----------
    def download_selected(self, audio_only):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要下载的视频")
            return

        bvids = []
        titles = []
        for item in selected_items:
            values = self.tree.item(item)['values']
            if len(values) >= 6:
                bvids.append(values[5])
                titles.append(values[1])
        if not bvids:
            messagebox.showwarning("警告", "未获取到有效的视频ID")
            return

        # 重置取消标志
        self.cancel_download = False
        self.controller.downloader.reset_cancel_flag()

        def batch_download():
            total = len(bvids)
            completed = 0
            failed = []

            self.controller.root.after(0, lambda: self.bottom_progress.config(maximum=total, value=0))

            for bvid, title in zip(bvids, titles):
                if self.cancel_download or self.controller.downloader.cancel_flag:
                    self.controller.root.after(0, lambda: self.controller.download_status_var.set("下载已取消"))
                    break

                self.controller.root.after(0, lambda t=title: self.controller.download_status_var.set(f"正在下载: {t}"))
                try:
                    self.controller.downloader.download_video(bvid, audio_only)
                    completed += 1
                    self.controller.root.after(0, lambda c=completed: self.bottom_progress.config(value=c))
                    self.controller.root.after(0, lambda t=title: self.controller.download_status_var.set(
                        f"下载完成: {t}"))
                except Exception as e:
                    failed.append(f"{title}: {str(e)}")
                    self.controller.root.after(0, lambda t=title: self.controller.download_status_var.set(
                        f"下载失败: {t}"))
                time.sleep(3)

            if failed:
                self.controller.root.after(0, lambda: messagebox.showwarning("部分下载失败", "\n".join(failed)))
            self.controller.root.after(0, lambda: self.controller.download_status_var.set("批量下载完成"))
            self.controller.root.after(0, lambda: self.bottom_progress.config(value=total))

        threading.Thread(target=batch_download, daemon=True).start()

    def cancel_download_task(self):
        """取消当前批量下载（停止后续任务）"""
        self.cancel_download = True
        self.controller.downloader.cancel_all()
        self.controller.download_status_var.set("正在取消...")

    def cancel_all_tasks(self):
        """取消所有下载任务（包括当前下载和待下载任务）"""
        self.cancel_download = True
        self.controller.downloader.cancel_all()
        # 清空下载器任务队列中的待下载任务状态
        for task in self.controller.downloader.tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.FAILED
                task.message = "已取消"
        self.controller.download_status_var.set("已取消全部任务")

    def start_download(self, bvid, audio_only, title):
        def download_thread():
            try:
                self.controller.downloader.download_video(bvid, audio_only)
                self.controller.root.after(0, lambda: self.controller.download_status_var.set(f"下载完成: {title}"))
            except Exception as e:
                self.controller.root.after(0, lambda: messagebox.showerror("下载失败", f"{title}: {str(e)}"))

        threading.Thread(target=download_thread, daemon=True).start()

    # 主题更新回调
    def on_theme_changed(self):
        theme = self.controller.theme
        self.folder_listbox.config(bg=theme['listbox_bg'], fg=theme['fg'],
                                   selectbackground=theme['tree_selected_bg'])
        pass