import asyncio
import aiohttp
import re
import os

# 1. 官方与聚合直播源链接列表
PLAYLIST_URLS = [
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/index.m3u", # 全球完整索引
    "https://live.zbds.top/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8"
]

LOCAL_SOURCES = "sources.m3u"
OUTPUT_FILE = "playlist.m3u"

# 核心白名单规则：只允许匹配以下关键词的频道通过
TARGET_CHANNELS = [
    {"name": "CCTV财经", "keywords": ["cctv 2", "cctv-2", "cctv2"]},
    {"name": "Bloomberg TV", "keywords": ["bloomberg"]},
    {"name": "CNN International", "keywords": ["cnn"]},
    {"name": "Hong Kong Finance", "keywords": ["now business", "cable tv finance", "hk", "hong kong", "香港", "财经"]}, 
    {"name": "Singapore Finance", "keywords": ["singapore", "channel newsasia", "cna", "新加坡"]},
    {"name": "UK Finance", "keywords": ["bbc news", "skynews", "uk", "british", "bloomberg uk"]}
]

async def fetch_playlist(session, url):
    try:
        # 针对部分大文件（如 index.m3u 较大），适当延长超时时间
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        print(f"[-] 读取播放列表失败 [{url}]: {e}")
    return ""

def parse_m3u(m3u_text):
    channels = []
    lines = m3u_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            info = line
            if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                stream_url = lines[i+1].strip()
                name_match = re.search(r',([^,]+)$', info)
                name = name_match.group(1).strip() if name_match else "Unknown Channel"
                
                # 检查该频道是否在我们的目标白名单中
                matched_category = None
                name_lower = name.lower()
                
                for target in TARGET_CHANNELS:
                    if any(kw in name_lower for kw in target["keywords"]):
                        matched_category = target["name"]
                        break
                
                if matched_category:
                    channels.append({
                        "info": info, 
                        "name": name, 
                        "url": stream_url, 
                        "group": matched_category
                    })
                i += 1
        i += 1
    return channels

async def verify_stream(session, channel, timeout=5):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with session.get(channel["url"], headers=headers, timeout=timeout, allow_redirects=True) as resp:
            if resp.status == 200:
                content = await resp.content.read(512)
                content_str = content.decode('utf-8', errors='ignore')
                if "#EXTM3U" in content_str or resp.content_type in ["application/x-mpegurl", "application/vnd.apple.mpegurl", "video/mp2t"]:
                    print(f"[✓ 有效] {channel['group']} -> {channel['name']}")
                    return channel
    except Exception:
        pass
    print(f"[× 无效] {channel['name']}")
    return None

async def main():
    async with aiohttp.ClientSession() as session:
        print("开始从多个扩展源并发拉取数据...")
        
        # 并发抓取所有的外部源
        fetch_tasks = [fetch_playlist(session, url) for url in PLAYLIST_URLS]
        raw_results = await asyncio.gather(*fetch_tasks)

        all_channels = []
        for raw_text in raw_results:
            if raw_text:
                all_channels += parse_m3u(raw_text)

        # 读取本地 sources.m3u (如果存在)
        if os.path.exists(LOCAL_SOURCES):
            print("发现本地 sources.m3u，一并进行白名单过滤...")
            with open(LOCAL_SOURCES, 'r', encoding='utf-8') as f:
                local_raw = f.read()
                all_channels += parse_m3u(local_raw)

        # URL 去重
        all_channels_dict = {ch["url"]: ch for ch in all_channels}
        channels_to_check = list(all_channels_dict.values())
        print(f"初筛后共锁定 {len(channels_to_check)} 个目标候选源，开始网络连通性检测...")

        # 检测有效性
        tasks = [verify_stream(session, ch) for ch in channels_to_check]
        results = await asyncio.gather(*tasks)

        valid_channels = [ch for ch in results if ch is not None]
        print(f"检测完成！最终有效频道: {len(valid_channels)} 个。正在写入 {OUTPUT_FILE}...")

        # 写入最终的 m3u 文件
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in valid_channels:
                f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n')
        print("多源整合更新完毕！")

if __name__ == "__main__":
    asyncio.run(main())
