"""REST API /api/v1：Agent（沙僧口头指令）与浏览器插件共用，Bearer Token 或 Web 会话认证。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from . import auth, bark, config, db, items, scheduler

router = APIRouter(prefix="/api/v1", tags=["api"])


# ---------- 模型 ----------

class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    category: str = "其他"
    note: str = ""
    expire_date: str  # YYYY-MM-DD
    cycle: str = "none"          # none|month|year|custom
    cycle_days: int | None = None
    advance_days: int = 30
    remind_days: str | list = "default"  # "default"=[30,7,1,0] | "all" | [30,7,1,0]
    remind_times: str | list = "default"  # "default"=["09:00"] | ["09:00","20:00"]

    @field_validator("expire_date")
    @classmethod
    def check_date(cls, v: str) -> str:
        items.parse_date(v)  # 抛 ValueError 即 400
        return v

    @field_validator("cycle_days", mode="before")
    @classmethod
    def empty_cycle_days(cls, v):
        """宽容空串/空值（表单或插件可能传 ""）。"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(v)

    @field_validator("cycle")
    @classmethod
    def check_cycle(cls, v: str) -> str:
        if v not in ("none", "month", "year", "custom"):
            raise ValueError("cycle 必须是 none|month|year|custom")
        return v


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    server_url: str
    device_key: str = Field(min_length=8)
    enabled: bool = True


def _norm_json_field(v: str | list, default: list, kind: str) -> str:
    if v == "default":
        return json.dumps(default)
    if v == "all":
        return "all"
    if isinstance(v, list):
        if kind == "days":
            v = sorted({int(x) for x in v}, reverse=True)
        else:
            v = [str(x) for x in v]
        return json.dumps(v)
    # 字符串透传（应为合法 JSON 或 "all"）
    json.loads(v) if v != "all" else None
    return v


def _item_to_out(it: dict) -> dict:
    return items.item_display(it)


# ---------- 事项 ----------

@router.get("/items")
def list_items(request: Request, due: str | None = None, status: str = "active",
               user: dict = Depends(auth.require_any)):
    if due == "today":
        return {"items": [_item_to_out(i) for i in items.due_items()]}
    rows = db.query(
        "SELECT * FROM items WHERE status=? ORDER BY expire_date", (status,))
    return {"items": [_item_to_out(r) for r in rows]}


@router.get("/items/{item_id}")
def get_item(item_id: int, user: dict = Depends(auth.require_any)):
    it = db.query_one("SELECT * FROM items WHERE id=?", (item_id,))
    if not it:
        raise HTTPException(404, "item not found")
    return _item_to_out(it)


@router.post("/items", status_code=201)
def create_item(body: ItemIn, user: dict = Depends(auth.require_any)):
    rd = _norm_json_field(body.remind_days, items.DEFAULT_REMIND_DAYS, "days")
    rt = _norm_json_field(body.remind_times, items.DEFAULT_REMIND_TIMES, "times")
    if body.cycle == "custom" and not (body.cycle_days and body.cycle_days > 0):
        raise HTTPException(400, "cycle=custom 需要正整数 cycle_days")
    iid = db.execute(
        "INSERT INTO items(title,category,note,expire_date,cycle,cycle_days,advance_days,remind_days,remind_times)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (body.title, body.category, body.note, body.expire_date, body.cycle,
         body.cycle_days, body.advance_days, rd, rt))
    return _item_to_out(db.query_one("SELECT * FROM items WHERE id=?", (iid,)))


