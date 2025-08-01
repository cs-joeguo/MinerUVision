'''
Descripttion: 项目所有配置参数
Author: Joe Guo
version: 
Date: 2025-07-25 16:57:01
LastEditors: Joe Guo
LastEditTime: 2025-07-25 16:57:21
'''

import os
import platform
from pathlib import Path
import datetime

# MinIO 配置
MINIO_ENDPOINT = "192.168.230.27:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "Zjtx@2024CgAi"
MINIO_BUCKET = "mineru"
MINIO_SECURE = False

# 服务器配置
MINERU_EXECUTABLE = "mineru"
OUTPUT_BASE_DIR = "/data/mineru_output"
LOCAL_DEVICE_TYPE = "cuda"

# Qwen2.5-VL模型配置
QWEN_MODEL_PATH = "/root/.cache/modelscope/hub/models/Qwen/Qwen2.5-VL-7B-Instruct"

# 远程GPU设备配置
REMOTE_DEVICES = [
    {
        "name": "gpu-node-1",
        "ip": "192.168.230.29",
        "port": 8000,
        "device_type": "cuda",
        "status": "idle"
    }
]

# 本地显卡状态管理
LOCAL_GPUS = [
    {"id": 0, "status": "idle"},
    {"id": 1, "status": "idle"}
]

# Redis 配置
REDIS_HOST = "localhost"
REDIS_PORT = 16379
REDIS_DB = 0
REDIS_PASSWORD = "Zjtx@2024CgAi"
TASK_QUEUE_NAME = "mineru_task_queue"
TASK_RESULT_KEY_PREFIX = "mineru_task_result:"
IMAGE_TASK_QUEUE_NAME = "image_description_queue"
IMAGE_TASK_RESULT_KEY_PREFIX = "image_desc_result:"
COMBINED_TASK_QUEUE_NAME = "combined_task_queue"
COMBINED_TASK_RESULT_KEY_PREFIX = "combined_task_result:"

# 支持的文件类型定义
SUPPORTED_FILE_TYPES = {
    'pdf': ['.pdf'],
    'image': ['.jpg', '.jpeg', '.png'],
    'office': ['.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']
}

# 统一core_files键名的映射关系
CORE_FILE_KEY_MAPPING = {
    '.txt': 'model_output.txt',
    '.md': 'result.md',
    '_middle.json': 'middle.json',
    '_content_list.json': 'content_list.json'
}

# 确保输出目录存在
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

def get_output_dir(request_id: str) -> Path:
    """获取输出目录路径"""
    today = datetime.date.today().isoformat()
    output_dir = Path(OUTPUT_BASE_DIR) / today / request_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir