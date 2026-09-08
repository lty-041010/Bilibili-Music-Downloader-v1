# utils.py
import re
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, USLT
from config import HEADERS

from opencc import OpenCC
cc_t2s = OpenCC('t2s')  # 繁体转简体
cc_s2t = OpenCC('s2t')  # 简体转繁体

def clean_noise_text(text: str) -> str:
    s = text
    # 1. 强行移除所有带连字符的垃圾词（如 Hi-Res, 无损音质等）
    s = re.sub(r"Hi‑Res|hi‑res|无损音质|百万级豪华录音棚试听|3D环绕|母带|动态歌词|官方MV|歌词纯享版", "", s,
               flags=re.IGNORECASE)

    # 2. 强力移除所有括号及其内部内容：【】、[]、()、（）、「」、『』
    s = re.sub(r"[【\[\(（「『][^】\]\)）」』]*[】\]\)）」』]", "", s)

    # 3. 移除各种引号内的内容
    s = re.sub(r"“.*?”", "", s)
    s = re.sub(r"「.*?」", "", s)

    # 4. 移除尾部 _1 等数字后缀
    s = re.sub(r"_\d+$", "", s)

    # 5. 统一空格
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_filename(fname: str):
    # 移除临时前缀和扩展名
    name_no_ext = fname.replace("temp_", "").rsplit(".mp3", 1)[0]
    clean_str = clean_noise_text(name_no_ext)

    # 1. 【最准的方案】：如果有《》，直接取《》里的内容作为纯歌名，忽略前后所有垃圾信息！
    book_ret = re.search(r"《(.*?)》", clean_str)
    if book_ret:
        return book_ret.group(1).strip(), ""

    # 2. 使用 - 分割，但严格限制只分割一次 (maxsplit=1) 防止越界
    parts = re.split(r"[-‑—]", clean_str, maxsplit=1)
    if len(parts) == 2:
        a, b = parts[0].strip(), parts[1].strip()
        if not a:
            return b, ""
        if not b:
            return a, ""
        # 通常歌名较长，歌手较短，据此判断
        if len(a) >= len(b):
            return a, b
        else:
            return b, a

    # 3. 如果分割后依然超过 2 个部分（可能类似【Hi-Res无损】的连字符没被清洗掉）
    parts = re.split(r"[-‑—]", clean_str)
    if len(parts) > 2:
        # 只取最后一段作为歌名，前面的全部忽略
        return parts[-1].strip(), ""

    # 4. 纯歌名
    return clean_str, ""


# ===================== 多平台歌词获取（保底策略） =====================
def _get_from_lrclib(title, artist=""):
    try:
        url = "https://lrclib.net/api/search"
        params = {'q': f"{title} {artist}".strip()}
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            results = resp.json()
            if results:
                # 修改 utils.py 中的第73行
                return results[0].get('syncedLyrics') or results[0].get('plainLyrics')
    except Exception as e:
        print(f"Lrclib 请求失败: {e}")
    return None


def _get_netease(title, artist=""):
    try:
        search_url = "https://music.163.com/api/search/get"
        params = {'s': f"{title} {artist}".strip(), 'type': 1, 'limit': 1}
        resp = requests.get(search_url, params=params, headers=HEADERS, timeout=5)
        data = resp.json()
        if data.get('result') and data['result']['songs']:
            song_id = data['result']['songs'][0]['id']
            lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
            lyric_resp = requests.get(lyric_url, headers=HEADERS, timeout=5)
            lyric_data = lyric_resp.json()
            if 'lrc' in lyric_data and lyric_data['lrc'].get('lyric'):
                return lyric_data['lrc']['lyric']
    except Exception as e:
        print(f"网易云接口失败: {e}")
    return None


def _get_qq(title, artist=""):
    try:
        search_url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
        params = {'w': f"{title} {artist}".strip(), 'format': 'json', 'n': 1, 'p': 1}
        headers = {**HEADERS, 'Referer': 'https://y.qq.com/'}
        resp = requests.get(search_url, params=params, headers=headers, timeout=5)
        data = resp.json()
        if data['data']['song']['list']:
            song = data['data']['song']['list'][0]
            songmid = song.get('songmid')
            if songmid:
                lyric_url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                params = {'songmid': songmid, 'format': 'json', 'nobase64': 1}
                headers = {**HEADERS, 'Referer': 'https://y.qq.com/', 'Cookie': 'qqmusic_key=123'}
                lyric_resp = requests.get(lyric_url, params=params, headers=headers, timeout=5)
                lyric_data = lyric_resp.json()
                if lyric_data.get('lyric'):
                    return lyric_data['lyric']
    except Exception as e:
        print(f"QQ音乐接口失败: {e}")
    return None


