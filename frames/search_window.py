# frames/search_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading


class SearchWindow:
    """独立的B站搜索弹窗，显示搜索结果并支持下载"""

    def __init__(self, controller, keyword):
        """
        Args:
            controller: BiliApp 主控制器实例
            keyword: 搜索关键词
        """
        self.controller = controller
        self.keyword = keyword

        # 创建顶级窗口
        self.win = tk.Toplevel(controller.root)
        self.win.title(f"B站搜索结果: {keyword}")
        self.win.geometry("800x400")
        self.win.transient(controller.root)
        self.win.grab_set()  # 模态（可选）

        # 结果树
        columns = ('title', 'up', 'duration', 'bvid')
        self.tree = ttk.Treeview(self.win, columns=columns, show='headings',
                                 height=15, selectmode='browse')
        self.tree.heading('title', text='标题')
        self.tree.heading('up', text='UP主')
        self.tree.heading('duration', text='时长')
        self.tree.heading('bvid', text='BV号')
        self.tree.column('title', width=400)
        self.tree.column('up', width=150)
        self.tree.column('duration', width=80)
        self.tree.column('bvid', width=120)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 绑定右键复制菜单
        self.bind_copy_menu()

        # 按钮框架
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="下载MP4",
                   command=lambda: self.download_selected(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="下载MP3",
                   command=lambda: self.download_selected(True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=self.win.destroy).pack(side=tk.LEFT, padx=5)

        # 状态标签（显示加载状态）
        self.status_label = ttk.Label(self.win, text="正在搜索...")
        self.status_label.pack(pady=2)

        # 启动搜索线程
        self.fetch_results()

    def fetch_results(self):
        """在后台线程中调用B站搜索API"""

        def fetch():
            try:
                url = 'https://api.bilibili.com/x/web-interface/search/type'
                params = {
                    'search_type': 'video',
                    'keyword': self.keyword,
                    'page': 1,
                    'page_size': 20
                }
                resp = self.controller.session.get(url, params=params)
                data = resp.json()
                if data['code'] != 0:
                    raise Exception(data['message'])
                results = data['data']['result']
                # 在主线程更新UI
                self.controller.root.after(0, lambda: self.display_results(results))
            except Exception as e:
                self.controller.root.after(0, lambda: self.show_error(str(e)))

        threading.Thread(target=fetch, daemon=True).start()

    def display_results(self, results):
        """显示搜索结果到树控件"""
        self.status_label.config(text=f"找到 {len(results)} 个视频")
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in results:
            duration = r.get('duration', '--')
            if isinstance(duration, int):
                mins, secs = divmod(duration, 60)
                duration = f"{mins:02d}:{secs:02d}"
            self.tree.insert('', tk.END, values=(
                r.get('title', ''),
                r.get('author', ''),
                duration,
                r.get('bvid', '')
            ))

    def show_error(self, msg):
        self.status_label.config(text=f"搜索失败: {msg}")
        messagebox.showerror("错误", f"搜索失败: {msg}")

    def download_selected(self, audio_only):
        """下载选中的视频"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个视频")
            return
        item = self.tree.item(selection[0])
        values = item['values']
        if len(values) < 4:
            return
        bvid = values[3]  # BV号
        title = values[0]  # 标题
        # 关闭当前窗口
        self.win.destroy()
        # 调用主控制器的下载方法
        self.controller.start_download(bvid, audio_only, title)

    # ---------- 复制菜单功能 ----------
    def bind_copy_menu(self):
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(label="复制选中行", command=self.copy_selected_row)
        menu.add_command(label="复制单元格", command=self.copy_selected_cell)
        self.tree.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))

    def copy_selected_row(self):
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        values = item['values']
        text = "\t".join(str(v) for v in values)
        self.win.clipboard_clear()
        self.win.clipboard_append(text)

    def copy_selected_cell(self):
        selection = self.tree.selection()
        if not selection:
            return
        # 获取鼠标点击的列
        x = self.tree.winfo_pointerx() - self.tree.winfo_rootx()
        col = self.tree.identify_column(x)
        if not col:
            return
        col_index = int(col.replace('#', '')) - 1
        item = self.tree.item(selection[0])
        values = item['values']
        if col_index < len(values):
            value = values[col_index]
            self.win.clipboard_clear()
            self.win.clipboard_append(str(value))