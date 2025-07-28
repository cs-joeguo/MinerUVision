'''
Descripttion: 文本提取任务消费者，负责处理文本提取任务队列中的任务
Author: Joe Guo
version: 
Date: 2025-07-28 14:19:24
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:13:25
'''

import logging
import json
import asyncio
import shutil
from pathlib import Path
import redis
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    TASK_QUEUE_NAME,
    TASK_RESULT_KEY_PREFIX,
    get_output_dir
)
from utils.file_utils import preprocess_file, is_core_file, normalize_core_files
from utils.minio_utils import upload_to_minio
from services.mineru_service import process_locally, process_remotely

logger = logging.getLogger("task_consumer")

# 初始化Redis客户端
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB, 
    password=REDIS_PASSWORD
)

async def process_task(task):
    """
    处理单个文本提取任务
    
    参数:
        task: 任务数据字典
        
    返回:
        处理结果字典
    """
    request_id = task["request_id"]
    input_path = Path(task["input_path"])
    output_dir = get_output_dir(request_id)
    process_params = task["process_params"]
    use_remote = task["use_remote"]

    try:
        # 预处理文件（统一处理Office转PDF）
        preprocessed = await preprocess_file(
            input_path, 
            process_params.get("libreoffice_path")
        )
        
        # 处理文本提取，根据use_remote选择本地或远程
        if use_remote:
            remote_result = await process_remotely(request_id, preprocessed["processed_path"], process_params)
            logger.info(f"远程处理完成: {request_id}，设备: {remote_result['device_name']}")

            # 处理远程结果的core_files
            remote_core_files = remote_result["remote_result"]["results"].get("core_files", {})
            normalized_core_files = normalize_core_files(remote_core_files)

            result = {
                "status": "success",
                "request_id": request_id,
                "core_files": normalized_core_files
            }
        else:
            local_result = await process_locally(request_id, preprocessed["processed_path"], output_dir, process_params)
            
            if local_result.get("status") == "error":
                error_msg = f"本地处理失败: {local_result['error_message']}"
                logger.error(error_msg)
                
                log_content = ""
                if local_result.get("log_file") and local_result["log_file"].exists():
                    with open(local_result["log_file"], "r") as f:
                        log_content = f.read()
                
                # 清理临时目录
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                    logger.info(f"清理临时目录: {output_dir}")
                
                result = {
                    "status": "error",
                    "request_id": request_id,
                    "error": error_msg
                }
            else:
                logger.info(f"本地处理完成: {request_id}，使用显卡: {local_result['gpu_id']}")

                # 收集核心文件并标准化键名
                core_files = {}
                for file_path in local_result["output_dir"].rglob("*"):
                    if file_path.is_file() and is_core_file(file_path.relative_to(local_result["output_dir"])):
                        rel_path = file_path.relative_to(local_result["output_dir"])
                        url = upload_to_minio(request_id, file_path, "output")
                        core_files[str(rel_path)] = url

                # 标准化core_files键名
                normalized_core_files = normalize_core_files(core_files)

                # 清理临时目录
                shutil.rmtree(output_dir)
                logger.info(f"清理临时目录: {output_dir}")

                result = {
                    "status": "success",
                    "request_id": request_id,
                    "core_files": normalized_core_files
                }
        
        # 如果生成了PDF，将PDF URL添加到结果中
        if preprocessed["converted_to_pdf"]:
            pdf_url = upload_to_minio(request_id, preprocessed["processed_path"], "pdf_output")
            result["pdf_url"] = pdf_url
            result["converted_from_office"] = True

        # 推送结果到Redis队列
        redis_client.rpush(TASK_RESULT_KEY_PREFIX + request_id, json.dumps(result))
        return result

    except Exception as e:
        logger.exception(f"处理异常: {str(e)}")
        
        if 'output_dir' in locals() and output_dir.exists():
            try:
                shutil.rmtree(output_dir)
                logger.info(f"清理临时目录: {output_dir}")
            except Exception as clean_e:
                logger.warning(f"清理临时目录失败: {str(clean_e)}")
        
        error_result = {
            "status": "error",
            "request_id": request_id,
            "error": str(e)
        }
        # 推送错误结果到Redis队列
        redis_client.rpush(TASK_RESULT_KEY_PREFIX + request_id, json.dumps(error_result))
        return error_result

async def task_consumer():
    """文本提取任务消费者主循环"""
    logger.info("文本提取任务消费者已启动")
    while True:
        try:
            # 从队列获取任务
            blpop_result = redis_client.blpop(TASK_QUEUE_NAME, timeout=10)
            if blpop_result is None:
                # 超时无任务，继续循环等待
                continue
            # 有任务时才解包
            _, task_data = blpop_result
            task = json.loads(task_data)
            logger.info(f"开始处理任务: {task['request_id']}")
            await process_task(task)
            logger.info(f"任务处理完成: {task['request_id']}")
        except Exception as e:
            logger.error(f"任务消费者出错: {str(e)}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(task_consumer())
    except KeyboardInterrupt:
        logger.info("任务消费者已停止")