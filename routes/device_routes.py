'''
Descripttion: 
Author: Joe Guo
version: 
Date: 2025-07-25 17:02:44
LastEditors: Joe Guo
LastEditTime: 2025-07-25 17:02:50
'''
'''
设备信息接口
提供设备状态和资源信息查询
'''
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from config import (
    REMOTE_DEVICES,
    LOCAL_GPUS,
    MINERU_EXECUTABLE,
    QWEN_MODEL_PATH
)
from services.mineru_service import check_remote_health
from services.office_service import find_libreoffice_path
import shutil
import os

router = APIRouter()
logger = logging.getLogger("device_routes")

@router.get("/devices", response_class=JSONResponse)
async def list_devices():
    """获取设备列表及状态信息"""
    logger.info("开始获取设备列表及状态信息")
    for device in REMOTE_DEVICES:
        health_status = check_remote_health(device)
        device["status"] = "idle" if health_status else "error"
        logger.info(f"远程设备 {device['name']} 状态: {device['status']}")
    
    local_healthy = shutil.which(MINERU_EXECUTABLE) is not None
    logger.info(f"本地MinerU可用: {local_healthy}")
    local_gpus_status = [{"id": gpu["id"], "status": gpu["status"]} for gpu in LOCAL_GPUS]
    logger.info(f"本地GPU状态: {local_gpus_status}")
    
    # 检查LibreOffice状态
    libreoffice_path = find_libreoffice_path()
    libreoffice_status = "available" if libreoffice_path else "not found"
    logger.info(f"LibreOffice状态: {libreoffice_status}, 路径: {libreoffice_path}")
    
    # 检查Qwen模型状态
    qwen_status = "available" if os.path.exists(QWEN_MODEL_PATH) else "not found"
    logger.info(f"Qwen模型状态: {qwen_status}, 路径: {QWEN_MODEL_PATH}")
    
    result = {
        "local_devices": {
            "gpus": local_gpus_status,
            "mineru_healthy": local_healthy,
            "libreoffice_status": libreoffice_status,
            "libreoffice_path": libreoffice_path,
            "qwen_vl_status": qwen_status,
            "qwen_vl_path": QWEN_MODEL_PATH
        },
        "remote_devices": REMOTE_DEVICES
    }
    logger.info("设备信息获取完成")
    return result