#!/usr/bin/env python3
"""
主采集脚本
依次调用各数据源 → 合并 → 传给 ingest.py 入库
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加 scripts 目录到 path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_taptap
import collect_bilibili
import collect_kaola
import ingest


def main():
    print(f"========== 新闻采集开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==========")
    all_items = []

    # 1. 采集 TapTap
    print("\n[Step 1] TapTap 热门话题")
    taptap_items = collect_taptap.collect()
    all_items.extend(taptap_items)

    # 2. 采集 B站热榜
    print("\n[Step 2] B站热榜")
    bili_items = collect_bilibili.collect()
    all_items.extend(bili_items)

    # 3. 采集 贴吧/微博/抖音/头条
    print("\n[Step 3] 考拉导航（贴吧/微博/抖音/头条）")
    kaola_items = collect_kaola.collect()
    all_items.extend(kaola_items)

    # 4. 合并写入临时文件，传递给 ingest
    tmp_file = SCRIPT_DIR / "collected.json"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False)

    print(f"\n[汇总] 共采集 {len(all_items)} 条原始数据")
    print(f"已保存到 {tmp_file}")

    # 5. 入库（通过 stdin 传递）
    print("\n[Step 4] 入库飞书 Base")
    with open(tmp_file, "r", encoding="utf-8") as f:
        raw = f.read()
    # 用环境变量告诉 ingest 用 larksuite-cli 路径
    os.environ["LARKSUITE_CLI"] = os.environ.get("LARKSUITE_CLI", "larksuite-cli")

    # 直接调用 ingest.run()
    sys.stdin = open(tmp_file, "r", encoding="utf-8")
    result = ingest.run()
    sys.stdin.close()

    # 6. 写入结果摘要
    summary_file = SCRIPT_DIR / "result.json"
    result["total_collected"] = len(all_items)
    result["sources"] = {
        "taptap":  len(taptap_items),
        "bilibili": len(bili_items),
        "kaola":   len(kaola_items),
    }
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n========== 采集完成 ==========")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
