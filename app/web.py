"""Web UI 路由：服务端渲染（Jinja2），表单 POST 为主，按钮动作用 fetch 调 /api/v1。"""
import json
import secrets
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth, bark, config, db, items
from .config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)


# 登录锁定触发时推一条告警到师傅手机
def _lockout_alert(ip: str, fails: int) -> None:
    for r in bark.push_all_channels(
        f"⚠️时效Lite：登录失败过多",
        f"15分钟内 {fails} 次失败，来源 {ip}，已锁定15分钟。如非本人操作请检查服务暴露面。",
        url=None):
        db.execute(
            "INSERT INTO push_logs(item_id, remind_date, remind_time, channel_id, channel_name, ok, detail)"
            " VALUES(0, ?, ?, ?, ?, ?, ?)",
            (items.today().isoformat(), items.now_hm(), r["channel"]["id"],
             r["channel"]["name"], 1 if r["ok"] else 0, "[security] " + r["detail"]))


auth.set_lockout_hook(_lockout_alert)


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    ctx = ctx or {}
    ctx.setdefault("app_name", config.APP_NAME)
    ctx.setdefault("user", auth.current_user(request))
    ctx.setdefault("base_url", config.BASE_URL)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _login_or_redirect(request: Request):
    if not auth.current_user(request):
        return RedirectResponse("/login", status_code=303)
    return None


# ---------- 登录 ----------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, err: str = ""):
    return render(request, "login.html", {"err": err})


@router.post("/login")
def login(request: Request,
          username: Annotated[str, Form(max_length=auth.MAX_USERNAME)] = ...,
          password: Annotated[str, Form(max_length=auth.MAX_PASSWORD)] = ...):
    ip = request.client.host if request.client else "?"
    # 限速：锁定中直接拒（含正确密码，防靠响应差异探密码）
    locked = auth.throttle_state(ip)
    if locked > 0:
        return render(request, "login.html",
                      {"err": f"尝试过多已锁定，请 {max(locked // 60, 1)} 分钟后再试"},
                      status_code=429)
    user = db.query_one("SELECT * FROM users WHERE username=?", (username,))
    if not user:
        auth.verify_password(password, auth._DUMMY_HASH)  # 抹平用户名不存在的时序差
        auth.throttle_fail(ip)
        return render(request, "login.html", {"err": "用户名或密码错误"}, status_code=401)
    if not auth.verify_password(password, user["password_hash"]):
        auth.throttle_fail(ip)
        return render(request, "login.html", {"err": "用户名或密码错误"}, status_code=401)
    auth.throttle_ok(ip)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.SESSION_COOKIE,
                    auth.make_session(username, user.get("session_ver", 0)),
                    max_age=auth.SESSION_TTL, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


# ---------- 今日概览 ----------

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    if r := _login_or_redirect(request):
        return r
    t = items.today().isoformat()
    due = [items.item_display(i) for i in items.due_items()]
    acked = {a["item_id"] for a in db.query("SELECT item_id FROM acks WHERE ack_date=?", (t,))}
    active = [items.item_display(i) for i in items.upcoming(limit=999)]
    stats = {
        "today": len(due),
        "overdue": sum(1 for i in active if i["days_left"] < 0),
        "week": sum(1 for i in active if 0 <= i["days_left"] <= 7),
        "active": len(active),
    }
    return render(request, "index.html", {
        "due": due, "acked": acked, "today": t,
        "active_count": stats["active"], "stats": stats,
    })


# ---------- 效期管理 ----------

