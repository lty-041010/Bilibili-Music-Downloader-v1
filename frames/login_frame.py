# frames/login_frame.py
import tkinter as tk
from tkinter import ttk
import qrcode
from qrcode.image.pil import PilImage
import threading
import io
import time
from PIL import Image, ImageTk


class LoginFrame(ttk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller          # 主控对象（BiliApp 实例）
        self.qrcode_key = None
        self.login_thread = None
        self.stop_login_poll = False
        self.setup_ui()

    def setup_ui(self):
        # 状态提示标签
        self.status_label = ttk.Label(self, text="正在生成二维码...", style='Header.TLabel')
        self.status_label.pack(pady=10)

        # 二维码显示标签
        self.qr_label = ttk.Label(self)
        self.qr_label.pack(pady=10)

        # 按钮框架
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)

        self.refresh_qr_btn = ttk.Button(btn_frame, text="刷新二维码",
                                         command=self.refresh_qrcode, state=tk.DISABLED)
        self.refresh_qr_btn.pack(side=tk.LEFT, padx=5)

        self.theme_btn_login = ttk.Button(btn_frame, text="切换主题",
                                          command=self.controller.toggle_theme)
        self.theme_btn_login.pack(side=tk.LEFT, padx=5)

        # 生成二维码
        self.generate_qrcode()

    def generate_qrcode(self):
        """生成登录二维码并开始轮询"""
        try:
            url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
            resp = self.controller.session.get(url)
            data = resp.json()
            if data['code'] != 0:
                raise Exception(f"获取二维码失败: {data['message']}")

            self.qrcode_key = data['data']['qrcode_key']
            qr_url = data['data']['url']

            # 生成二维码图片
            qr_img = qrcode.make(qr_url, image_factory=PilImage, box_size=6, border=2)
            img_bytes = io.BytesIO()
            qr_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            pil_image = Image.open(img_bytes)
            self.tk_image = ImageTk.PhotoImage(pil_image)
            self.qr_label.config(image=self.tk_image)

            self.status_label.config(text="请使用B站手机客户端扫描二维码")
            self.refresh_qr_btn.config(state=tk.NORMAL)

            # 开始轮询登录状态
            self.stop_login_poll = False
            self.login_thread = threading.Thread(target=self.poll_login, daemon=True)
            self.login_thread.start()

        except Exception as e:
            self.status_label.config(text=f"错误: {e}")
            # 可弹出错误框（由 controller 提供）
            from tkinter import messagebox
            messagebox.showerror("错误", str(e))

    def refresh_qrcode(self):
        """刷新二维码"""
        self.stop_login_poll = True
        if self.login_thread and self.login_thread.is_alive():
            self.login_thread.join(timeout=1)
        self.generate_qrcode()

    def poll_login(self):
        """轮询二维码登录状态"""
        url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
        params = {'qrcode_key': self.qrcode_key}
        last_status = None

        while not self.stop_login_poll:
            try:
                resp = self.controller.session.get(url, params=params)
                data = resp.json()

                if data['code'] != 0:
                    status = data['code']
                    if status != last_status:
                        if status == 86038:          # 二维码失效
                            self.update_status("二维码已失效，请刷新")
                            self.refresh_qr_btn.config(state=tk.NORMAL)
                            break
                        elif status == 86090:        # 已扫描，等待确认
                            self.update_status("二维码已扫描，等待确认...")
                        elif status == 86101:        # 未扫描
                            self.update_status("未扫描，请使用B站客户端扫码")
                        else:
                            self.update_status(f"状态码: {status} - {data['message']}")
                        last_status = status
                else:
                    # 登录成功，验证并跳转
                    self.verify_and_login()
                    break

                time.sleep(2)

            except Exception as e:
                self.update_status(f"轮询异常: {e}")
                time.sleep(2)

    def verify_and_login(self):
        """验证登录并切换至主界面"""
        uid = self.controller.session.cookies.get('DedeUserID')
        if not uid:
            try:
                nav_resp = self.controller.session.get('https://api.bilibili.com/x/web-interface/nav')
                nav_data = nav_resp.json()
                if nav_data['code'] == 0 and nav_data['data'].get('isLogin'):
                    uid = nav_data['data']['mid']
            except:
                pass

        if uid:
            self.controller.uid = uid
            self.controller.save_cookies()          # 保存登录凭证
            self.update_status(f"登录成功！UID: {uid}")
            # 延迟切换主界面，让用户看到成功提示
            self.controller.root.after(500, self.controller.show_main_frame)
        else:
            self.update_status("登录确认中，请稍候...")
            # 继续轮询（或重新尝试）
            self.poll_login()

    def update_status(self, text):
        """更新状态标签（线程安全）"""
        self.controller.root.after(0, lambda: self.status_label.config(text=text))