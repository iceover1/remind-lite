"""认证：Web 会话（HMAC 签名 Cookie）+ API Bearer Token + 密码哈希（scrypt）。"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request

from . import config, db

SESSION_COOKIE = "rl_session"
SESSION_TTL = 30 * 86400  # 30 天


# ---------- 密码哈希：scrypt（标准库，无额外依赖） ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
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


def make_session(username: str) -> str:
    payload = json.dumps({"u": username, "exp": int(time.time()) + SESSION_TTL},
                         separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{b64}.{_sign(payload)}"


def parse_session(token: str | None) -> str | None:
    """校验签名与有效期，返回用户名。"""
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
        return data["u"]
    except Exception:
        return None


def current_user(request: Request) -> dict | None:
    username = parse_session(request.cookies.get(SESSION_COOKIE))
    if not username:
        return None
    return db.query_one("SELECT * FROM users WHERE username=?", (username,))


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
