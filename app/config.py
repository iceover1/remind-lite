"""全局配置：环境变量优先，缺省值适配飞牛 NAS 部署。"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录（容器内挂载卷）
DATA_DIR = Path(os.environ.get("RL_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "remindlite.db"

# Web 登录（首次启动若无用户则用此初始密码创建 admin，登录后可改）
INIT_USERNAME = os.environ.get("RL_USERNAME", "admin")
INIT_PASSWORD = os.environ.get("RL_PASSWORD", "changeme")

# session 签名密钥：优先环境变量，否则持久化到 data 目录，重启不变
_key_file = DATA_DIR / ".secret_key"
if os.environ.get("RL_SECRET_KEY"):
    SECRET_KEY = os.environ["RL_SECRET_KEY"]
elif _key_file.exists():
    SECRET_KEY = _key_file.read_text().strip()
else:
    SECRET_KEY = secrets.token_urlsafe(48)
    _key_file.write_text(SECRET_KEY)
    _key_file.chmod(0o600)

# 时区固定上海（提醒调度以此时区为准）
TZ_NAME = "Asia/Shanghai"

# Bark 推送默认值（实际通道在 Web 设置页/数据库里配置，此处仅为部署时的缺省参考）
DEFAULT_SERVER_URL = os.environ.get("RL_BARK_SERVER", "")
DEFAULT_DEVICE_KEY = os.environ.get("RL_BARK_KEY", "")

# 推送点击跳转的 Web 地址（手机可达的地址，按部署环境在 .env 配置）
BASE_URL = os.environ.get("RL_BASE_URL", "http://localhost:15809")

# 调度
SCHEDULER_ENABLED = os.environ.get("RL_SCHEDULER", "1") == "1"

APP_NAME = "时效 Lite"
APP_VERSION = "1.0.4"