@router.get("/items", response_class=HTMLResponse)
def items_page(request: Request, edit: int | None = None):
    if r := _login_or_redirect(request):
        return r
    rows = [items.item_display(i) for i in db.query(
        "SELECT * FROM items ORDER BY status='done', expire_date")]
    editing = None
    if edit:
        row = db.query_one("SELECT * FROM items WHERE id=?", (edit,))
        if row:
            editing = {
                **row,
                "remind_days_json": (row["remind_days"] if row["remind_days"] == "all"
                                     else json.dumps(items.get_remind_days(row))),
                "remind_times_json": json.dumps(items.get_remind_times(row)),
            }
    return render(request, "items.html", {
        "rows": rows, "editing": editing, "categories": items.CATEGORIES,
        "default_days": json.dumps(items.DEFAULT_REMIND_DAYS),
        "default_times": json.dumps(items.DEFAULT_REMIND_TIMES),
    })


@router.post("/items/save")
def items_save(request: Request, id: int | None = Form(None), title: str = Form(...),
               category: str = Form("其他"), note: str = Form(""), expire_date: str = Form(...),
               cycle: str = Form("none"), cycle_days: str = Form(""),
               advance_days: str = Form("30"), remind_days: str = Form("[30,7,1,0]"),
               remind_times: str = Form('["09:00"]')):
    if r := _login_or_redirect(request):
        return r
    try:
        items.parse_date(expire_date)
    except ValueError:
        return RedirectResponse("/items?err=日期格式错误", status_code=303)
    if cycle not in ("none", "month", "year", "custom"):
        cycle = "none"
    # 表单空字符串宽容处理（浏览器对空 number input 提交 ""）
    try:
        cycle_days_i = int(cycle_days) if str(cycle_days).strip() else None
    except ValueError:
        cycle_days_i = None
    try:
        advance_i = int(advance_days) if str(advance_days).strip() else 30
    except ValueError:
        advance_i = 30
    if cycle == "custom" and not (cycle_days_i and cycle_days_i > 0):
        return RedirectResponse("/items?err=自定义循环需要填写周期天数", status_code=303)
    # remind_days / remind_times 兜底：非法 JSON 时回默认
    try:
        json.loads(remind_days)
    except Exception:
        remind_days = "[30,7,1,0]"
    try:
        json.loads(remind_times)
    except Exception:
        remind_times = '["09:00"]'
    if id:
        db.execute(
            "UPDATE items SET title=?,category=?,note=?,expire_date=?,cycle=?,cycle_days=?,"
            "advance_days=?,remind_days=?,remind_times=?,updated_at=datetime('now','localtime') WHERE id=?",
            (title, category, note, expire_date, cycle, cycle_days_i, advance_i,
             remind_days, remind_times, id))
    else:
        db.execute(
            "INSERT INTO items(title,category,note,expire_date,cycle,cycle_days,advance_days,remind_days,remind_times)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (title, category, note, expire_date, cycle, cycle_days_i, advance_i,
             remind_days, remind_times))
    return RedirectResponse("/items", status_code=303)


@router.post("/items/{item_id}/delete")
def items_delete(item_id: int, request: Request):
    if r := _login_or_redirect(request):
        return r
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    db.execute("DELETE FROM acks WHERE item_id=?", (item_id,))
    return RedirectResponse("/items", status_code=303)


@router.post("/items/{item_id}/done")
def items_done(item_id: int, request: Request):
    if r := _login_or_redirect(request):
        return r
    db.execute("UPDATE items SET status='done',updated_at=datetime('now','localtime') WHERE id=?",
               (item_id,))
    return RedirectResponse(request.headers.get("referer") or "/items", status_code=303)


# ---------- 发送日志 ----------

@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    if r := _login_or_redirect(request):
        return r
    logs = db.query(
        "SELECT l.*, i.title AS item_title FROM push_logs l"
        " LEFT JOIN items i ON i.id=l.item_id ORDER BY l.id DESC LIMIT 200")
    return render(request, "logs.html", {"logs": logs})


# ---------- 设置 ----------

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, msg: str = ""):
    if r := _login_or_redirect(request):
        return r
    user = auth.current_user(request)
    return render(request, "settings.html", {
        "channels": db.query("SELECT * FROM channels ORDER BY id"),
        "api_token": user["api_token"] or "", "msg": msg,
    })


