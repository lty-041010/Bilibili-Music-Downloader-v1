# log_manager.py
import queue
import datetime
import threading
import os
from enum import Enum
from config import APP_DIR  # 统一使用 config 中的目录

class TaskStatus(Enum):
    PENDING = "待下载"
    DOWNLOADING = "下载中"
    FINISHED = "已完成"
    FAILED = "下载失败"
    CANCELLED = "已取消"

# 全局队列
ui_queue = queue.Queue()

# 日志文件路径
LOG_FILE = os.path.join(APP_DIR, "bili_downloader.log")

# 文件写入锁（线程安全）
_log_lock = threading.Lock()

def _write_log_file(msg):
    """将日志消息追加写入日志文件"""
    try:
        with _log_lock:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(msg + "\n")
    except Exception as e:
        print(f"写入日志文件失败: {e}")

def send_log(msg, log_type="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{log_type}] {msg}"
    print(log_entry)  # 保留控制台输出
    ui_queue.put(("LOG", log_entry))
    _write_log_file(log_entry)  # 写入文件

def send_status_update(song_id, status: TaskStatus, title="", progress=0.0, message=""):
    ui_queue.put(("STATUS", song_id, status.value, title, progress, message))


def send_duplicate_query(file_path, title, artist):
    """发送重复文件询问，并阻塞当前线程等待结果（增加30秒超时）"""
    result_box = [None]
    event = threading.Event()
    ui_queue.put(("QUERY_DUP", file_path, title, artist, result_box, event))

    # 等待最多 30 秒，如果用户没点，默认返回 False（跳过当前文件）
    event.wait(timeout=30)

    # 如果超时了且没有结果（result_box[0] 还是 None），默认改为 False
    if result_box[0] is None:
        result_box[0] = False  # 自动跳过当前文件，继续下一个任务

    return result_box[0]  # True(覆盖), False(跳过), None(取消/全局跳过)