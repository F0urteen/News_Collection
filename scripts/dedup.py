"""
去重逻辑：
1. 用 Levenshtein 距离判断标题相似度（阈值 0.85）
2. 同时检查 URL 是否相同
3. 检查过去 N 天内是否已入库（避免热点连续多天重复出现）
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
import config

def _levenshtein_ratio(s1: str, s2: str) -> float:
    """计算两个字符串的相似度（0~1），越接近1越相似"""
    s1, s2 = s1.strip(), s2.strip()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    len1, len2 = len(s1), len(s2)
    # 简单优化：长度差异过大直接返回0
    if abs(len1 - len2) > max(len1, len2) * 0.4:
        return 0.0

    # 动态规划
    dp = [[0] * (len2 + 1) for _ in range(2)]
    for j in range(len2 + 1):
        dp[0][j] = j
    for i in range(1, len1 + 1):
        dp[i % 2][0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            dp[i % 2][j] = min(
                dp[(i-1) % 2][j] + 1,        # 删除
                dp[i % 2][j-1] + 1,          # 插入
                dp[(i-1) % 2][j-1] + cost,   # 替换
            )
    distance = dp[len1 % 2][len2]
    max_len = max(len1, len2)
    return 1.0 - distance / max_len


def _keyword_similarity(s1: str, s2: str) -> float:
    """基于关键词集合的相似度"""
    words1 = set(s1) - set("，。！？、：；（）【】《》""''")
    words2 = set(s2) - set("，。！？、：；（）【】《》""''")
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    return len(intersection) / min(len(words1), len(words2))


def is_duplicate(new_item: dict, existing: list[dict]) -> bool:
    """
    判断 new_item 是否与已有记录重复。
    重复条件：标题相似度 > 0.8 或 URL 完全相同
    """
    new_title = new_item.get("title", "")
    new_url   = new_item.get("url", "")

    for exist in existing:
        # URL 精确匹配
        if new_url and exist.get("url") == new_url:
            return True

        # 标题相似度
        exist_title = exist.get("title", "")
        ratio = _levenshtein_ratio(new_title, exist_title)
        kw_ratio = _keyword_similarity(new_title, exist_title)

        if ratio > 0.80 or kw_ratio > 0.85:
            return True

    return False


def dedup(new_items: list[dict], existing_today: list[dict] = None) -> tuple[list[dict], list[dict]]:
    """
    对新采集内容去重。
    返回：(入库列表, 被过滤列表)
    """
    existing = existing_today or []
    to_ingest = []
    filtered = []

    for item in new_items:
        if is_duplicate(item, existing + to_ingest):
            filtered.append(item)
        else:
            to_ingest.append(item)

    if filtered:
        print(f"[去重] 过滤 {len(filtered)} 条重复内容")
        for f in filtered:
            print(f"    过滤: {f['title'][:40]} (来源:{f.get('source','')})")

    return to_ingest, filtered


def auto_categorize(item: dict) -> str:
    """根据标题/摘要关键词自动分类"""
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    for cat, keywords in config.CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                return cat
    return "泛娱乐"


def auto_hot_level(item: dict) -> str:
    """根据热度数值自动判断热度等级"""
    summary = item.get("summary", "")
    import re
    # 提取热度值
    match = re.search(r'热度[:：]?(\d+)', summary)
    if match:
        val = int(match.group(1))
        if val > 100000:
            return config.HOT_HIGH
        elif val > 10000:
            return config.HOT_MED
        else:
            return config.HOT_LOW
    # 根据正文长度
    text_len = len(item.get("summary", ""))
    if text_len > 100:
        return config.HOT_MED
    return config.HOT_LOW


if __name__ == "__main__":
    # 测试
    test_items = [
        {"title": "尘白禁区5月8日重开服", "url": "https://example.com/1", "summary": "测试1", "source": "贴吧"},
        {"title": "尘白禁区开服公告", "url": "https://example.com/2", "summary": "测试2", "source": "头条"},
    ]
    ingested, filtered = dedup(test_items, [])
    print(f"入库: {len(ingested)}, 过滤: {len(filtered)}")
