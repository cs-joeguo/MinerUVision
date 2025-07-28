'''
Descripttion: 应用入口，初始化FastAPI应用并注册路由
Author: Joe Guo
version: 
Date: 2025-07-25 16:56:56
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:14:24
'''

import logging
import sys
from fastapi import FastAPI
from routes.health_routes import router as health_router
from routes.device_routes import router as device_router
from routes.extract_routes import router as extract_router
from routes.image_routes import router as image_router

# 初始化日志，输出到文件和控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("mineru_service")

# 初始化FastAPI应用
app = FastAPI(
    title="MinerU API Service with MinIO and Qwen-VL",
    version="2.2",
    description="提供PDF/图片文件处理和图片描述生成功能的API服务"
)

# 注册路由
app.include_router(health_router)
app.include_router(device_router)
app.include_router(extract_router)
app.include_router(image_router)

@app.on_event("startup")
async def startup_event():
    """应用启动事件处理"""
    logger.info("应用启动中...")
    # 可以在这里添加初始化代码，如连接数据库等
    logger.info("应用启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件处理"""
    logger.info("应用关闭中...")
    # 可以在这里添加清理代码，如关闭连接等
    logger.info("应用已关闭")

if __name__ == "__main__":
    # 仅作为脚本运行时启动uvicorn服务
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)