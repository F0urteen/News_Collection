"""
采集 B站（bilibili）各区热榜
API: https://api.bilibili.com/x/web-interface/ranking/v2
同时拉取：动画、游戏、番剧、生活、影视
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

BILI_RANK_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"

# B站分区 ID（rid）
ZONES = {
    "动画":    1,
    "游戏":    4,
    "番剧":    13,
    "生活":    160,
    "影视":    181,
}

CATEGORY_MAP = {
    1:  "动漫",   # 动画
    4:  "游戏",   # 游戏
    13: "动漫",   # 番剧
    160: "泛娱乐", # 生活
    181: "影视",  # 影视
}


def collect() -> list[dict]:
    try:
        import urllib.request
        results = []
        seen = {}

        for zone_name, rid in ZONES.items():
            url = f"{BILI_RANK_URL}?rid={rid}"
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://www.bilibili.com/",
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if data.get("code") != 0:
                    print(f"[B站] {zone_name} 请求失败: {data.get('message')}")
                    continue

                video_list = data["data"]["list"]
                for v in video_list[:5]:  # 每区取前5
                    bvid = v.get("bvid", "")
                    if bvid in seen:
                        continue
                    seen[bvid] = True
                    title = v.get("title", "")
                    desc = v.get("desc", "")[:120]
                    link = f"https://www.bilibili.com/video/{bvid}"
                    results.append({
                        "title":   title,
                        "url":     link,
                        "summary": f"播放:{v.get('stat',{}).get('view',0)} 点赞:{v.get('stat',{}).get('like',0)} | {desc}",
                        "source":  "B站",
                        "category": CATEGORY_MAP.get(rid, "泛娱乐"),
                    })
            except Exception as e:
                print(f"[B站] {zone_name} 采集失败: {e}")

        print(f"[B站] 采集到 {len(results)} 条热榜内容")
        return results

    except Exception as e:
        print(f"[B站] 整体失败: {e}")
        return []


if __name__ == "__main__":
    data = collect()
    print(json.dumps(data, ensure_ascii=False, indent=2))