@router.post("/settings/channel/add")
def channel_add(request: Request, name: str = Form(...), server_url: str = Form(...),
                device_key: str = Form(...)):
    if r := _login_or_redirect(request):
        return r
    db.execute("INSERT INTO channels(name,server_url,device_key,enabled) VALUES(?,?,?,1)",
               (name, server_url.rstrip("/"), device_key))
    return RedirectResponse("/settings?msg=通道已添加", status_code=303)


@router.post("/settings/channel/{cid}/delete")
def channel_delete(cid: int, request: Request):
    if r := _login_or_redirect(request):
        return r
    db.execute("DELETE FROM channels WHERE id=?", (cid,))
    return RedirectResponse("/settings?msg=通道已删除", status_code=303)


@router.post("/settings/token/reset")
def token_reset(request: Request):
    if r := _login_or_redirect(request):
        return r
    user = auth.current_user(request)
    db.execute("UPDATE users SET api_token=? WHERE id=?", (auth.new_api_token(), user["id"]))
    return RedirectResponse("/settings?msg=API Token 已重置（旧 Token 立即失效）", status_code=303)


@router.post("/settings/username")
def username_change(request: Request,
                    new_username: Annotated[str, Form(max_length=auth.MAX_USERNAME)] = ...,
                    old_password: Annotated[str, Form(max_length=auth.MAX_PASSWORD)] = ...):
    """修改用户名（需密码确认）。改名后旧会话作废，当前浏览器换发新会话。"""
    if r := _login_or_redirect(request):
        return r
    user = auth.current_user(request)
    new_username = new_username.strip()
    if not auth.verify_password(old_password, user["password_hash"]):
        return RedirectResponse("/settings?msg=密码错误，用户名未改", status_code=303)
    if len(new_username) < 3 or any(c.isspace() for c in new_username):
        return RedirectResponse("/settings?msg=用户名需3位以上且不含空格", status_code=303)
    if new_username == user["username"]:
        return RedirectResponse("/settings?msg=与新用户名相同", status_code=303)
    if db.query_one("SELECT id FROM users WHERE username=?", (new_username,)):
        return RedirectResponse("/settings?msg=该用户名已被占用", status_code=303)
    db.execute("UPDATE users SET username=?, session_ver=session_ver+1 WHERE id=?",
               (new_username, user["id"]))
    resp = RedirectResponse("/settings?msg=用户名已修改（旧登录名即刻失效）", status_code=303)
    resp.set_cookie(auth.SESSION_COOKIE,
                    auth.make_session(new_username, user["session_ver"] + 1),
                    max_age=auth.SESSION_TTL, httponly=True, samesite="lax")
    return resp


@router.post("/settings/password")
def password_change(request: Request,
                    old_password: Annotated[str, Form(max_length=auth.MAX_PASSWORD)] = ...,
                    new_password: Annotated[str, Form(max_length=auth.MAX_PASSWORD)] = ...):
    if r := _login_or_redirect(request):
        return r
    user = auth.current_user(request)
    if not auth.verify_password(old_password, user["password_hash"]):
        return RedirectResponse("/settings?msg=旧密码错误", status_code=303)
    if len(new_password) < 6:
        return RedirectResponse("/settings?msg=新密码至少6位", status_code=303)
    # 改密码 → 会话版本+1：所有旧会话（含被偷的Cookie）立即作废
    db.execute("UPDATE users SET password_hash=?, session_ver=session_ver+1 WHERE id=?",
               (auth.hash_password(new_password), user["id"]))
    fresh = db.query_one("SELECT * FROM users WHERE id=?", (user["id"],))
    resp = RedirectResponse("/settings?msg=密码已修改（其他已登录设备已全部下线）", status_code=303)
    resp.set_cookie(auth.SESSION_COOKIE,
                    auth.make_session(user["username"], fresh["session_ver"]),
                    max_age=auth.SESSION_TTL, httponly=True, samesite="lax")
    return resp
