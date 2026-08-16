"""事项领域逻辑：解析提醒配置、计算到期信息、判断是否该推。"""
import json
from datetime import date, datetime, timedelta

from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TZ_NAME)

CATEGORIES = ["域名", "服务器", "证件", "订阅", "质保", "其他"]
DEFAULT_REMIND_DAYS = [30, 7, 1, 0]   # 提前 N 天时推送（0 = 当天），默认节奏
DEFAULT_REMIND_TIMES = ["09:00"]


def today() -> date:
    return datetime.now(TZ).date()


def now_hm() -> str:
    return datetime.now(TZ).strftime("%H:%M")


def parse_json_list(raw: str | None, default: list) -> list:
    if not raw:
        return list(default)
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else list(default)
    except Exception:
        return list(default)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def days_left(item: dict, base: date | None = None) -> int:
    """距到期天数：当天=0，昨天=-1。"""
    base = base or today()
    return (parse_date(item["expire_date"]) - base).days


def get_remind_days(item: dict) -> list[int] | str:
    """返回 [30,7,1,0] 或 "all"。"""
    raw = item.get("remind_days") or ""
    if raw.strip() == "all":
        return "all"
    return parse_json_list(raw, DEFAULT_REMIND_DAYS)


def get_remind_times(item: dict) -> list[str]:
    return parse_json_list(item.get("remind_times"), DEFAULT_REMIND_TIMES)


def should_remind_today(item: dict, base: date | None = None) -> bool:
    """今天是否处于该事项的提醒日（不含 ack/已推判断）。"""
    if item["status"] != "active":
        return False
    d = days_left(item, base)
    if d < 0:
        return True  # 逾期未处理，每天继续提醒
    if d > item["advance_days"]:
        return False
    rd = get_remind_days(item)
    if rd == "all":
        return True
    return d in rd


def due_items(base: date | None = None) -> list[dict]:
    """今天应提醒的活跃事项列表（含逾期）。"""
    items = []
    for it in query_active():
        if should_remind_today(it, base):
            items.append(it)
    items.sort(key=lambda x: x["expire_date"])
    return items


def query_active() -> list[dict]:
    from . import db
    return db.query("SELECT * FROM items WHERE status='active'")


def upcoming(limit: int = 50) -> list[dict]:
    """按到期日排序的未完成事项（Web 列表/日历用）。"""
    from . import db
    rows = db.query("SELECT * FROM items WHERE status='active' ORDER BY expire_date LIMIT ?", (limit,))
    return rows


def item_display(it: dict, base: date | None = None) -> dict:
    """给 UI/推送用的展示字段。"""
    d = days_left(it, base)
    if d < 0:
        left_text = f"已逾期{-d}天"
    elif d == 0:
        left_text = "今天到期"
    else:
        left_text = f"还剩{d}天"
    return {
        **it,
        "days_left": d,
        "left_text": left_text,
        "remind_days_disp": ("窗口内每天" if get_remind_days(it) == "all"
                             else "/".join(f"提前{d}天" if d else "当天" for d in get_remind_days(it))),
        "remind_times_disp": "、".join(get_remind_times(it)),
        "cycle_disp": {"none": "不循环", "month": "每月循环", "year": "每年循环"}.get(
            it["cycle"], f"每{it.get('cycle_days') or '?'}天循环" if it["cycle"] == "custom" else it["cycle"]),
    }


def roll_cycle(expire_date: str, cycle: str, cycle_days: int | None) -> str:
    """循环事项滚动到 >= 今天（含今天之后首轮）的下一个周期日。"""
    d = parse_date(expire_date)
    t = today()
    if cycle == "month":
        while d < t:
            d = add_months(d, 1)
    elif cycle == "year":
        while d < t:
            d = add_years(d, 1)
    elif cycle == "custom" and cycle_days:
        while d < t:
            d += timedelta(days=cycle_days)
    return d.isoformat()


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    # 月末溢出保护：2026-01-31 +1月 → 2026-02-28
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def add_years(d: date, n: int) -> date:
    try:
        return date(d.year + n, d.month, d.day)
    except ValueError:  # 2-29
        return date(d.year + n, 3, 1)