@router.patch("/items/{item_id}")
def update_item(item_id: int, body: ItemIn, user: dict = Depends(auth.require_any)):
    if not db.query_one("SELECT id FROM items WHERE id=?", (item_id,)):
        raise HTTPException(404, "item not found")
    rd = _norm_json_field(body.remind_days, items.DEFAULT_REMIND_DAYS, "days")
    rt = _norm_json_field(body.remind_times, items.DEFAULT_REMIND_TIMES, "times")
    if body.cycle == "custom" and not (body.cycle_days and body.cycle_days > 0):
        raise HTTPException(400, "cycle=custom 需要正整数 cycle_days")
    db.execute(
        "UPDATE items SET title=?,category=?,note=?,expire_date=?,cycle=?,cycle_days=?,"
        "advance_days=?,remind_days=?,remind_times=?,updated_at=datetime('now','localtime') WHERE id=?",
        (body.title, body.category, body.note, body.expire_date, body.cycle,
         body.cycle_days, body.advance_days, rd, rt, item_id))
    return _item_to_out(db.query_one("SELECT * FROM items WHERE id=?", (item_id,)))


@router.delete("/items/{item_id}")
def delete_item(item_id: int, user: dict = Depends(auth.require_any)):
    if not db.query_one("SELECT id FROM items WHERE id=?", (item_id,)):
        raise HTTPException(404, "item not found")
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    db.execute("DELETE FROM acks WHERE item_id=?", (item_id,))
    db.execute("DELETE FROM push_logs WHERE item_id=?", (item_id,))
    return {"ok": True}


@router.post("/items/{item_id}/ack")
def ack_item(item_id: int, user: dict = Depends(auth.require_any)):
    if not db.query_one("SELECT id FROM items WHERE id=?", (item_id,)):
        raise HTTPException(404, "item not found")
    scheduler.ack_item(item_id)
    return {"ok": True, "ack_date": items.today().isoformat()}


@router.post("/items/{item_id}/done")
def done_item(item_id: int, user: dict = Depends(auth.require_any)):
    db.execute("UPDATE items SET status='done',updated_at=datetime('now','localtime') WHERE id=?",
               (item_id,))
    return {"ok": True}


@router.post("/items/{item_id}/test-push")
def test_push(item_id: int, user: dict = Depends(auth.require_any)):
    it = db.query_one("SELECT * FROM items WHERE id=?", (item_id,))
    if not it:
        raise HTTPException(404, "item not found")
    disp = items.item_display(it)
    title = f"🧪测试推送 · {it['category']} · {disp['left_text']}"
    body = f"{it['title']}\n到期日 {it['expire_date']}"
    results = bark.push_all_channels(title, body, url=f"{config.BASE_URL}/")
    for r in results:
        db.execute(
            "INSERT INTO push_logs(item_id, remind_date, remind_time, channel_id, channel_name, ok, detail)"
            " VALUES(?,?,?,?,?,?,?)",
            (item_id, items.today().isoformat(), items.now_hm(), r["channel"]["id"],
             r["channel"]["name"], 1 if r["ok"] else 0, "[test] " + r["detail"]))
    if not results:
        raise HTTPException(400, "没有启用的推送通道，请先在设置里配置 Bark")
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "results": [{"channel": r["channel"]["name"], "ok": r["ok"],
                                   "detail": r["detail"]} for r in results]}


# ---------- 通道 ----------

@router.get("/channels")
def list_channels(user: dict = Depends(auth.require_any)):
    return {"channels": db.query("SELECT * FROM channels ORDER BY id")}


@router.post("/channels", status_code=201)
def create_channel(body: ChannelIn, user: dict = Depends(auth.require_any)):
    cid = db.execute(
        "INSERT INTO channels(name,server_url,device_key,enabled) VALUES(?,?,?,?)",
        (body.name, body.server_url.rstrip("/"), body.device_key, 1 if body.enabled else 0))
    return db.query_one("SELECT * FROM channels WHERE id=?", (cid,))


@router.delete("/channels/{cid}")
def delete_channel(cid: int, user: dict = Depends(auth.require_any)):
    db.execute("DELETE FROM channels WHERE id=?", (cid,))
    return {"ok": True}


# ---------- 元信息 ----------

@router.get("/meta")
def meta(user: dict = Depends(auth.require_any)):
    """插件拉默认值：分类、默认时刻等。"""
    return {
        "categories": items.CATEGORIES,
        "default_remind_days": items.DEFAULT_REMIND_DAYS,
        "default_remind_times": items.DEFAULT_REMIND_TIMES,
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
    }
