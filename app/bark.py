"""推送客户端：一个通道依次尝试三种后端格式，适配自建 bark-server 与 MagicPush。

1) bark-server v2：POST {server}/push JSON{device_key,title,body,...}
2) MagicPush：    POST {server}/api/push/{key} JSON{content:"title\nbody"}
   （飞牛 NAS 上的 magicpush 容器，最终转发到 Bark 落手机）
3) bark 经典 GET：GET {server}/{key}/{title}/{body} —— 响应必须是 JSON 且 code==200 才算成功
"""
import logging

import httpx

log = logging.getLogger("rl.bark")

TIMEOUT = 10


def _is_json_ok(text: str, code_key: str = "code") -> bool:
    import json
    try:
        data = json.loads(text)
    except Exception:
        return False  # HTML/文本响应一律不算成功（防止 SPA 页面误报）
    return (data.get(code_key) == 200) or data.get("success") is True


def push(server_url: str, device_key: str, title: str, body: str,
         group: str = "remind-lite", url: str | None = None,
         sound: str | None = None, level: str | None = None) -> tuple[bool, str]:
    """向单个通道推送，返回 (ok, detail)。"""
    server = server_url.rstrip("/")
    details = []

    # 1) bark-server v2 JSON API
    payload: dict = {"device_key": device_key, "title": title, "body": body, "group": group}
    if url:
        payload["url"] = url
    if sound:
        payload["sound"] = sound
    if level:
        payload["level"] = level
    try:
        r = httpx.post(f"{server}/push", json=payload, timeout=TIMEOUT)
        if r.status_code == 200 and _is_json_ok(r.text):
            return True, r.text[:200]
        details.append(f"bark /push: HTTP {r.status_code} {r.text[:80]}")
    except Exception as e:
        details.append(f"bark /push: {e}")

    # 2) MagicPush：POST /api/push/{key}，字段 content
    content = title + "\n" + body + (f"\n{url}" if url else "")
    try:
        r = httpx.post(f"{server}/api/push/{device_key}",
                       json={"content": content}, timeout=TIMEOUT)
        if r.status_code == 200 and _is_json_ok(r.text):
            return True, f"(magicpush) {r.text[:200]}"
        details.append(f"magicpush: HTTP {r.status_code} {r.text[:80]}")
    except Exception as e:
        details.append(f"magicpush: {e}")

    # 3) bark 经典 GET 路径（严格校验 JSON 响应）
    from urllib.parse import quote
    try:
        path = quote(f"{device_key}/{title}/{body}", safe="")
        r = httpx.get(f"{server}/{path}", timeout=TIMEOUT)
        if r.status_code == 200 and _is_json_ok(r.text):
            return True, f"(GET fallback) {r.text[:200]}"
        details.append(f"GET: HTTP {r.status_code} 非JSON响应")
    except Exception as e:
        details.append(f"GET: {e}")

    return False, "; ".join(details)[:400]


def push_all_channels(title: str, body: str, url: str | None = None) -> list[dict]:
    """向所有启用通道推送，返回逐通道结果（供日志记录）。"""
    from . import db
    channels = db.query("SELECT * FROM channels WHERE enabled=1")
    results = []
    for ch in channels:
        ok, detail = push(ch["server_url"], ch["device_key"], title, body, url=url)
        log.info("bark push channel=%s ok=%s detail=%s", ch["name"], ok, detail)
        results.append({"channel": ch, "ok": ok, "detail": detail})
    return results
