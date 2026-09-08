# Bilibili Music Downloader

一个用于下载 Bilibili 视频/音频的 Python 图形界面工具。

## 功能
- 登录 Bilibili 账号
- 搜索视频
- 下载音频/视频

## 安装与使用
1. 克隆本仓库
2. 安装依赖：`pip install -r requirements.txt`
3. 运行：`python main.py`

## 打包为 EXE
使用 PyInstaller：
```bash
pyinstaller -F -w --hidden-import=keyring main.py
