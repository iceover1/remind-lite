"""调度器：每分钟 tick 推送 + 每日 00:05 循环事项滚动 + 每日 08:00 月度汇总（预留）。"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import bark, config, db, items

log = logging.getLogger("rl.scheduler")


def tick() -> None:
    """每分钟执行：当前 HH:MM 命中 remind_times 且当日该时刻未推、未 ack 的事项 → Bark。"""
    try:
        _tick()
    except Exception:
        log.exception("tick 执行异常")


def _tick() -> None:
    now = datetime.now(items.TZ)
    hm = now.strftime("%H:%M")
    date_s = now.strftime("%Y-%m-%d")

    for it in items.due_items():
        iid = it["id"]
        # 1) 当日已确认 → 全天静默
        if db.query_one("SELECT id FROM acks WHERE item_id=? AND ack_date=?", (iid, date_s)):
            continue
        # 2) 当前时刻不在配置里 → 跳过
        if hm not in items.get_remind_times(it):
            continue
        # 3) 该 (事项, 日期, 时刻) 已推过（含失败，防重启轰炸）→ 跳过
        if db.query_one(
            "SELECT id FROM push_logs WHERE item_id=? AND remind_date=? AND remind_time=?",
            (iid, date_s, hm),
        ):
            continue

        disp = items.item_display(it)
        d = disp["days_left"]
        if d < 0:
            title = f"⏰{it['category']} · 已逾期{-d}天"
        elif d == 0:
            title = f"⏰{it['category']} · 今天到期"
        else:
            title = f"⏰{it['category']} · 还剩{d}天"
        body = f"{it['title']}\n到期日 {it['expire_date']}（{disp['left_text']}）"
        if it.get("note"):
            body += f"\n备注：{it['note']}"

        for r in bark.push_all_channels(title, body, url=f"{config.BASE_URL}/"):
            db.execute(
                "INSERT INTO push_logs(item_id, remind_date, remind_time, channel_id, channel_name, ok, detail) "
                "VALUES(?,?,?,?,?,?,?)",
                (iid, date_s, hm, r["channel"]["id"], r["channel"]["name"],
                 1 if r["ok"] else 0, r["detail"]),
            )
        log.info("pushed item=%s %s %s", iid, it["title"], hm)


def roll_job() -> None:
    """每日 00:05：循环事项过期后滚动到下一周期。"""
    try:
        t = items.today().isoformat()
        for it in items.query_active():
            if it["cycle"] == "none":
                continue
            if items.parse_date(it["expire_date"]) >= items.today():
                continue
            nxt = items.roll_cycle(it["expire_date"], it["cycle"], it["cycle_days"])
            db.execute(
                "UPDATE items SET expire_date=?, updated_at=datetime('now','localtime') WHERE id=?",
                (nxt, it["id"]),
            )
            log.info("cycle roll item=%s %s -> %s", it["id"], it["expire_date"], nxt)
    except Exception:
        log.exception("roll_job 执行异常")


def ack_item(item_id: int) -> bool:
    """当日确认：当日剩余推送全部取消。幂等。"""
    date_s = items.today().isoformat()
    db.execute(
        "INSERT OR IGNORE INTO acks(item_id, ack_date) VALUES(?,?)", (item_id, date_s))
    return True


def start() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=config.TZ_NAME)
    sched.add_job(tick, CronTrigger(minute="*", timezone=config.TZ_NAME), id="tick",
                  max_instances=1, coalesce=True)
    sched.add_job(roll_job, CronTrigger(hour=0, minute=5, timezone=config.TZ_NAME), id="roll",
                  max_instances=1, coalesce=True)
    sched.start()
    log.info("scheduler started (tz=%s)", config.TZ_NAME)
    return sched
