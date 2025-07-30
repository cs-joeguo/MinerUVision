'''
Descripttion: 复合任务消费者：负责处理复合任务队列中的任务，同时执行文本提取和图片描述
Author: Joe Guo
version: 2.0
Date: 2025-07-30 16:16:46
LastEditors: Joe Guo
LastEditTime: 2025-07-30 17:04:05
'''


import logging
import json
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import torch
import requests
from requests.exceptions import RequestException
import aioredis
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    COMBINED_TASK_QUEUE_NAME,
    COMBINED_TASK_RESULT_KEY_PREFIX,
    get_output_dir,
    TASK_QUEUE_NAME,
    TASK_RESULT_KEY_PREFIX,
    IMAGE_TASK_QUEUE_NAME,
    IMAGE_TASK_RESULT_KEY_PREFIX,
    SUPPORTED_FILE_TYPES
)
from utils.file_utils import preprocess_file, normalize_core_files
from utils.minio_utils import upload_to_minio
from services.mineru_service import process_locally, process_remotely
from services.qwen_service import load_qwen_model, extract_images_from_pdf, process_single_image

logger = logging.getLogger("combined_task_consumer")

# 全局模型变量（复用Qwen模型）
qwen_model = None
qwen_processor = None

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


def load_qwen_model_once() -> Tuple[Any, Any]:
    """仅加载一次Qwen模型（单例模式）"""
    global qwen_model, qwen_processor
    if qwen_model is None or qwen_processor is None:
        qwen_model, qwen_processor = load_qwen_model()
    return qwen_model, qwen_processor


async def execute_text_extraction(
    task_id: str,
    input_path: Path,
    extract_params: Dict[str, Any],
    use_remote: bool,
    output_dir: Path
) -> Dict[str, Any]:
    """执行文本提取任务"""
    try:
        if use_remote:
            remote_result = await process_remotely(task_id, input_path, extract_params)
            logger.info(f"远程文本提取完成: {task_id}，设备: {remote_result['device_name']}")
            
            # 处理远程结果的core_files
            remote_core_files = remote_result["remote_result"]["results"].get("core_files", {})
            return {
                "status": "success",
                "core_files": normalize_core_files(remote_core_files)
            }
        else:
            local_result = await process_locally(task_id, input_path, output_dir, extract_params)
            
            if local_result.get("status") == "error":
                return {
                    "status": "error",
                    "error": f"本地处理失败: {local_result['error_message']}"
                }
            
            logger.info(f"本地文本提取完成: {task_id}，使用显卡: {local_result['gpu_id']}")

            # 收集核心文件并标准化键名
            core_files = {}
            for file_path in local_result["output_dir"].rglob("*"):
                if file_path.is_file() and is_core_file(file_path.relative_to(local_result["output_dir"])):
                    rel_path = file_path.relative_to(local_result["output_dir"])
                    url = upload_to_minio(task_id, file_path, "output")
                    core_files[str(rel_path)] = url

            return {
                "status": "success",
                "core_files": normalize_core_files(core_files)
            }
    except Exception as e:
        logger.error(f"文本提取执行失败: {str(e)}")
        return {"status": "error", "error": str(e)}


async def execute_image_description(
    task_id: str,
    input_path: Path,
    pdf_path: Optional[str] = None
) -> Dict[str, Any]:
    """执行图片描述任务"""
    try:
        # 复用全局模型
        model, processor = load_qwen_model_once()
        
        # 确定处理路径，如果有PDF转换结果则使用PDF
        process_path = pdf_path if pdf_path else input_path
        
        # 根据文件类型处理
        file_type = get_file_type(Path(process_path))
        descriptions: List[Dict[str, Any]] = []
        
        if file_type == 'pdf' or (pdf_path and get_file_type(Path(input_path)) == 'office'):
            # 处理PDF文件
            descriptions = extract_images_from_pdf(
                str(process_path),
                model=model,
                processor=processor,
                generate_descriptions=True
            )
        elif file_type == 'image':
            # 处理单张图片
            descriptions = process_single_image(
                str(process_path),
                model=model,
                processor=processor
            )
        
        # 释放Qwen模型显存
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception as e:
                logger.warning(f"释放Qwen模型显存失败: {str(e)}")
        
        return {
            "status": "success",
            "image_count": len(descriptions) if descriptions else 0,
            "descriptions": descriptions
        }
    except Exception as e:
        logger.error(f"图片描述执行失败: {str(e)}")
        return {"status": "error", "error": str(e)}


def is_core_file(file_path: Path) -> bool:
    """判断是否为核心文件(需要返回给用户的文件)"""
    core_extensions = {".md", ".txt", ".json"}
    non_core_dirs = {"images", "layout", "intermediate"}
    
    if any(part in non_core_dirs for part in file_path.parts):
        return False
    
    return file_path.suffix.lower() in core_extensions


