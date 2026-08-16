#!/usr/bin/env python3
"""从原时效管家（remindflow.db）导出数据为 seed JSON：
- tasks → items（域名/服务器续费类，title/note/expire_date/推送时刻）
- webhook_channels → bark 通道（沿用自建服务器 + device key）

用法：python3 convert.py <remindflow.db 路径> [输出目录]
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))  # 原版存储为 UTC 毫秒时间戳


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, TZ)


def guess_category(name: str, desc: str) -> str:
    text = name + desc
    if "域名" in text or "dns" in text or ".org" in text or ".ci" in text or ".cd" in text:
        return "域名"
    if "服务器" in text or "vps" in text.lower():
        return "服务器"
    return "其他"


def main(db_path: str, out_dir: str = "."):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    items = []
    for t in con.execute("SELECT * FROM tasks ORDER BY id"):
        expire = ms_to_dt(t["task_date"])
        # remind_time 是绝对时间戳，取其当天时刻作为推送时刻偏好
        times = ["09:00"]
        if t["remind_time"]:
            rt = ms_to_dt(t["remind_time"])
            times = [rt.strftime("%H:%M")]
        items.append({
            "title": t["name"].strip(),
            "category": guess_category(t["name"] or "", t["description"] or ""),
            "note": (t["description"] or "").strip(),
            "expire_date": expire.strftime("%Y-%m-%d"),
            "cycle": "none",
            "cycle_days": None,
            "advance_days": 30,
            "remind_days": [30, 7, 1, 0],   # 原版用户习惯 expiry_remind_days=30,7,1,0
            "remind_times": times,
            "_source_id": t["id"],
            "_source_status": t["status_id"],
        })

    channels = []
    for c in con.execute("SELECT * FROM webhook_channels"):
        cfg = json.loads(c["config"] or "{}")
        url = c["api_url"] or cfg.get("url") or ""
        # bark 推送格式: {server}/api/push/{key}
        key = ""
        if "/api/push/" in url:
            key = url.split("/api/push/")[-1].strip("/")
        channels.append({
            "name": (c["name"] or "bark").strip(),
            "server_url": url.split("/api/push/")[0] if "/api/push/" in url else url,
            "device_key": key,
            "enabled": bool(c["enabled"]),
        })

    (out / "seed_items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2))
    (out / "seed_channels.json").write_text(
        json.dumps(channels, ensure_ascii=False, indent=2))
    print(f"导出 {len(items)} 条事项 → {out/'seed_items.json'}")
    for i in items:
        print(f"  [{i['category']:3}] {i['title']}  到期 {i['expire_date']}  推送 {i['remind_times']}")
    print(f"导出 {len(channels)} 条通道 → {out/'seed_channels.json'}")
    for c in channels:
        print(f"  {c['name']}: {c['server_url']} key={c['device_key'][:8]}…")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "remindflow.db",
         sys.argv[2] if len(sys.argv) > 2 else ".")
