'''
Descripttion: 复合任务接口：提供同时处理文本提取和图片描述的复合任务功能
Author: Joe Guo
version: 2.0
Date: 2025-07-30 16:20:16
LastEditors: Joe Guo
LastEditTime: 2025-07-30 17:03:04
'''

import logging
import uuid
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile
from utils.redis_utils import add_combined_task, get_combined_task_result

router = APIRouter()
logger = logging.getLogger("combined_routes")

@router.post("/combined-task", response_class=JSONResponse)
async def create_combined_task(
    file: UploadFile = File(...),
    method: str = Form("auto"),
    backend: str = Form("vlm-sglang-engine"),
    lang: str = Form("ch"),
    formula: bool = Form(True),
    table: bool = Form(True),
    start_page: int = Form(None),
    end_page: int = Form(None),
    sglang_url: str = Form(None),
    source: str = Form("local"),
    return_all_files: bool = Form(False),
    use_remote: bool = Form(False),
    libreoffice_path: str = Form(None)
):
    """
    复合任务接口：同时处理文本提取和图片描述
    
    参数:
        file: 上传的文件
        method: 文本提取处理方法
        backend: 文本提取后端引擎
        lang: 语言
        formula: 是否提取公式
        table: 是否提取表格
        start_page: 开始页码
        end_page: 结束页码
        sglang_url: sglang服务地址
        source: 来源标识
        return_all_files: 是否返回所有文件
        use_remote: 是否使用远程设备处理
        libreoffice_path: LibreOffice路径(可选)
    """
    try:
        # 生成唯一请求ID
        request_id = str(uuid.uuid4())
        logger.info(f"收到复合任务请求: {request_id}, 文件名: {file.filename}")
        
        # 保存上传的文件到临时位置
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            file_bytes = await file.read()
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name
            logger.info(f"文件已保存到临时路径: {temp_file_path}，大小: {len(file_bytes)} 字节")
        
        # 准备文本提取任务参数
        extract_params = {
            "method": method,
            "backend": backend,
            "lang": lang,
            "formula": formula,
            "table": table,
            "start_page": start_page,
            "end_page": end_page,
            "sglang_url": sglang_url,
            "source": source,
            "return_all_files": return_all_files
        }
        logger.info(f"文本提取任务参数: {extract_params}")
        
        # 创建任务数据
        task_data = {
            "request_id": request_id,
            "input_path": temp_file_path,
            "extract_params": extract_params,
            "use_remote": use_remote,
            "libreoffice_path": libreoffice_path
        }
        logger.info(f"复合任务数据已准备: {task_data}")
        
        # 将任务添加到队列
        task_id = add_combined_task(task_data)
        logger.info(f"复合任务已添加到队列，task_id: {task_id}")
        
        return {
            "status": "pending",
            "request_id": request_id,
            "message": "复合任务已提交，请使用request_id查询结果",
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"复合任务请求处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

@router.get("/combined-result", response_class=JSONResponse)
async def get_combined_result(request_id: str, timeout: int = 60):
    """
    获取复合任务结果

    参数:
        request_id: 请求ID（作为查询参数传入）
        timeout: 超时时间(秒)
    """
    try:
        logger.info(f"收到获取复合任务结果请求: request_id={request_id}, timeout={timeout}")
        result = get_combined_task_result(request_id, timeout)
        return result
    except Exception as e:
        logger.error(f"获取复合任务结果失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")