def get_file_type(file_path: Path) -> Optional[str]:
    """判断文件类型"""
    file_ext = file_path.suffix.lower()
    for type_name, extensions in SUPPORTED_FILE_TYPES.items():
        if file_ext in extensions:
            return type_name
    return None


async def merge_results(
    extract_result: Dict[str, Any],
    image_result: Dict[str, Any],
    task_id: str,
    output_dir: Path
) -> Dict[str, Any]:
    """合并文本提取结果和图片描述结果"""
    try:
        combined_result = {
            "text_extraction": extract_result,
            "image_description": image_result
        }
        
        # 保存合并结果到JSON文件
        combined_file = output_dir / "combined_result.json"
        with open(combined_file, "w", encoding="utf-8") as f:
            json.dump(combined_result, f, ensure_ascii=False, indent=2)
        
        # 上传合并结果到MinIO
        combined_url = upload_to_minio(task_id, combined_file, "combined_output")
        
        # 如果有Markdown格式的文本结果，创建一个包含图片描述的综合Markdown
        if (extract_result.get("status") == "success" and 
            "result.md" in extract_result.get("core_files", {})):
            
            # 下载文本提取的Markdown结果（带超时和异常处理）
            text_md_url = extract_result["core_files"]["result.md"]
            try:
                text_md_response = requests.get(text_md_url, timeout=10)
                text_md_response.raise_for_status()  # 触发4xx/5xx错误
                text_md_content = text_md_response.text
            except RequestException as e:
                logger.error(f"下载Markdown结果失败: {str(e)}")
                text_md_content = f"[警告：无法加载文本内容，错误：{str(e)}]"
            
            # 创建综合Markdown
            combined_md = output_dir / "combined_result.md"
            with open(combined_md, "w", encoding="utf-8") as f:
                f.write("# 文档内容与图片描述综合结果\n\n")
                f.write("## 一、文档文本内容\n\n")
                f.write(text_md_content)
                f.write("\n\n## 二、图片描述\n\n")
                
                if (image_result.get("status") == "success" and 
                    image_result.get("image_count", 0) > 0):
                    for idx, desc in enumerate(image_result["descriptions"]):
                        f.write(f"### 第 {desc['page']} 页 第 {desc['index']} 张图片\n")
                        f.write(f"概括: {desc['summary']}\n\n")
                        f.write(f"详细描述: {desc['detail']}\n")
                        if idx != len(image_result["descriptions"]) - 1:
                            f.write("\n---\n\n")
                else:
                    f.write("未提取到任何图片或图片描述生成失败。\n")
            
            # 上传综合Markdown到MinIO
            combined_md_url = upload_to_minio(task_id, combined_md, "combined_output")
            return {
                "status": "success",
                "combined_result_url": combined_url,
                "combined_md_url": combined_md_url
            }
        
        return {
            "status": "success",
            "combined_result_url": combined_url
        }
    except Exception as e:
        logger.error(f"结果合并失败: {str(e)}")
        return {"status": "error", "error": str(e)}


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
            
            # 1. 预处理文件（统一处理Office转PDF）
            logger.info(f"开始预处理文件: {input_path}")
            preprocessed = await preprocess_file(
                input_path, 
                libreoffice_path
            )
            pdf_path = str(preprocessed["processed_path"]) if preprocessed["converted_to_pdf"] else None
            
            # 2. 执行文本提取任务
            logger.info(f"开始执行文本提取任务: {request_id}")
            extract_result = await execute_text_extraction(
                request_id, 
                preprocessed["processed_path"], 
                extract_params, 
                use_remote,
                output_dir
            )
            
            if extract_result["status"] == "error":
                raise Exception(f"文本提取失败: {extract_result.get('error', '未知错误')}")
            
            # 3. 执行图片描述任务
            logger.info(f"开始执行图片描述任务: {request_id}")
            image_result = await execute_image_description(
                request_id, 
                input_path,
                pdf_path
            )
            
            if image_result["status"] == "error":
                raise Exception(f"图片描述失败: {image_result.get('error', '未知错误')}")
            
            # 4. 合并结果
            logger.info(f"开始合并结果: {request_id}")
            merge_result = await merge_results(
                extract_result, 
                image_result, 
                request_id, 
                output_dir
            )
            
            if merge_result["status"] == "error":
                raise Exception(f"结果合并失败: {merge_result.get('error', '未知错误')}")
            
            # 5. 准备最终结果
            final_result = {
                "status": "success",
                "request_id": request_id,
                "text_extraction": extract_result,
                "image_description": image_result,
                "combined_results": merge_result
            }
            
            # 如果生成了PDF，将PDF URL添加到结果中
            if preprocessed["converted_to_pdf"]:
                pdf_url = upload_to_minio(request_id, preprocessed["processed_path"], "pdf_output")
                final_result["pdf_url"] = pdf_url
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
    import tempfile  # 延迟导入，避免非主模块执行时的依赖问题
    logging.basicConfig(level=logging.INFO)
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