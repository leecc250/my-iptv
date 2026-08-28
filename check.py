import asyncio
import aiohttp
import re
import os

# 直播源链接列表
PLAYLIST_URLS = [
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%9B%BD%E5%A4%96%E7%94%B5%E8%A7%86%E5%8F%B0202409.m3u",
    "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
    "https://live.hacks.tools/iptv/index.m3u",
    "https://raw.githubusercontent.com/cs3306/IPTV-Sources/main/data/output/iptv_collection.m3u",
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://live.zbds.top/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8"
]

LOCAL_SOURCES = "sources.m3u"
OUTPUT_FILE = "playlist.m3u"

# 【更新后的白名单】对应你所要求的名称和关键词分类
TARGET_CHANNELS = [
    # 国际与央媒财经
    {
        "name": "CCTV 2", 
        "keywords": ["cctv 2", "cctv2", "中央电视台财经", "cctv-2"]
    },
    {
        "name": "Bloomberg TV", 
        "keywords": ["bloomberg tv", "bloomberg television", "bloomberg"]
    },
    {
        "name": "CNN International", 
        "keywords": ["cnn international", "cnn int", "cnn"]
    },
    {
        "name": "CNBC", 
        "keywords": ["cnbc", "cnbc usa", "cnbc europe", "cnbc asia"]
    },
    {
        "name": "Fox Business", 
        "keywords": ["fox business", "fbn"]
    },
    {
        "name": "Reuters TV", 
        "keywords": ["reuters", "reuters tv", "路透"]
    },
    # 国内财经电视与直播间
    {
        "name": "CBN", 
        "keywords": ["第一财经", "cbn", "第一财经电视"]
    },
    {
        "name": "东方财经", 
        "keywords": ["东方财经", "浦东频道", "东方财经浦东"]
    },
    {
        "name": "深圳财经", 
        "keywords": ["深圳财经", "深圳财经生活"]
    },
    {
        "name": "新浪财经直播", 
        "keywords": ["新浪财经", "新浪直播"]
    },
    {
        "name": "腾讯财经直播", 
        "keywords": ["腾讯财经", "腾讯直播"]
    },
    {
        "name": "同花顺直播间", 
        "keywords": ["同花顺", "同花顺直播"]
    },
    {
        "name": "东方财富直播间", 
        "keywords": ["东方财富", "东方财富直播"]
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
                
                # 严格过滤掉带有 originals 或 original 的杂音
                if "originals" in name_lower or "original" in name_lower:
                    i += 1
                    continue
                
                # 匹配目标白名单
                matched_category = None
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
        print("开始从多源抓取，并按新规则精准筛选...")
        
        fetch_tasks = [fetch_playlist(session, url) for url in PLAYLIST_URLS]
        raw_results = await asyncio.gather(*fetch_tasks)

        all_channels = []
        for raw_text in raw_results:
            if raw_text:
                all_channels += parse_m3u(raw_text)

        if os.path.exists(LOCAL_SOURCES):
            with open(LOCAL_SOURCES, 'r', encoding='utf-8') as f:
                local_raw = f.read()
                all_channels += parse_m3u(local_raw)

        all_channels_dict = {ch["url"]: ch for ch in all_channels}
        channels_to_check = list(all_channels_dict.values())
        print(f"初筛后共锁定 {len(channels_to_check)} 个候选源，开始连通性测试...")

        tasks = [verify_stream(session, ch) for ch in channels_to_check]
        results = await asyncio.gather(*tasks)

        valid_channels = [ch for ch in results if ch is not None]
        print(f"检测完成！有效频道数: {len(valid_channels)} 个。正在写入 {OUTPUT_FILE}...")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in valid_channels:
                f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n')
        print("更新完毕！")

if __name__ == "__main__":
    asyncio.run(main())
