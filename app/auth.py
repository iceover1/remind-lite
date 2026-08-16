"""认证：Web 会话（HMAC 签名 Cookie）+ API Bearer Token + 密码哈希（scrypt）+ 登录限速。"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from fastapi import HTTPException, Request

from . import config, db

SESSION_COOKIE = "rl_session"
SESSION_TTL = 30 * 86400  # 30 天

# 输入长度上限（防超长输入的内存/CPU 放大）
MAX_USERNAME = 50
MAX_PASSWORD = 256

# ---------- 登录限速：每 IP 滑动窗口计数 + 锁定 ----------
MAX_FAILS = 5          # 窗口内允许失败次数
FAIL_WINDOW = 15 * 60  # 计数窗口（秒）
LOCK_SECONDS = 15 * 60  # 触发后锁定时长

_throttle_lock = threading.Lock()
_throttle: dict[str, dict] = {}  # ip -> {fails: [ts...], locked_until: ts}
_on_lockout = None  # 由 web.py 注入的告警回调（推送 Bark）


def set_lockout_hook(fn):
    global _on_lockout
    _on_lockout = fn


def throttle_state(ip: str) -> int:
    """返回该 IP 剩余锁定秒数（0=未锁）。"""
    now = time.time()
    with _throttle_lock:
        st = _throttle.get(ip)
        if not st:
            return 0
        if st.get("locked_until", 0) > now:
            return int(st["locked_until"] - now)
    return 0


def throttle_fail(ip: str) -> bool:
    """记录一次失败。返回是否刚刚触发锁定（触发时调用告警钩子）。"""
    now = time.time()
    fired = False
    with _throttle_lock:
        st = _throttle.setdefault(ip, {"fails": [], "locked_until": 0})
        st["fails"] = [t for t in st["fails"] if now - t < FAIL_WINDOW]
        st["fails"].append(now)
        if len(st["fails"]) >= MAX_FAILS and st.get("locked_until", 0) <= now:
            st["locked_until"] = now + LOCK_SECONDS
            st["fails"] = []
            fired = True
    if fired and _on_lockout:
        try:
            _on_lockout(ip, MAX_FAILS)
        except Exception:
            pass
    return fired


def throttle_ok(ip: str) -> None:
    """登录成功，清空该 IP 记录。"""
    with _throttle_lock:
        _throttle.pop(ip, None)


# ---------- 密码哈希：scrypt（标准库，无额外依赖） ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


# 常量假哈希：用户名不存在时也跑一次同代价验证，抹平时序差（防用户名枚举）
_DUMMY_HASH = hash_password("rl-timing-equalizer")


def verify_password(password: str, stored: str) -> bool:
    try:
        if len(password) > MAX_PASSWORD:
            return False  # 超长直接拒（先于 scrypt，防 CPU 放大）
        _, salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expect = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, expect)
    except Exception:
        return False


# ---------- 会话 Cookie ----------

def _sign(payload: bytes) -> str:
    return hmac.new(config.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()


def make_session(username: str, session_ver: int = 0) -> str:
    payload = json.dumps({"u": username, "v": session_ver, "exp": int(time.time()) + SESSION_TTL},
                         separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{b64}.{_sign(payload)}"


def parse_session(token: str | None) -> dict | None:
    """校验签名与有效期，返回 {username, ver}。"""
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    try:
        data = json.loads(payload)
        if data.get("exp", 0) < time.time():
            return None
        return {"username": data["u"], "ver": data.get("v", 0)}
    except Exception:
        return None


def current_user(request: Request) -> dict | None:
    sess = parse_session(request.cookies.get(SESSION_COOKIE))
    if not sess:
        return None
    user = db.query_one("SELECT * FROM users WHERE username=?", (sess["username"],))
    # 会话版本不匹配（改过密码）→ 旧会话全部作废
    if not user or user.get("session_ver", 0) != sess["ver"]:
        return None
    return user


# ---------- 初始用户 ----------

def ensure_init_user() -> None:
    if db.query_one("SELECT id FROM users LIMIT 1"):
        return
    db.execute(
        "INSERT INTO users(username, password_hash, api_token) VALUES(?,?,?)",
        (config.INIT_USERNAME, hash_password(config.INIT_PASSWORD), secrets.token_urlsafe(32)),
    )


def new_api_token() -> str:
    return "rl_" + secrets.token_urlsafe(32)


# ---------- FastAPI 依赖 ----------

def require_token(request: Request) -> dict:
    """Bearer Token（Agent / 浏览器插件共用）。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth[7:].strip()
    user = db.query_one("SELECT * FROM users WHERE api_token=?", (token,))
    if not user:
        raise HTTPException(status_code=401, detail="invalid token")
    return user


def require_any(request: Request) -> dict:
    """会话或 Token 任一通过（网页内 fetch 也走 /api/v1）。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return require_token(request)
    user = current_user(request)
    if user:
        return user
    raise HTTPException(status_code=401, detail="unauthorized")
