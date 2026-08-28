import asyncio
import aiohttp
import re
import os

# 直播源链接列表
PLAYLIST_URLS = [
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/index.m3u",
    "https://live.zbds.top/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8"
]

LOCAL_SOURCES = "sources.m3u"
OUTPUT_FILE = "playlist.m3u"

# 【极致精简白名单】只精准匹配这三个频道，严格排除 originals 等其他杂音
TARGET_CHANNELS = [
    {
        "name": "CCTV 2", 
        "keywords": ["cctv 2", "cctv2", "中央电视台财经", "cctv-2"]
    },
    {
        "name": "Bloomberg TV", 
        "keywords": ["bloomberg tv", "bloomberg television"]
    },
    {
        "name": "CNN International", 
        "keywords": ["cnn international", "cnn int"]
    }
]

async def fetch_playlist(session, url):
    try:
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
                
                name_lower = name.lower()
                
                # 严格过滤掉带有 originals 或 original 的频道
                if "originals" in name_lower or "original" in name_lower:
                    i += 1
                    continue
                
                # 匹配目标白名单（必须严格符合这三个频道之一）
                matched_category = None
                for target in TARGET_CHANNELS:
                    # 检查所有关键词
                    if any(kw in name_lower for kw in target["keywords"]):
                        # 额外保险：如果是 Bloomberg 或 CNN，确保不会误伤其他衍生频道
                        if "bloomberg" in target["name"].lower() and "bloomberg" not in name_lower:
                            continue
                        if "cnn" in target["name"].lower() and "cnn" not in name_lower:
                            continue
                        
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
        print("开始从多源抓取，并严格筛选 CCTV-2、Bloomberg、CNN...")
        
        fetch_tasks = [fetch_playlist(session, url) for url in PLAYLIST_URLS]
        raw_results = await asyncio.gather(*fetch_tasks)

        all_channels = []
        for raw_text in raw_results:
            if raw_text:
                all_channels += parse_m3u(raw_text)

        if os.path.exists(LOCAL_SOURCES):
            print("发现本地 sources.m3u，一并进行白名单过滤...")
            with open(LOCAL_SOURCES, 'r', encoding='utf-8') as f:
                local_raw = f.read()
                all_channels += parse_m3u(local_raw)

        # URL 去重
        all_channels_dict = {ch["url"]: ch for ch in all_channels}
        channels_to_check = list(all_channels_dict.values())
        print(f"初筛后共锁定 {len(channels_to_check)} 个目标候选源，开始网络连通性测试...")

        tasks = [verify_stream(session, ch) for ch in channels_to_check]
        results = await asyncio.gather(*tasks)

        valid_channels = [ch for ch in results if ch is not None]
        print(f"检测完成！最终有效频道数: {len(valid_channels)} 个。正在写入 {OUTPUT_FILE}...")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in valid_channels:
                f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n')
        print("精简更新完毕！")

if __name__ == "__main__":
    asyncio.run(main())
