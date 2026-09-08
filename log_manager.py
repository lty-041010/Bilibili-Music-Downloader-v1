# log_manager.py
import queue
import datetime
import threading
from enum import Enum

class TaskStatus(Enum):
    PENDING = "待下载"
    DOWNLOADING = "下载中"
    FINISHED = "已完成"
    FAILED = "下载失败"

# 全局队列
ui_queue = queue.Queue()

def send_log(msg, log_type="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{log_type}] {msg}"
    print(log_entry) # 保留控制台输出
    ui_queue.put(("LOG", log_entry))

def send_status_update(song_id, status: TaskStatus, title="", progress=0.0, message=""):
    ui_queue.put(("STATUS", song_id, status.value, title, progress, message))

def send_duplicate_query(file_path, title, artist):
    """发送重复文件询问，并阻塞当前线程等待结果"""
    # 创建一个结果容器和事件
    result_box = [None]
    event = threading.Event()
    # 将请求放入队列，主线程会弹窗，并设置事件
    ui_queue.put(("QUERY_DUP", file_path, title, artist, result_box, event))
    # 阻塞当前下载线程，等待主线程弹窗并点击按钮
    event.wait()
    return result_box[0] # True(覆盖), False(跳过), None(取消/全局跳过)