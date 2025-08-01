'''
Descripttion: 复合任务消费者：负责处理复合任务队列中的任务，同时执行文本提取和图片描述
Author: Joe Guo
version: 3.0
Date: 2025-07-30 16:16:46
LastEditors: Joe Guo
LastEditTime: 2025-08-01 15:20:26
'''


import logging
import json
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import torch
import aioredis
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    COMBINED_TASK_QUEUE_NAME,
    COMBINED_TASK_RESULT_KEY_PREFIX,
    SUPPORTED_FILE_TYPES
)
from utils.minio_utils import upload_to_minio
from utils.pdf_utils import convert_to_pdf
from services.pdf_image_service import generate_image_descriptions, replace_images_with_descriptions
from services.text_extract_service import execute_text_extraction

logger = logging.getLogger("combined_task_consumer")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    file_handler = logging.FileHandler("logs/combined_consumer.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    # 可选：同时输出到控制台
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(stream_handler)

# 异步Redis客户端
redis_client: Optional[aioredis.Redis] = None


async def init_redis() -> aioredis.Redis:
    """初始化异步Redis客户端"""
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
            password=REDIS_PASSWORD,
            decode_responses=False  # 保持二进制数据
        )
    return redis_client


def get_file_type(file_path: Path) -> Optional[str]:
    """判断文件类型"""
    file_ext = file_path.suffix.lower()
    for type_name, extensions in SUPPORTED_FILE_TYPES.items():
        if file_ext in extensions:
            return type_name
    return None


async def process_combined_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """处理复合任务"""
    request_id = task["request_id"]
    input_path = Path(task["input_path"])
    extract_params = task["extract_params"]
    use_remote = task.get("use_remote", False)
    libreoffice_path = task.get("libreoffice_path")
    
    try:
        # 使用临时目录自动管理（退出with块时自动删除）
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pdf_output_dir = output_dir / "pdf_files"
            pdf_output_dir.mkdir(exist_ok=True)
            
            # 1. 预处理文件：统一转换为PDF
            logger.info(f"开始预处理文件: {input_path}")
            pdf_path, original_type = convert_to_pdf(
                str(input_path), 
                str(pdf_output_dir),
                libreoffice_path=libreoffice_path
            )
            
            if not pdf_path:
                raise Exception("文件转换为PDF失败")
            
            # 2. 生成PDF中所有图片的描述
            logger.info(f"开始生成图片描述: {request_id}")
            image_descriptions = await generate_image_descriptions(
                request_id, 
                pdf_path
            )
            
            if not image_descriptions:
                logger.warning(f"未提取到任何图片或图片描述生成失败: {request_id}")
                processed_pdf_path = pdf_path
            else:
                # 3. 将图片描述替换回PDF
                logger.info(f"开始替换图片为描述文本: {request_id}")
                processed_pdf_path = str(pdf_output_dir / f"processed_{os.path.basename(pdf_path)}")
                success = replace_images_with_descriptions(
                    pdf_path, 
                    processed_pdf_path, 
                    image_descriptions
                )
                
                if not success:
                    logger.warning("替换图片为描述文本失败，将使用原始PDF进行后续处理")
                    processed_pdf_path = pdf_path
            
            # 4. 基于处理后的PDF执行文本提取任务
            logger.info(f"开始执行文本提取任务: {request_id}")
            extract_result = await execute_text_extraction(
                request_id, 
                Path(processed_pdf_path), 
                extract_params, 
                use_remote,
                output_dir
            )
            
            if extract_result["status"] == "error":
                raise Exception(f"文本提取失败: {extract_result.get('error', '未知错误')}")
            
            # 5. 准备最终结果
            final_result = {
                "status": "success",
                "request_id": request_id,
                "text_extraction": extract_result,
                "image_description_count": len(image_descriptions)
            }
            
            # 上传处理后的PDF
            processed_pdf_url = upload_to_minio(request_id, processed_pdf_path, "processed_pdf")
            final_result["processed_pdf_url"] = processed_pdf_url
            
            # 如果生成了PDF，将原始PDF URL添加到结果中
            if original_type != 'pdf':
                original_pdf_url = upload_to_minio(request_id, pdf_path, "original_pdf")
                final_result["original_pdf_url"] = original_pdf_url
                final_result["converted_from_office"] = True
        
        # 存储结果到Redis（异步操作）
        redis = await init_redis()
        await redis.rpush(COMBINED_TASK_RESULT_KEY_PREFIX + request_id, json.dumps(final_result))
        return final_result
        
    except Exception as e:
        logger.exception(f"复合任务处理异常: {str(e)}")
        
        # 存储错误结果到Redis
        redis = await init_redis()
        error_result = {
            "status": "error",
            "request_id": request_id,
            "error": str(e)
        }
        await redis.rpush(COMBINED_TASK_RESULT_KEY_PREFIX + request_id, json.dumps(error_result))
        return error_result


async def combined_task_consumer():
    """复合任务消费者主循环（带并发控制）"""
    logger.info("复合任务消费者已启动")
    redis = await init_redis()
    semaphore = asyncio.Semaphore(5)  # 限制最大并发数为5
    while True:
        try:
            # 异步从队列获取任务
            task_data = await redis.blpop(COMBINED_TASK_QUEUE_NAME, timeout=10)
            if task_data is None:
                continue  # 超时无任务
            _, task_data = task_data
            task = json.loads(task_data)
            logger.info(f"开始处理复合任务: {task['request_id']}")
            
            # 控制并发执行
            async with semaphore:
                await process_combined_task(task)
            
            logger.info(f"复合任务处理完成: {task['request_id']}")
        except Exception as e:
            logger.error(f"复合任务消费者出错: {str(e)}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    import time  # 延迟导入，避免非主模块执行时的依赖问题
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler("logs/combined_consumer.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    loop = asyncio.get_event_loop()
    try:
        print("启动复合任务消费者...")
        loop.run_until_complete(combined_task_consumer())
    except KeyboardInterrupt:
        logger.info("复合任务消费者已停止")
    finally:
        # 关闭Redis连接
        if redis_client is not None:
            loop.run_until_complete(redis_client.close())
        loop.close()