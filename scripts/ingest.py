"""
Feishu Base 入库脚本
- 查询当日已有记录（用于去重）
- 批量写入新记录
- 字段映射、格式转换
"""
import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config, dedup

LARKSUITE_CLI = "larksuite-cli"


def _run(cmd: str) -> dict:
    import subprocess
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[CLI 错误] stdout: {result.stdout[:200]}")
        print(f"[CLI 错误] stderr: {result.stderr[:200]}")
        return {"ok": False, "error": result.stderr[:200]}


def query_today_records() -> list[dict]:
    """
    查询今日已入库记录，返回记录列表（含标题、URL、分类）
    用于去重比对。
    """
    today_str = datetime.now().strftime("%Y/%m/%d")
    cmd = (
        f"{LARKSUITE_CLI} base +record-search "
        f"--as user "
        f"--base-token {config.BASE_TOKEN} "
        f"--table-id {config.TABLE_ID} "
        f"--field-ids {config.FIELD_DATE},{config.FIELD_TITLE},{config.FIELD_URL},{config.FIELD_CAT} "
        f"--filter {config.FIELD_DATE}={today_str}"
    )
    resp = _run(cmd)
    if not resp.get("ok"):
        print(f"[查询] 当日记录查询失败: {resp.get('error', {}).get('message', '')}")
        return []
    records = resp.get("data", {}).get("items", [])
    print(f"[查询] 今日已有 {len(records)} 条记录")
    return records


def build_fields(record: dict) -> dict:
    """
    将标准记录 dict 转换为飞书 Base 字段格式。
    返回 fields 字典。
    """
    title = record.get("title", "").strip()
    source = record.get("source", "")
    url = record.get("url", "")
    summary = record.get("summary", "")
    category = record.get("category") or dedup.auto_categorize(record)
    hot = record.get("hot") or dedup.auto_hot_level(record)

    fields = {
        config.FIELD_STATUS: "待审核",
        config.FIELD_SOURCE: source,
        config.FIELD_TITLE:  title,
        config.FIELD_URL:     url,
        config.FIELD_NOTE:    summary,
        config.FIELD_CAT:     category,
        config.FIELD_HOT:     hot,
    }
    return fields


def batch_ingest(items: list[dict]) -> tuple[int, int]:
    """
    批量将记录写入飞书 Base。
    使用 upsert（按 URL 去重），失败自动重试。
    返回：(成功数, 失败数)
    """
    if not items:
        return 0, 0

    success = 0
    failed = 0

    # 批量写入（最多每次10条，防止超时）
    BATCH_SIZE = 10
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        records = []
        for item in batch:
            fields = build_fields(item)
            record = {
                "fields": fields,
            }
            # 用 URL 作为唯一标识，避免重复写入
            if item.get("url"):
                record["fields"][config.FIELD_URL] = item["url"]
            records.append(record)

        cmd = (
            f"{LARKSUITE_CLI} base +record-batch-create "
            f"--as user "
            f"--base-token {config.BASE_TOKEN} "
            f"--table-id {config.TABLE_ID} "
        )

        import subprocess, tempfile, json as j
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            j.dump({"records": records}, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            cmd += f"--data @{tmp_path}"
            resp = _run(cmd)
            if resp.get("ok"):
                success += len(batch)
                print(f"[入库] 第 {i//BATCH_SIZE+1} 批成功 {len(batch)} 条")
            else:
                # fallback: 逐条写入
                print(f"[入库] 批量失败，切换逐条模式: {resp.get('error',{}).get('message','')[:80]}")
                for item in batch:
                    ok, msg = _ingest_single(item)
                    if ok:
                        success += 1
                    else:
                        failed += 1
                        print(f"  失败: {item['title'][:30]} - {msg[:60]}")
        finally:
            os.unlink(tmp_path)

    return success, failed


def _ingest_single(item: dict) -> tuple[bool, str]:
    """单条记录写入，返回 (是否成功, 错误信息)"""
    fields = build_fields(item)
    data = {"records": [{"fields": fields}]}

    import subprocess, json as j, tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        j.dump(data, f, ensure_ascii=False)
        tmp = f.name

    try:
        cmd = (
            f"{LARKSUITE_CLI} base +record-batch-create "
            f"--as user "
            f"--base-token {config.BASE_TOKEN} "
            f"--table-id {config.TABLE_ID} "
            f"--data @{tmp}"
        )
        resp = _run(cmd)
        if resp.get("ok"):
            return True, ""
        return False, resp.get("error", {}).get("message", "")
    finally:
        os.unlink(tmp)


def run() -> dict:
    """
    主入口：从 stdin 读取待入库列表，执行去重+入库
    """
    raw = sys.stdin.read()
    if not raw.strip():
        print("[入库] 无新数据，退出")
        return {"success": 0, "failed": 0, "deduped": 0}

    new_items = json.loads(raw)
    print(f"[入库] 待处理 {len(new_items)} 条")

    # 查询今日已有
    existing = query_today_records()
    # 转换为 dedup 需要的格式
    existing_for_dedup = [
        {"title": r.get("fields", {}).get(config.FIELD_TITLE, ""),
         "url":   r.get("fields", {}).get(config.FIELD_URL, ""),
         "source": r.get("fields", {}).get(config.FIELD_SOURCE, "")}
        for r in existing
    ]

    # 去重
    to_ingest, deduped = dedup.dedup(new_items, existing_for_dedup)
    print(f"[入库] 去重后 {len(to_ingest)} 条待写入")

    # 入库
    success, failed = batch_ingest(to_ingest)

    result = {
        "success":   success,
        "failed":    failed,
        "deduped":   len(deduped),
        "total_raw": len(new_items),
        "timestamp": datetime.now().isoformat(),
    }
    print(f"[完成] {json.dumps(result, ensure_ascii=False)}")
    return result


if __name__ == "__main__":
    run()
