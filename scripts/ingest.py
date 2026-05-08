"""
Feishu Base 入库脚本（直接调用 Open API，无需 larksuite-cli）
- 查询当日已有记录（用于去重）
- 批量写入新记录
- 使用 FEISHU_USER_TOKEN 环境变量认证
"""
import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config, dedup

FEISHU_API = "https://open.feishu.cn/open-apis"


def _api(method: str, path: str, token: str, data: dict = None) -> dict:
    """直接调用飞书 Open API"""
    import urllib.request
    url = f"{FEISHU_API}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
        if result.get("code") != 0:
            print(f"[API 错误] {method} {path}: {result.get('msg')}")
        return result


def _api_records_search(token: str, filter_str: str = None) -> list:
    """
    查询记录，支持 filter 条件
    返回记录列表
    """
    records = []
    page_token = None
    while True:
        params = {
            "page_size": 100,
            "field_ids": f"{config.FIELD_DATE},{config.FIELD_TITLE},{config.FIELD_URL},{config.FIELD_CAT},{config.FIELD_SOURCE}",
        }
        if filter_str:
            params["filter"] = filter_str
        if page_token:
            params["page_token"] = page_token

        query_str = "&".join(f"{k}={v}" for k, v in params.items())
        resp = _api("GET",
            f"/bitable/v1/apps/{config.BASE_TOKEN}/tables/{config.TABLE_ID}/records?{query_str}",
            token
        )
        if not resp.get("ok"):
            print(f"[查询] 失败: {resp.get('msg')}")
            break
        items = resp.get("data", {}).get("items", [])
        records.extend(items)
        has_more = resp.get("data", {}).get("has_more", False)
        if not has_more:
            break
        page_token = resp.get("data", {}).get("page_token")
        time.sleep(0.2)  # 避免频率限制

    return records


def query_today_records(token: str) -> list[dict]:
    """查询今日已入库记录，用于去重"""
    today_str = datetime.now().strftime("%Y/%m/%d")
    filter_str = f'AND(RECORD_DATETIME(\"{config.FIELD_DATE}\")=\"{today_str}\")'
    records = _api_records_search(token, filter_str)
    print(f"[查询] 今日已有 {len(records)} 条记录")
    return records


def batch_ingest(token: str, items: list[dict]) -> tuple[int, int]:
    """
    批量写入记录到飞书 Base
    返回：(成功数, 失败数)
    """
    if not items:
        return 0, 0

    success = 0
    failed = 0
    BATCH_SIZE = 10

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        records = []
        for item in batch:
            fields = build_fields(item)
            records.append({"fields": fields})

        resp = _api("POST",
            f"/bitable/v1/apps/{config.BASE_TOKEN}/tables/{config.TABLE_ID}/records/batch_create",
            token,
            {"records": records}
        )

        if resp.get("ok"):
            cnt = len(resp.get("data", {}).get("records", []))
            success += cnt
            print(f"[入库] 第 {i//BATCH_SIZE+1} 批成功 {cnt} 条")
        else:
            # 逐条 fallback
            print(f"[入库] 批量失败({resp.get('msg')})，切换逐条模式")
            for item in batch:
                ok, msg = _ingest_single(token, item)
                if ok:
                    success += 1
                else:
                    failed += 1
                    print(f"  失败: {item['title'][:30]} - {msg[:80]}")
        time.sleep(0.3)

    return success, failed


def _ingest_single(token: str, item: dict) -> tuple[bool, str]:
    """单条写入"""
    fields = build_fields(item)
    resp = _api("POST",
        f"/bitable/v1/apps/{config.BASE_TOKEN}/tables/{config.TABLE_ID}/records",
        token,
        {"fields": fields}
    )
    if resp.get("ok"):
        return True, ""
    return False, resp.get("msg", "")


def build_fields(record: dict) -> dict:
    """将标准记录 dict 转换为飞书字段格式"""
    source = record.get("source", "")
    url = record.get("url", "")
    summary = record.get("summary", "")
    category = record.get("category") or dedup.auto_categorize(record)
    hot = record.get("hot") or dedup.auto_hot_level(record)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = {
        config.FIELD_STATUS: "待审核",
        config.FIELD_SOURCE: source,
        config.FIELD_TITLE:  record.get("title", "").strip(),
        config.FIELD_URL:    url,
        config.FIELD_NOTE:   summary,
        config.FIELD_CAT:   category,
        config.FIELD_HOT:   hot,
        config.FIELD_DATE:  now,
    }
    return fields


def run():
    """主入口：读取 collected.json → 去重 → 入库"""
    token = os.environ.get("FEISHU_USER_TOKEN", "").strip()
    if not token:
        print("[错误] 缺少 FEISHU_USER_TOKEN 环境变量")
        sys.exit(1)

    # 读取采集结果
    SCRIPT_DIR = Path(__file__).parent
    raw_file = SCRIPT_DIR / "collected.json"
    if not raw_file.exists():
        print("[入库] 无新数据文件，退出")
        return

    with open(raw_file, "r", encoding="utf-8") as f:
        new_items = json.load(f)

    if not new_items:
        print("[入库] 无新数据，退出")
        return

    print(f"[入库] 待处理 {len(new_items)} 条")

    # 查询今日已有
    existing = query_today_records(token)
    existing_for_dedup = [
        {
            "title": r.get("fields", {}).get(config.FIELD_TITLE, ""),
            "url":   r.get("fields", {}).get(config.FIELD_URL, ""),
            "source": r.get("fields", {}).get(config.FIELD_SOURCE, ""),
        }
        for r in existing
    ]

    # 去重
    to_ingest, deduped = dedup.dedup(new_items, existing_for_dedup)
    print(f"[入库] 去重后 {len(to_ingest)} 条待写入")

    # 入库
    success, failed = batch_ingest(token, to_ingest)

    result = {
        "success":   success,
        "failed":    failed,
        "deduped":   len(deduped),
        "total_raw": len(new_items),
        "timestamp": datetime.now().isoformat(),
    }

    summary_file = SCRIPT_DIR / "result.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] {json.dumps(result, ensure_ascii=False)}")
    return result


if __name__ == "__main__":
    run()
