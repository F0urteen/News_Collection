"""
Feishu Base 入库脚本
- 获取 App Access Token（自动刷新）
- 查询当日已有记录（用于去重）
- 批量写入新记录
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
_app_token_cache = None
_app_token_expires_at = 0


def get_app_access_token() -> str:
    """获取 App Access Token，自动处理缓存"""
    global _app_token_cache, _app_token_expires_at

    # 缓存有效（提前 60s 刷新）
    if _app_token_cache and time.time() < _app_token_expires_at - 60:
        return _app_token_cache

    import urllib.request

    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()

    if not app_id or not app_secret:
        print("[认证] 缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
        sys.exit(1)

    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
        data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    if result.get("code") != 0:
        print(f"[认证失败] {result.get('msg')}")
        sys.exit(1)

    _app_token_cache = result["tenant_access_token"]
    _app_token_expires_at = time.time() + result.get("expire", 7200)
    print(f"[认证] App Access Token 获取成功，有效期 {result.get('expire', 7200)}s")
    return _app_token_cache


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


def _api_records_all(token: str) -> list:
    """查询全部记录，支持翻页（不再依赖 filter 参数）"""
    records = []
    page_token = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token

        query_str = "&".join(f"{k}={v}" for k, v in params.items())
        resp = _api("GET",
            f"/bitable/v1/apps/{config.BASE_TOKEN}/tables/{config.TABLE_ID}/records?{query_str}",
            token
        )
        if resp.get("code") != 0:
            print(f"[查询] 失败: {resp.get('msg')}")
            break
        items = resp.get("data", {}).get("items", [])
        records.extend(items)
        if not resp.get("data", {}).get("has_more"):
            break
        page_token = resp.get("data", {}).get("page_token")
        time.sleep(0.2)

    return records


def query_today_records(token: str) -> list[dict]:
    """查询今日已入库记录，用于去重（本地过滤，避免 API filter 格式问题）"""
    today_str = datetime.now().strftime("%Y/%m/%d")
    print(f"[查询] 获取全量记录（本地过滤 {today_str}）...")
    all_records = _api_records_all(token)

    today_records = [
        r for r in all_records
        if r.get("fields", {}).get(config.FIELD_DATE, "").startswith(today_str)
    ]
    print(f"[查询] 今日已有 {len(today_records)} 条记录（总记录 {len(all_records)} 条）")
    return today_records


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
        records = [{"fields": build_fields(item)} for item in batch]

        resp = _api("POST",
            f"/bitable/v1/apps/{config.BASE_TOKEN}/tables/{config.TABLE_ID}/records/batch_create",
            token,
            {"records": records}
        )

        if resp.get("code") == 0:
            cnt = len(resp.get("data", {}).get("records", []))
            success += cnt
            print(f"[入库] 第 {i//BATCH_SIZE+1} 批成功 {cnt} 条")
        else:
            print(f"[入库] 批量失败({resp.get('msg')})，切换逐条模式")
            for item in batch:
                ok, msg = _ingest_single(token, item)
                if ok:
                    success += 1
                else:
                    failed += 1
                    print(f"  失败: {item.get('title','')[:30]} - {msg[:80]}")
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
    if resp.get("code") == 0:
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

    return {
        config.FIELD_STATUS: "待审核",
        config.FIELD_SOURCE: source,
        config.FIELD_TITLE:  record.get("title", "").strip(),
        config.FIELD_URL:    url,
        config.FIELD_NOTE:   summary,
        config.FIELD_CAT:    category,
        config.FIELD_HOT:    hot,
        config.FIELD_DATE:   now,
    }


def run():
    """主入口：读取 collected.json → 去重 → 入库"""
    token = get_app_access_token()

    # 读取采集结果
    SCRIPT_DIR = Path(__file__).parent
    raw_file = SCRIPT_DIR / "collected.json"
    if not raw_file.exists():
        print("[入库] 无新数据文件，退出")
        return {"success": 0, "failed": 0, "deduped": 0, "total_raw": 0}

    with open(raw_file, "r", encoding="utf-8") as f:
        new_items = json.load(f)

    if not new_items:
        print("[入库] 无新数据，退出")
        return {"success": 0, "failed": 0, "deduped": 0, "total_raw": 0}

    print(f"[入库] 待处理 {len(new_items)} 条")

    # 查询今日已有
    existing = query_today_records(token)
    existing_for_dedup = [
        {
            "title":   r.get("fields", {}).get(config.FIELD_TITLE, ""),
            "url":     r.get("fields", {}).get(config.FIELD_URL, ""),
            "source":  r.get("fields", {}).get(config.FIELD_SOURCE, ""),
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
