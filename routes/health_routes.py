'''
Descripttion: 健康检查接口，提供系统各组件的健康状态检查
Author: Joe Guo
version: 
Date: 2025-07-25 17:02:24
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:11:50
'''

import logging
import datetime
import shutil
import os  # 添加os模块用于Qwen模型检查
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from utils.minio_utils import minio_client
from config import (
    MINIO_BUCKET,
    MINERU_EXECUTABLE,
    QWEN_MODEL_PATH,
    REMOTE_DEVICES
)
from services.office_service import find_libreoffice_path
from services.mineru_service import check_remote_health

router = APIRouter()
logger = logging.getLogger("health_routes")

@router.get("/health", response_class=JSONResponse)
async def health_check():
    """系统健康检查接口"""
    logger.info("开始进行系统健康检查")
    # 检查MinIO存储服务健康状态
    minio_healthy = False
    try:
        minio_healthy = minio_client.bucket_exists(MINIO_BUCKET)
        logger.info(f"MinIO健康: {minio_healthy}")
    except Exception as e:
        logger.error(f"MinIO健康检查失败: {str(e)}")
    
    # 检查本地MinerU可执行文件是否存在
    mineru_healthy = shutil.which(MINERU_EXECUTABLE) is not None
    logger.info(f"MinerU本地可用: {mineru_healthy}")
    
    # 检查LibreOffice是否可用
    libreoffice_healthy = find_libreoffice_path() is not None
    logger.info(f"LibreOffice可用: {libreoffice_healthy}")
    
    # 检查Qwen模型文件是否存在
    qwen_healthy = False
    try:
        qwen_healthy = os.path.exists(QWEN_MODEL_PATH)
        logger.info(f"Qwen模型可用: {qwen_healthy}")
    except Exception as e:
        logger.error(f"Qwen模型健康检查失败: {str(e)}")
    
    # 检查所有远程设备的健康状态
    remote_health = []
    for device in REMOTE_DEVICES:
        health = check_remote_health(device)
        logger.info(f"远程设备 {device['name']} 健康: {health}")
        remote_health.append({
            "name": device["name"],
            "ip": device["ip"],
            "port": device["port"],
            "healthy": health
        })
    
    # 计算整体健康状态
    overall_healthy = minio_healthy and mineru_healthy
    logger.info(f"系统整体健康状态: {'healthy' if overall_healthy else 'unhealthy'}")
    
    # 返回健康检查结果
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "services": {
            "minio": {"healthy": minio_healthy},
            "mineru_local": {"healthy": mineru_healthy, "executable": MINERU_EXECUTABLE},
            "libreoffice": {"healthy": libreoffice_healthy},
            "qwen_vl_model": {"healthy": qwen_healthy, "path": QWEN_MODEL_PATH},
            "remote_devices": remote_health
        }
    }
