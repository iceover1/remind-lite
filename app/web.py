"""Web UI 路由：服务端渲染（Jinja2），表单 POST 为主，按钮动作用 fetch 调 /api/v1。"""
import json
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth, config, db, items
from .config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)


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
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = db.query_one("SELECT * FROM users WHERE username=?", (username,))
    if not user or not auth.verify_password(password, user["password_hash"]):
        return render(request, "login.html", {"err": "用户名或密码错误"}, status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.SESSION_COOKIE, auth.make_session(username),
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
    return render(request, "index.html", {
        "due": due, "acked": acked, "today": t,
        "active_count": len(items.upcoming(limit=999)),
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
               cycle: str = Form("none"), cycle_days: int | None = Form(None),
               advance_days: int = Form(30), remind_days: str = Form("[30,7,1,0]"),
               remind_times: str = Form('["09:00"]')):
    if r := _login_or_redirect(request):
        return r
    try:
        items.parse_date(expire_date)
    except ValueError:
        return RedirectResponse("/items?err=日期格式错误", status_code=303)
    if cycle not in ("none", "month", "year", "custom"):
        cycle = "none"
    if cycle == "custom" and not (cycle_days and cycle_days > 0):
        return RedirectResponse("/items?err=自定义循环需要填写周期天数", status_code=303)
    if id:
        db.execute(
            "UPDATE items SET title=?,category=?,note=?,expire_date=?,cycle=?,cycle_days=?,"
            "advance_days=?,remind_days=?,remind_times=?,updated_at=datetime('now','localtime') WHERE id=?",
            (title, category, note, expire_date, cycle, cycle_days, advance_days,
             remind_days, remind_times, id))
    else:
        db.execute(
            "INSERT INTO items(title,category,note,expire_date,cycle,cycle_days,advance_days,remind_days,remind_times)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (title, category, note, expire_date, cycle, cycle_days, advance_days,
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


@router.post("/settings/password")
def password_change(request: Request, old_password: str = Form(...), new_password: str = Form(...)):
    if r := _login_or_redirect(request):
        return r
    user = auth.current_user(request)
    if not auth.verify_password(old_password, user["password_hash"]):
        return RedirectResponse("/settings?msg=旧密码错误", status_code=303)
    if len(new_password) < 6:
        return RedirectResponse("/settings?msg=新密码至少6位", status_code=303)
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (auth.hash_password(new_password), user["id"]))
    return RedirectResponse("/settings?msg=密码已修改", status_code=303)
