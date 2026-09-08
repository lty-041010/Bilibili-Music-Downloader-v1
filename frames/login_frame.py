# frames/login_frame.py
import tkinter as tk
from tkinter import ttk
import qrcode
from qrcode.image.pil import PilImage
import threading
import io
import time
from PIL import Image, ImageTk
import log_manager


class LoginFrame(ttk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.qrcode_key = None
        self.login_thread = None
        self.stop_login_poll = False
        self.setup_ui()

    def setup_ui(self):
        self.status_label = ttk.Label(self, text="正在生成二维码...", style='Header.TLabel')
        self.status_label.pack(pady=10)

        self.qr_label = ttk.Label(self)
        self.qr_label.pack(pady=10)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)

        self.refresh_qr_btn = ttk.Button(btn_frame, text="刷新二维码",
                                         command=self.refresh_qrcode, state=tk.DISABLED)
        self.refresh_qr_btn.pack(side=tk.LEFT, padx=5)

        self.theme_btn_login = ttk.Button(btn_frame, text="切换主题",
                                          command=self.controller.toggle_theme)
        self.theme_btn_login.pack(side=tk.LEFT, padx=5)

        self.generate_qrcode()

    def generate_qrcode(self):
        try:
            url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
            resp = self.controller.session.get(url, timeout=10)
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
            from tkinter import messagebox
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
                resp = self.controller.session.get(url, params=params, timeout=10)
                data = resp.json()
                log_manager.send_log(f"poll响应: {data}", "DEBUG")

                if data['code'] != 0:
                    log_manager.send_log(f"poll请求错误: {data['message']}", "ERROR")
                    break
                else:
                    inner_data = data.get('data', {})
                    inner_code = inner_data.get('code', -1)
                    inner_message = inner_data.get('message', '')

                    if inner_code == 86101:
                        if last_status != 86101:
                            self.update_status("未扫描，请使用B站客户端扫码")
                            last_status = inner_code
                    elif inner_code == 86090:
                        if last_status != 86090:
                            self.update_status("二维码已扫描，等待确认...")
                            last_status = inner_code
                    elif inner_code == 86038:
                        self.update_status("二维码已失效，请刷新")
                        self.refresh_qr_btn.config(state=tk.NORMAL)
                        break
                    elif inner_code == 0:
                        complete_url = inner_data.get('url', '')
                        log_manager.send_log(f"登录成功，complete_url: {complete_url}", "DEBUG")

                        if complete_url:
                            try:
                                self.controller.session.get(complete_url, timeout=10)
                            except Exception as e:
                                log_manager.send_log(f"请求跨域链接异常: {e}", "ERROR")

                        self.verify_and_login()
                        break
                    else:
                        if last_status != inner_code:
                            self.update_status(f"状态码: {inner_code} - {inner_message}")
                            last_status = inner_code

                time.sleep(2)
            except Exception as e:
                log_manager.send_log(f"poll轮询异常: {e}", "ERROR")
                self.update_status(f"轮询异常: {e}")
                time.sleep(2)

    def verify_and_login(self):
        # 获取所有cookies
        cookies_dict = self.controller.session.cookies.get_dict()
        log_manager.send_log(f"当前cookies: {cookies_dict}", "DEBUG")

        # 从字典中获取UID，避免重复Cookie异常
        uid = None
        for _ in range(10):
            cookies_dict = self.controller.session.cookies.get_dict()
            uid = cookies_dict.get('DedeUserID')
            if uid:
                break
            time.sleep(0.5)

        if not uid:
            for attempt in range(5):
                try:
                    nav_resp = self.controller.session.get('https://api.bilibili.com/x/web-interface/nav', timeout=10)
                    nav_data = nav_resp.json()
                    log_manager.send_log(f"nav接口返回: {nav_data}", "DEBUG")
                    if nav_data['code'] == 0 and nav_data['data'].get('isLogin'):
                        uid = nav_data['data']['mid']
                        break
                except Exception as e:
                    log_manager.send_log(f"获取UID异常: {e}", "ERROR")
                time.sleep(1)

        if uid:
            self.controller.uid = int(uid) if str(uid).isdigit() else uid
            self.controller.save_cookies()
            self.update_status(f"登录成功！UID: {uid}")
            self.controller.root.after(500, self.controller.show_main_frame)
        else:
            log_manager.send_log("登录成功但获取UID失败，自动刷新二维码", "WARNING")
            self.update_status("获取UID失败，正在刷新二维码...")
            self.refresh_qr_btn.config(state=tk.NORMAL)
            self.stop_login_poll = True
            self.controller.root.after(1000, self.refresh_qrcode)

    def update_status(self, text):
        self.controller.root.after(0, lambda: self.status_label.config(text=text))