'''
Descripttion: 应用入口，初始化FastAPI应用并注册路由
Author: Joe Guo
version: 2.0
Date: 2025-07-25 16:56:56
LastEditors: Joe Guo
LastEditTime: 2025-07-30 17:05:27
'''


import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.extract_routes import router as extract_router
from routes.image_routes import router as image_router
from routes.combined_routes import router as combined_router  # 新增复合任务路由

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

# 创建FastAPI应用
app = FastAPI(
    title="MinerUVision API",
    description="提供文本提取和图片描述功能的API服务",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(extract_router, tags=["文本提取"])
app.include_router(image_router, tags=["图片描述"])
app.include_router(combined_router, tags=["复合任务"])  # 新增复合任务路由

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
    import uvicorn
    logger.info("启动MinerUVision API服务...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)