def _get_kugou(title, artist=""):
    try:
        search_url = "https://songsearch.kugou.com/song_search_v2"
        params = {'keyword': f"{title} {artist}".strip(), 'page': 1, 'pagesize': 1}
        resp = requests.get(search_url, params=params, headers=HEADERS, timeout=5)
        data = resp.json()
        if data['data']['lists']:
            hash_value = data['data']['lists'][0]['FileHash']
            lyric_url = "https://www.kugou.com/yy/index.php?r=play/getdata&hash=" + hash_value
            lyric_resp = requests.get(lyric_url, headers=HEADERS, timeout=5)
            lyric_data = lyric_resp.json()
            if lyric_data['data'].get('lyrics'):
                return lyric_data['data']['lyrics']
    except Exception as e:
        print(f"酷狗接口失败: {e}")
    return None


def _get_kuwo(title, artist=""):
    try:
        search_url = "http://search.kuwo.cn/r.s"
        params = {
            'client': 'kt', 'bilibili_downloader': f"{title} {artist}".strip(), 'pn': 0, 'rn': 1,
            'uid': '', 'ver': 'kwplayer_ar_9.2.2.1', 'vipver': '1', 'show_copyright_off': '1',
            'newver': '1', 'ft': 'music', 'cluster': '0', 'strategy': '2012',
            'encoding': 'utf8', 'rformat': 'json', 'vermerge': '1', 'mobi': '1'
        }
        resp = requests.get(search_url, params=params, headers=HEADERS, timeout=5)
        data = resp.json()
        if isinstance(data, list) and data:
            music_id = data[0]['MUSICRID']
            rid = music_id.replace("MUSIC_", "")
            lyric_url = f"http://m.kuwo.cn/newh5/singles/songinfoandlrc?musicId={rid}"
            lyric_resp = requests.get(lyric_url, headers=HEADERS, timeout=5)
            lyric_data = lyric_resp.json()
            if lyric_data['data'].get('lrclist'):
                lines = lyric_data['data']['lrclist']
                return "\n".join([f"[{line['time']}]{line['lineLyric']}" for line in lines])
    except Exception as e:
        print(f"酷我接口失败: {e}")
    return None


def get_lyrics_multi_platform(title, artist=""):
    print(f"正在搜索歌词: {title} - {artist}")
    for func in [_get_from_lrclib, _get_netease, _get_qq, _get_kugou, _get_kuwo]:
        lyrics = func(title, artist)
        if lyrics:
            print(f"成功使用平台: {func.__name__}")
            return lyrics
    print("所有平台均未找到歌词")
    return None



def embed_lyrics(file_path, title, artist="", lang="simplified"):
    """
    嵌入歌词到 MP3 文件

    :param file_path: MP3 文件路径
    :param title: 歌曲标题
    :param artist: 歌手名（可选）
    :param lang: 歌词语言转换，可选 'simplified'（简体）、'traditional'（繁体）、'none'（不转换）
    :return: 是否成功
    """
    try:
        # 1. 获取歌词
        lyrics_text = get_lyrics_multi_platform(title, artist)
        if not lyrics_text:
            return False

        # 2. 简繁转换
        if lang == "simplified":
            lyrics_text = cc_t2s.convert(lyrics_text)
        elif lang == "traditional":
            lyrics_text = cc_s2t.convert(lyrics_text)
        # lang == "none" 则保持原样

        # 3. 嵌入标签
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()

        # 设置标题
        audio.tags.add(TIT2(encoding=3, text=title))
        # 设置艺术家
        if artist:
            audio.tags.add(TPE1(encoding=3, text=artist))
        # 移除旧的歌词（如果有）
        if audio.tags.getall("USLT"):
            audio.tags.delall("USLT")
        # 添加新歌词
        audio.tags.add(USLT(encoding=3, lang='chi', text=lyrics_text))
        audio.save()
        return True

    except Exception as e:
        print(f"歌词嵌入失败: {e}")
        return False