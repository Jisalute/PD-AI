import os
import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import uvicorn
from dotenv import load_dotenv

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# 确保能导入 database_setup
sys.path.append(str(Path(__file__).parent))
from database_setup import create_tables
from app.api.v1.api import api_router
from app.core.config import settings
from app.api.v1.user.routes import register_pd_auth_routes
from app.core.logging import get_logger, setup_logging
from app.services.contract_service import expire_contracts_after_grace

# ========== 新增导入（智能体对话相关）- 只添加，不修改原有 ==========
from core.auth import get_user_identity_from_authorization
from core.database_async import db_async
from app.api.v1.routes.wechat_chat import router as wechat_chat_router
from app.core.logging import reset_log_user, set_log_user  # 添加日志用户功能


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 启动时初始化数据库"""
    setup_logging()
    logger = get_logger("app.lifespan")
    print("正在检查数据库初始化...")
    try:
        create_tables()
        print("数据库初始化完成")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        logger.exception("database init failed")

    # ========== 新增：初始化异步数据库连接池 ==========
    print("正在初始化数据库连接池...")
    try:
        await db_async.init_pool()
        print("✅ 数据库连接池初始化成功")
    except Exception as e:
        print(f"❌ 数据库连接池初始化失败: {e}")
        logger.exception("database pool init failed")

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        func=expire_contracts_after_grace,
        trigger=CronTrigger(hour=0, minute=10),
        kwargs={"grace_days": 5},
        id="expire_contracts",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("contract expire scheduler started")
    yield

    # ========== 新增：关闭数据库连接池 ==========
    print("正在关闭数据库连接池...")
    await db_async.close()
    print("✅ 数据库连接池已关闭")

    scheduler.shutdown(wait=False)
    print("应用关闭")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan
)

cors_origins = [origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 原有路由注册（保持不变） ==========
app.include_router(api_router, prefix="/api/v1")
register_pd_auth_routes(app)

# ========== 新增：注册智能体对话路由 ==========
app.include_router(wechat_chat_router, prefix="/api/v1")  # 添加智能体对话接口

logger = get_logger("app")


# ========== 修改请求日志中间件（添加用户身份追踪）- 只添加新功能，不破坏原有 ==========
@app.middleware("http")
async def request_logger(request: Request, call_next):
    start_time = time.perf_counter()

    # ========== 新增：获取用户身份用于日志 ==========
    identity = get_user_identity_from_authorization(request.headers.get("Authorization"))
    token = set_log_user(identity)

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed method=%s path=%s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    finally:
        # ========== 新增：重置日志用户 ==========
        reset_log_user(token)

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    if request.method in {"POST", "PUT", "DELETE"}:
        logger.info(
            "audit method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

    return response


# register_user_routes(app)

@app.get("/healthz")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/init-db")
def manual_init_db():
    """手动触发数据库初始化（调试用）"""
    try:
        create_tables()
        return {"success": True, "message": "数据库初始化完成"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== 新增：调试接口（可选，用于测试）==========
@app.get("/routes")
def list_routes():
    """查看所有已注册的路由（仅用于开发和调试）"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": getattr(route, "path", None),
            "name": getattr(route, "name", None),
            "methods": getattr(route, "methods", None)
        })
    return {
        "total": len(routes),
        "routes": routes
    }


@app.get("/debug/pool-status")
async def get_pool_status():
    """查看数据库连接池状态（仅用于调试）"""
    try:
        if hasattr(db_async, 'pool') and db_async.pool:
            return {
                "initialized": True,
                "pool_size": db_async.pool.size,
                "free_size": db_async.pool.freesize if hasattr(db_async.pool, 'freesize') else "N/A"
            }
        else:
            return {"initialized": False}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    load_dotenv()
    port = int(os.getenv("PORT", "8007"))


    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)