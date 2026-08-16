"""时效 Lite 入口：FastAPI app + 调度器生命周期。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api, auth, config, db, scheduler, web
from .config import BASE_DIR

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

MAX_BODY = 1024 * 1024  # 1MB：本应用无文件上传，超限即恶意


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    auth.ensure_init_user()
    sched = scheduler.start() if config.SCHEDULER_ENABLED else None
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    """请求体大小硬上限：挡超长密码/超长字段造成的内存与 CPU 放大。"""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse({"detail": "request body too large"}, status_code=413)
    return await call_next(request)


app.include_router(api.router)
app.include_router(web.router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/healthz")
def healthz():
    return {"ok": True, "app": config.APP_NAME, "version": config.APP_VERSION}
