"""
采集 TapTap 热门话题（hashtags）
URL: https://www.taptap.cn/forum/hot/hashtags
"""
import re
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

def collect() -> list[dict]:
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.taptap.cn/forum/hot/hashtags",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.taptap.cn/",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[TapTap] 采集失败: {e}")
        return []

    results = []

    # 尝试从 HTML 中提取 JSON 数据
    # TapTap 的话题数据通常在 window.__INITIAL_STATE__ 或 JSON 数据块中
    json_matches = re.findall(
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        html, re.DOTALL
    )
    if json_matches:
        try:
            state = json.loads(json_matches[0])
            # 遍历数据结构找到话题列表
            topics = _extract_topics(state)
            for t in topics:
                results.append(_format(t, "TapTap"))
        except json.JSONDecodeError:
            pass

    # fallback: 从 HTML 中正则提取话题
    if not results:
        results = _fallback_parse(html)

    print(f"[TapTap] 采集到 {len(results)} 条话题")
    return results


def _extract_topics(state: dict, path: str = "") -> list:
    """递归查找 state 中的话题列表"""
    if isinstance(state, list):
        items = []
        for i, item in enumerate(state):
            items.extend(_extract_topics(item, f"{path}[{i}]"))
        return items
    if isinstance(state, dict):
        # 命中话题结构：有 title / name 且有 url/link
        if "title" in state and "id" in state and "description" in state:
            return [state]
        items = []
        for k, v in state.items():
            items.extend(_extract_topics(v, f"{path}.{k}"))
        return items
    return []


def _fallback_parse(html: str) -> list:
    """从 HTML 中正则提取话题标题和描述"""
    results = []
    # 匹配 <a class="topic-name">标题</a> 类似结构
    matches = re.findall(
        r'<a[^>]+href=["\'](/forum/topic/[^"\']+)["\'][^>]*>\s*([^<]{2,50})\s*</a>',
        html
    )
    seen = set()
    for url, title in matches:
        title = title.strip()
        if not title or title in seen:
            continue
        if any(kw in title for kw in ["登录", "注册", "下载", "APP", "官方"]):
            continue
        seen.add(title)
        results.append({
            "title": title,
            "url": f"https://www.taptap.cn{url}",
            "summary": "",
        })
    return results[:20]  # 最多 20 条


def _format(item: dict, source: str) -> dict:
    title = item.get("title") or item.get("name", "")
    summary = item.get("description", "")
    url = item.get("url") or item.get("link", "")
    if url and not url.startswith("http"):
        url = f"https://www.taptap.cn{url}"
    return {
        "title":   title,
        "url":     url,
        "summary": summary,
        "source":  source,
    }


if __name__ == "__main__":
    data = collect()
    print(json.dumps(data, ensure_ascii=False, indent=2))
