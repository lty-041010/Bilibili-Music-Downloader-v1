# main.py
import tkinter as tk
from ui import BiliApp

if __name__ == '__main__':
    root = tk.Tk()
    app = BiliApp(root)
    root.mainloop()