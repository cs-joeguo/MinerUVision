'''
Descripttion: 文本提取接口，提供文件上传和文本提取功能
Author: Joe Guo
version: 
Date: 2025-07-28 14:19:24
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:11:30
'''

import logging
import uuid
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile
from config import get_output_dir
from utils.redis_utils import add_extract_task, get_extract_task_result

router = APIRouter()
logger = logging.getLogger("extract_routes")

@router.post("/extract-text", response_class=JSONResponse)
async def extract_text(
    file: UploadFile = File(...),
    method: str = Form("auto"),
    backend: str = Form("auto"),
    lang: str = Form("zh"),
    formula: bool = Form(True),
    table: bool = Form(True),
    start_page: int = Form(None),
    end_page: int = Form(None),
    sglang_url: str = Form(None),
    source: str = Form("user_upload"),
    return_all_files: bool = Form(False),
    use_remote: bool = Form(False)
):
    """
    文本提取接口
    
    参数:
        file: 上传的文件
        method: 处理方法
        backend: 后端引擎
        lang: 语言
        formula: 是否提取公式
        table: 是否提取表格
        start_page: 开始页码
        end_page: 结束页码
        sglang_url: sglang服务地址
        source: 来源标识
        return_all_files: 是否返回所有文件
        use_remote: 是否使用远程设备处理
    """
    try:
        # 生成唯一请求ID
        request_id = str(uuid.uuid4())
        logger.info(f"收到文本提取请求: {request_id}, 文件名: {file.filename}")
        
        # 保存上传的文件到临时位置
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            file_bytes = await file.read()  # 读取上传文件内容
            temp_file.write(file_bytes)     # 写入临时文件
            temp_file_path = temp_file.name # 获取临时文件路径
            logger.info(f"文件已保存到临时路径: {temp_file_path}，大小: {len(file_bytes)} 字节")
        
        # 准备任务参数
        process_params = {
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
        logger.info(f"任务参数: {process_params}")
        
        # 创建任务数据
        task_data = {
            "request_id": request_id,
            "input_path": temp_file_path,
            "process_params": process_params,
            "use_remote": use_remote
        }
        logger.info(f"任务数据已准备: {task_data}")
        
        # 将任务添加到队列
        task_id = add_extract_task(task_data)
        logger.info(f"任务已添加到队列，task_id: {task_id}")
        
        return {
            "status": "pending",
            "request_id": request_id,
            "message": "任务已提交，请使用request_id查询结果",
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"文本提取请求处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

@router.get("/extract-result", response_class=JSONResponse)
async def get_extract_result(request_id: str, timeout: int = 60):
    """
    获取文本提取结果

    参数:
        request_id: 请求ID（作为查询参数传入）
        timeout: 超时时间(秒)
    """
    try:
        logger.info(f"收到获取文本提取结果请求: request_id={request_id}, timeout={timeout}")
        result = get_extract_task_result(request_id, timeout)  # 查询任务结果
        # logger.info(f"获取结果: {result}")
        return result
    except Exception as e:
        logger.error(f"获取文本提取结果失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")