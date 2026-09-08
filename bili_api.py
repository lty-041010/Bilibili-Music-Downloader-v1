# bili_api.py
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import HEADERS


class BiliAPI:
    def __init__(self, session):
        self.session = session
        # 配置重试策略：最多重试3次，退避因子0.5，对连接错误和状态码429/500/502/503/504重试
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def get_user_info(self):
        resp = self.session.get('https://api.bilibili.com/x/web-interface/nav', timeout=10)
        data = resp.json()
        if data['code'] == 0 and data['data'].get('isLogin'):
            return data['data']
        return None

    def get_all_folders(self, uid):
        url = 'https://api.bilibili.com/x/v3/fav/folder/created/list-all'
        params = {'up_mid': uid}
        resp = self.session.get(url, params=params, timeout=10)
        data = resp.json()
        if data['code'] != 0:
            raise Exception(f"获取收藏夹列表失败: {data['message']}")
        return data['data']['list']

    def get_folder_videos(self, media_id):
        videos = []
        page = 1
        while True:
            url = 'https://api.bilibili.com/x/v3/fav/resource/list'
            params = {'media_id': media_id, 'pn': page, 'ps': 20, 'keyword': '',
                      'order': 'mtime', 'type': 0, 'tid': 0, 'platform': 'web'}
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            if data['code'] != 0:
                break
            medias = data['data']['medias']
            if not medias:
                break
            for item in medias:
                videos.append({
                    'title': item['title'],
                    'bvid': item['bvid'],
                    'up': item['upper']['name'],
                    'duration': item['duration'],
                    'favorite_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item['fav_time']))
                })
            if not data['data']['has_more']:
                break
            page += 1
            time.sleep(0.3)
        return videos