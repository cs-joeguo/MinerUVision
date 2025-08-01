'''
Descripttion: 文本提取相关服务
Author: Joe Guo
Date: 2025-08-01
'''

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from utils.file_utils import normalize_core_files
from utils.minio_utils import upload_to_minio
from services.mineru_service import process_locally, process_remotely

logger = logging.getLogger("text_extract_service")
logger.setLevel(logging.INFO)


def is_core_file(file_path: Path) -> bool:
    """判断是否为核心文件(需要返回给用户的文件)"""
    core_extensions = {".md", ".txt", ".json"}
    non_core_dirs = {"images", "layout", "intermediate"}
    
    if any(part in non_core_dirs for part in file_path.parts):
        return False
    
    return file_path.suffix.lower() in core_extensions


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
            logger.info(f"开始本地文本提取: {task_id}, 输入路径: {input_path}")
            local_result = await process_locally(task_id, input_path, output_dir, extract_params)
            logger.info(f"本地文本提取结果: {local_result}")
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