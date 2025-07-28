'''
Descripttion: 
Author: Joe Guo
version: 
Date: 2025-07-25 17:03:07
LastEditors: Joe Guo
LastEditTime: 2025-07-25 17:03:11
'''
'''
图片描述接口
提供图片上传和描述生成功能
'''
import logging
import uuid
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile
from utils.redis_utils import add_image_task, get_image_task_result

router = APIRouter()
logger = logging.getLogger("image_routes")

@router.post("/describe-image", response_class=JSONResponse)
async def describe_image(
    file: UploadFile = File(...),
    libreoffice_path: str = Form(None)
):
    """
    图片描述接口
    
    参数:
        file: 上传的文件(PDF或图片)
        libreoffice_path: LibreOffice路径(可选)
    """
    try:
        # 生成唯一请求ID
        request_id = str(uuid.uuid4())
        logger.info(f"收到图片描述请求: {request_id}, 文件名: {file.filename}")
        
        # 保存上传的文件到临时位置
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            file_bytes = await file.read()
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name
            logger.info(f"文件已保存到临时路径: {temp_file_path}，大小: {len(file_bytes)} 字节")
        
        # 创建任务数据
        task_data = {
            "request_id": request_id,
            "input_path": temp_file_path,
            "libreoffice_path": libreoffice_path
        }
        logger.info(f"任务数据已准备: {task_data}")
        
        # 将任务添加到队列
        task_id = add_image_task(task_data)
        logger.info(f"任务已添加到队列，task_id: {task_id}")
        
        return {
            "status": "pending",
            "request_id": request_id,
            "message": "任务已提交，请使用request_id查询结果",
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"图片描述请求处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

@router.get("/image-result", response_class=JSONResponse)
async def get_image_result(request_id: str, timeout: int = 60):
    """
    获取图片描述结果

    参数:
        request_id: 请求ID（作为查询参数传入）
        timeout: 超时时间(秒)
    """
    try:
        logger.info(f"收到获取图片描述结果请求: request_id={request_id}, timeout={timeout}")
        result = get_image_task_result(request_id, timeout)
        # logger.info(f"获取结果: {result}")
        return result
    except Exception as e:
        logger.error(f"获取图片描述结果失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")