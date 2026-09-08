# downloader.py
import os
import re
import tempfile
import yt_dlp
from log_manager import TaskStatus, send_log, send_status_update, send_duplicate_query
from utils import parse_filename, clean_noise_text, embed_lyrics


class DownloadTask:
    def __init__(self, bvid, title="", status=TaskStatus.PENDING, progress=0.0, message=""):
        self.bvid = bvid
        self.title = title
        self.status = status
        self.progress = progress
        self.message = message
        self.filepath = None
        self.skip_all_duplicates = False


class Downloader:
    def __init__(self, download_dir, ffmpeg_path, session, progress_callback=None, task_callback=None, root=None, lyrics_lang=None):
        self.download_dir = download_dir
        self.ffmpeg_path = ffmpeg_path
        self.session = session
        self.progress_callback = progress_callback
        self.task_callback = task_callback
        self.tasks = {}
        self.current_bvid = None
        self.root = root
        self.skip_all_duplicates = False
        self.cancel_flag = False
        self.lyrics_lang = lyrics_lang  # 可以是 StringVar 或字符串

    # ---------- 任务管理 ----------
    def add_task(self, bvid, title=""):
        if bvid not in self.tasks:
            task = DownloadTask(bvid, title=title, status=TaskStatus.PENDING)
            self.tasks[bvid] = task
            self._notify_task_update(task)

    def _notify_task_update(self, task):
        if self.task_callback:
            self.task_callback(task)
        send_status_update(
            task.bvid,
            task.status,
            title=task.title,
            progress=task.progress,
            message=task.message
        )

    def _update_task(self, bvid, **kwargs):
        if bvid not in self.tasks:
            self.tasks[bvid] = DownloadTask(bvid)
        task = self.tasks[bvid]
        for key, value in kwargs.items():
            setattr(task, key, value)
        self._notify_task_update(task)

    # ---------- 取消控制 ----------
    def cancel_all(self):
        self.cancel_flag = True
        send_log("已请求取消所有下载任务", "WARNING")

    def reset_cancel_flag(self):
        self.cancel_flag = False

    # ---------- 下载核心 ----------
    def download_video(self, bvid, audio_only=False):
        if self.cancel_flag:
            raise Exception("下载已取消")

        self.add_task(bvid)
        self._update_task(bvid, status=TaskStatus.DOWNLOADING, progress=0.0)
        self.current_bvid = bvid

        url = f"https://www.bilibili.com/video/{bvid}"
        cookies = self.session.cookies.get_dict()

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp_cookie_file:
            tmp_cookie_file.write("# Netscape HTTP Cookie File\n")
            for name, value in cookies.items():
                tmp_cookie_file.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
            tmp_cookie_path = tmp_cookie_file.name

        ydl_opts = {
            'outtmpl': os.path.join(self.download_dir, 'temp_%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [self._hook],
            'cookiefile': tmp_cookie_path,
            'retries': 5,
            'fragment_retries': 5,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
        }

        if self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        if audio_only:
            if not self.ffmpeg_path:
                raise Exception("未找到 ffmpeg，无法转换为 MP3。")
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
                info = ydl.extract_info(url, download=True)

                file_path = None
                if 'requested_downloads' in info and info['requested_downloads']:
                    file_path = info['requested_downloads'][0].get('filepath')
                if not file_path:
                    file_path = ydl.prepare_filename(info)

                if audio_only:
                    file_path = os.path.splitext(file_path)[0] + ".mp3"

                # 处理文件（重命名、嵌入歌词等）
                self._process_audio_file(file_path, audio_only)

                self._update_task(bvid, status=TaskStatus.FINISHED, progress=100.0, filepath=file_path)

        except Exception as e:
            if str(e) == "下载已取消":
                self._update_task(bvid, status=TaskStatus.FAILED, message="用户取消下载")
                send_log(f"下载已取消: {bvid}", "WARNING")
            else:
                self._update_task(bvid, status=TaskStatus.FAILED, message=str(e))
                raise
        finally:
            if os.path.exists(tmp_cookie_path):
                os.unlink(tmp_cookie_path)

    # ---------- 处理下载后的文件 ----------
    def _process_audio_file(self, file_path, is_audio):
        # 如果是视频（MP4），仅做基本的重命名（去除 temp_ 前缀）并返回
        if not is_audio:
            dirname = os.path.dirname(file_path)
            basename = os.path.basename(file_path)
            if basename.startswith("temp_"):
                new_basename = basename[5:]  # 去掉 "temp_"
                new_path = os.path.join(dirname, new_basename)
                try:
                    os.rename(file_path, new_path)
                    send_log(f"视频已重命名为: {new_basename}")
                except Exception as e:
                    send_log(f"视频重命名失败: {e}", "ERROR")
            return

        # --- 以下仅针对音频文件 ---
        base_dir = os.path.dirname(file_path)
        filename = os.path.basename(file_path)

        # 去除 "temp_" 前缀并去掉扩展名
        temp_name = filename.replace("temp_", "").replace(".mp3", "")
        title, artist = parse_filename(temp_name)
        if not title:
            title = clean_noise_text(temp_name)

        safe_title = re.sub(r'[\\/:*?"<>|]', "", title)
        safe_artist = re.sub(r'[\\/:*?"<>|]', "", artist)
        base_name = f"{safe_title} - {safe_artist}" if safe_artist else safe_title
        new_name = f"{base_name}.mp3"
        new_path = os.path.join(base_dir, new_name)

        # 检查重复
        if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(file_path):
            send_log(f"发现重复文件: {safe_title} - {safe_artist}", "WARNING")

            if self.skip_all_duplicates:
                send_log(f"已执行全局跳过，删除新下载文件: {new_name}")
                os.remove(file_path)
                return

            if self.root:
                user_choice = send_duplicate_query(new_path, safe_title, safe_artist)
            else:
                user_choice = False

            if user_choice is True:
                send_log(f"用户选择覆盖，正在重新下载: {safe_title}")
                try:
                    if os.path.abspath(new_path) != os.path.abspath(file_path):
                        os.remove(new_path)
                except Exception as e:
                    send_log(f"删除旧文件失败: {e}", "ERROR")
                    os.remove(file_path)
                    return
            elif user_choice is False:
                send_log(f"用户选择跳过，删除新文件: {safe_title}")
                os.remove(file_path)
                return
            else:  # None 表示全部跳过
                send_log("用户选择后续全部跳过重复文件")
                self.skip_all_duplicates = True
                os.remove(file_path)
                return

        # 重命名
        try:
            os.rename(file_path, new_path)
            send_log(f"已重命名为: {new_name}")
        except Exception as e:
            send_log(f"文件重命名失败: {e}", "ERROR")
            return

        # 更新任务标题
        if self.current_bvid and safe_title:
            self._update_task(self.current_bvid, title=safe_title)

        # 嵌入歌词
        if self.progress_callback:
            self.progress_callback(f"正在写入歌词: {safe_title}")

        # 获取语言设置
        lang = self.lyrics_lang.get() if hasattr(self.lyrics_lang, 'get') else self.lyrics_lang
        if lang is None:
            lang = "none"
        success = embed_lyrics(new_path, safe_title, safe_artist, lang=lang)
        if success:
            send_log(f"歌词嵌入成功: {safe_title}")
        else:
            send_log(f"歌词未找到（可使用 LDDC 补漏）: {safe_title}")

    # ---------- 进度回调 ----------
    def _hook(self, d):
        if self.cancel_flag:
            raise Exception("下载已取消")

        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '').strip('%')
            try:
                percent = float(percent_str) if percent_str else 0.0
            except ValueError:
                percent = 0.0
            if self.current_bvid:
                self._update_task(self.current_bvid, progress=percent)
            if self.progress_callback:
                speed = d.get('_speed_str', '')
                self.progress_callback(f"下载中: {percent:.1f}% - {speed}")
        elif d['status'] == 'finished':
            if self.progress_callback:
                self.progress_callback("下载完成，正在处理...")