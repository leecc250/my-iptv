import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

CONFIG_FILE = "config.json"
OUTPUT_FILE = "playlist.m3u"
TIMEOUT = 4  # 单个频道超时时间（秒）
MAX_THREADS = 15  # 并发检测线程数


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sources": [], "keywords": [], "custom_sources_file": "sources.m3u"}


def fetch_m3u_from_url(url):
    print(f"正在拉取远程网络源: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        print(f"  [X] 拉取失败 {url}: {e}")
    return ""


def parse_m3u(content, keywords):
    """解析 M3U 内容，筛选包含指定关键词的频道"""
    channels = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = line
            i += 1
            if i < len(lines):
                stream_url = lines[i].strip()
                if stream_url and not stream_url.startswith("#"):
                    channel_name = extinf.split(",")[-1]
                    if not keywords or any(
                        kw.lower() in channel_name.lower()
                        for kw in keywords
                    ):
                        channels.append((extinf, stream_url))
        i += 1
    return channels


def check_channel_worker(item):
    """单个频道连通性测试"""
    extinf, url = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
        if res.status_code in [200, 206, 301, 302]:
            return True, extinf, url
    except Exception:
        pass
    return False, extinf, url


def main():
    config = load_config()
    raw_channels = []

    # 1. 拉取并解析所有在线网络源
    for url in config.get("sources", []):
        content = fetch_m3u_from_url(url)
        if content:
            matched = parse_m3u(content, config.get("keywords", []))
            raw_channels.extend(matched)

    # 2. 读取本地自定义源
    custom_file = config.get("custom_sources_file", "sources.m3u")
    if os.path.exists(custom_file):
        print(f"正在读取本地自定义源: {custom_file}")
        with open(custom_file, "r", encoding="utf-8") as f:
            custom_channels = parse_m3u(f.read(), [])
            raw_channels.extend(custom_channels)

    print(
        f"\n筛选完成，共获得 {len(raw_channels)} 个候选频道，开始并发连通性测试..."
    )

    # 3. 按 URL 去重
    unique_channels = {}
    for extinf, url in raw_channels:
        if url not in unique_channels:
            unique_channels[url] = extinf

    items_to_test = [(extinf, url) for url, extinf in unique_channels.items()]

    # 4. 多线程并发检测
    valid_channels = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [
            executor.submit(check_channel_worker, item)
            for item in items_to_test
        ]
        for future in as_completed(futures):
            is_valid, extinf, url = future.result()
            name = extinf.split(",")[-1]
            if is_valid:
                print(f"  [✓ 成功] {name}")
                valid_channels.append((extinf, url))
            else:
                print(f"  [X 失败] {name}")

    # 5. 写入最终文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for extinf, url in valid_channels:
            f.write(f"{extinf}\n{url}\n")

    print(
        f"\n任务完成！最终保留 {len(valid_channels)} 个有效频道，已更新至 {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
