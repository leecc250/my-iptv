import asyncio
import aiohttp
import re
import os

# iptv-org 官方分类源
URL_HK = "https://iptv-org.github.io/iptv/countries/hk.m3u"       
URL_BUSINESS = "https://iptv-org.github.io/iptv/categories/business.m3u"  
URL_NEWS = "https://iptv-org.github.io/iptv/categories/news.m3u"          

# 适配你现有仓库的文件名
LOCAL_SOURCES = "sources.m3u"
OUTPUT_FILE = "playlist.m3u"

async def fetch_playlist(session, url):
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        print(f"[-] 读取播放列表失败 [{url}]: {e}")
    return ""

def parse_m3u(m3u_text, default_group="Finance"):
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
                channels.append({"info": info, "name": name, "url": stream_url, "group": default_group})
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
                    print(f"[✓ 有效] {channel['name']}")
                    return channel
    except Exception:
        pass
    print(f"[× 无效] {channel['name']}")
    return None

async def main():
    async with aiohttp.ClientSession() as session:
        print("开始抓取网络源...")
        hk_raw = await fetch_playlist(session, URL_HK)
        biz_raw = await fetch_playlist(session, URL_BUSINESS)
        news_raw = await fetch_playlist(session, URL_NEWS)

        all_channels = parse_m3u(hk_raw, default_group="Hong Kong") + \
                       parse_m3u(biz_raw, default_group="Business") + \
                       parse_m3u(news_raw, default_group="News")

        # 读取你仓库里的本地 sources.m3u (如果存在)
        if os.path.exists(LOCAL_SOURCES):
            print("发现本地 sources.m3u，加入检测队列...")
            with open(LOCAL_SOURCES, 'r', encoding='utf-8') as f:
                local_raw = f.read()
                all_channels += parse_m3u(local_raw, default_group="My Custom")

        # 根据 URL 去重
        all_channels_dict = {ch["url"]: ch for ch in all_channels}
        channels_to_check = list(all_channels_dict.values())
        print(f"共汇总 {len(channels_to_check)} 个独立频道，开始测试连通性...")

        # 并发检测
        tasks = [verify_stream(session, ch) for ch in channels_to_check]
        results = await asyncio.gather(*tasks)

        valid_channels = [ch for ch in results if ch is not None]
        print(f"检测完成！有效频道: {len(valid_channels)} 个。开始生成 {OUTPUT_FILE}...")

        # 覆盖写入你的 playlist.m3u
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in valid_channels:
                f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n')
        print("更新完毕！")

if __name__ == "__main__":
    asyncio.run(main())
