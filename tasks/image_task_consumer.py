'''
Descripttion: 图片描述任务消费者，负责处理图片描述任务队列中的任务
Author: Joe Guo
version: 
Date: 2025-07-28 14:19:24
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:13:14
'''

import logging
import json
import asyncio
import shutil
from pathlib import Path
import redis
import torch
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    IMAGE_TASK_QUEUE_NAME,
    IMAGE_TASK_RESULT_KEY_PREFIX,
    get_output_dir
)
from utils.file_utils import preprocess_file
from utils.minio_utils import upload_to_minio
from services.qwen_service import load_qwen_model, extract_images_from_pdf, process_single_image

logger = logging.getLogger("image_task_consumer")

# 初始化Redis客户端
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB, 
    password=REDIS_PASSWORD
)

async def process_image_description_task(task):
    """
    处理图片描述生成任务
    
    参数:
        task: 任务数据字典
        
    返回:
        处理结果字典
    """
    request_id = task["request_id"]
    input_path = Path(task["input_path"])
    output_dir = get_output_dir(request_id)
    
    try:
        # 预处理文件（统一处理Office转PDF）
        preprocessed = await preprocess_file(
            input_path, 
            task.get("libreoffice_path")
        )
        
        # 加载Qwen模型和处理器
        model, processor = load_qwen_model()
        
        # 根据文件类型处理
        file_type = preprocessed["original_type"]
        descriptions = []
        
        if file_type == 'pdf' or preprocessed["converted_to_pdf"]:
            # 处理PDF文件，提取图片并生成描述
            descriptions = extract_images_from_pdf(
                str(preprocessed["processed_path"]),
                model=model,
                processor=processor,
                generate_descriptions=True
            )
        elif file_type == 'image':
            # 处理单张图片
            descriptions = process_single_image(
                str(preprocessed["processed_path"]),
                model=model,
                processor=processor
            )
        
        # 释放Qwen模型显存
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception as e:
                logger.warning(f"释放Qwen模型显存失败: {str(e)}")
        
        if not descriptions:
            logger.warning(f"未从文件中提取到任何图片: {input_path}")
            result = {
                "status": "success",
                "request_id": request_id,
                "message": "未从文件中提取到任何图片",
                "image_count": 0,
                "descriptions": []
            }
        else:
            # 保存描述结果到markdown文件
            desc_file = output_dir / "image_descriptions.md"
            with open(desc_file, "w", encoding="utf-8") as f:
                for idx, desc in enumerate(descriptions):
                    f.write(f"### 第 {desc['page']} 页 第 {desc['index']} 张图片\n")
                    f.write(f"概括: {desc['summary']}\n\n")
                    f.write(f"详细描述: {desc['detail']}\n")
                    # 最后一条描述后不加分隔线
                    if idx != len(descriptions) - 1:
                        f.write("\n---\n\n")
            
            # 上传描述文件到MinIO
            desc_url = upload_to_minio(request_id, desc_file, "image_descriptions")
            
            result = {
                "status": "success",
                "request_id": request_id,
                "image_count": len(descriptions),
                "descriptions": descriptions,
                "descriptions_url": desc_url
            }
        
        # 如果生成了PDF，将PDF URL添加到结果中
        if preprocessed["converted_to_pdf"]:
            pdf_url = upload_to_minio(request_id, preprocessed["processed_path"], "pdf_output")
            result["pdf_url"] = pdf_url
            result["converted_from_office"] = True
        
        # 清理临时目录
        if output_dir.exists():
            shutil.rmtree(output_dir)
            logger.info(f"清理临时目录: {output_dir}")
        
        # 将结果推送到Redis队列
        redis_client.rpush(IMAGE_TASK_RESULT_KEY_PREFIX + request_id, json.dumps(result))
        return result
        
    except Exception as e:
        logger.exception(f"图片描述任务处理异常: {str(e)}")
        
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
        redis_client.rpush(IMAGE_TASK_RESULT_KEY_PREFIX + request_id, json.dumps(error_result))
        return error_result

async def image_task_consumer():
    """图片描述任务消费者主循环"""
    logger.info("图片描述任务消费者已启动")
    while True:
        try:
            # 从队列获取任务（超时返回None）
            blpop_result = redis_client.blpop(IMAGE_TASK_QUEUE_NAME, timeout=10)
            if blpop_result is None:
                # 超时无任务，继续循环等待
                continue
            # 有任务时才解包
            _, task_data = blpop_result
            task = json.loads(task_data)
            logger.info(f"开始处理图片描述任务: {task['request_id']}")
            await process_image_description_task(task)
            logger.info(f"图片描述任务处理完成: {task['request_id']}")
        except Exception as e:
            logger.error(f"图片描述任务消费者出错: {str(e)}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    try:
        print("启动图片描述任务消费者...")
        loop.run_until_complete(image_task_consumer())
    except KeyboardInterrupt:
        logger.info("图片描述任务消费者已停止")