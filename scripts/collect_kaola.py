"""
采集 考拉导航 (kaolaflow.com) 整合热搜
考拉导航本身聚合了微博、抖音、贴吧、头条等热搜，
但我们直接对各平台原始接口采集，以保证数据新鲜度。

本模块采集：
1. 百度贴吧 热门话题
2. 微博 热搜 TOP20
3. 抖音 热点榜
4. 今日头条 热搜
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

def _fetch(url: str, headers: dict = None) -> str:
    import urllib.request
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="ignore")


# ── 1. 百度贴吧 热门话题 ──────────────────────────────────
def collect_tieba() -> list[dict]:
    """
    贴吧热话 API
    """
    results = []
    try:
        # 移动端接口，返回热话
        html = _fetch(
            "https://tieba.baidu.com/hottopic/browse/topicList",
            {"Referer": "https://tieba.baidu.com/"}
        )
        import re, json as j
        # 提取 JSON 数据
        m = re.search(r'"topic_list":\s*(\[.*?\])\s*,"', html, re.DOTALL)
        if m:
            items = j.loads(m.group(1))
            seen = set()
            for item in items[:15]:
                title = item.get("topic_name", "")
                url = f"https://tieba.baidu.com/topic/yz单向历/{item.get('topic_id','')}"
                tid = item.get("topic_id", "")
                if not title or tid in seen:
                    continue
                seen.add(tid)
                results.append({
                    "title":   title,
                    "url":     url,
                    "summary": f"讨论量:{item.get('discuss_count',0)}",
                    "source":  "百度贴吧",
                })
        print(f"[贴吧] 采集到 {len(results)} 条")
    except Exception as e:
        print(f"[贴吧] 失败: {e}")
    return results


# ── 2. 微博 热搜 TOP20 ────────────────────────────────────
def collect_weibo() -> list[dict]:
    results = []
    try:
        # 移动端热搜接口
        html = _fetch(
            "https://m.weibo.cn/api/container/getIndex?containerid=106003&page_type=1",
            {"Referer": "https://m.weibo.cn/"}
        )
        data = json.loads(html)
        cards = data.get("data", {}).get("cards", [])
        seen = set()
        for card in cards:
            for item in card.get("card_group", [])[:10]:
                title = item.get("desc", "")
                url = item.get("scheme", "")
                if not title or title in seen:
                    continue
                seen.add(title)
                results.append({
                    "title":   title,
                    "url":     url,
                    "summary": "",
                    "source":  "微博",
                })
        # 备用接口
        if not results:
            html2 = _fetch(
                "https://weibo.com/ajax/side/hotSearch",
                {"Referer": "https://weibo.com/"}
            )
            d = json.loads(html2)
            for item in d.get("data", {}).get("realtime", [])[:20]:
                title = item.get("word", "")
                url = f"https://s.weibo.com/weibo?q={title}"
                results.append({
                    "title":   title,
                    "url":     url,
                    "summary": f"热度:{item.get('raw_hot','')}",
                    "source":  "微博",
                })
        print(f"[微博] 采集到 {len(results)} 条")
    except Exception as e:
        print(f"[微博] 失败: {e}")
    return results


# ── 3. 抖音 热点榜 ────────────────────────────────────────
def collect_douyin() -> list[dict]:
    results = []
    try:
        html = _fetch(
            "https://www.douyin.com/aweme/v1/hot/search/list/?device_platform=webapp&aid=6383",
            {"Referer": "https://www.douyin.com/"}
        )
        data = json.loads(html)
        words = data.get("data", {}).get("word_list", [])
        seen = set()
        for w in words[:15]:
            title = w.get("word", "")
            url = f"https://www.douyin.com/search/{title}"
            wid = w.get("word_id", "")
            if not title or wid in seen:
                continue
            seen.add(wid)
            results.append({
                "title":   title,
                "url":     url,
                "summary": f"热度:{w.get('hot_value','')}",
                "source":  "抖音",
            })
        print(f"[抖音] 采集到 {len(results)} 条")
    except Exception as e:
        print(f"[抖音] 失败: {e}")
    return results


# ── 4. 今日头条 热搜 ──────────────────────────────────────
def collect_toutiao() -> list[dict]:
    results = []
    try:
        html = _fetch(
            "https://www.toutiao.com/c/article/hot_search/list/",
            {"Referer": "https://www.toutiao.com/"}
        )
        data = json.loads(html)
        items = data.get("data", [])
        seen = set()
        for item in items[:15]:
            title = item.get("title", "")
            url = item.get("open_url", "")
            tid = item.get("id", "")
            if not title or tid in seen:
                continue
            seen.add(tid)
            results.append({
                "title":   title,
                "url":     url,
                "summary": "",
                "source":  "今日头条",
            })
        print(f"[头条] 采集到 {len(results)} 条")
    except Exception as e:
        print(f"[头条] 失败: {e}")
    return results


# ── 主函数 ─────────────────────────────────────────────────
def collect() -> list[dict]:
    all_results = []
    all_results += collect_tieba()
    time.sleep(0.5)
    all_results += collect_weibo()
    time.sleep(0.5)
    all_results += collect_douyin()
    time.sleep(0.5)
    all_results += collect_toutiao()
    print(f"[考拉] 共 {len(all_results)} 条原始数据")
    return all_results


if __name__ == "__main__":
    data = collect()
    print(json.dumps(data, ensure_ascii=False, indent=2))
