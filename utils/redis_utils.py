'''
Descripttion: Redis操作工具函数：包括客户端初始化、任务队列操作等功能
Author: Joe Guo
<<<<<<< HEAD
version: 2.0
Date: 2025-07-28 14:19:24
LastEditors: Joe Guo
LastEditTime: 2025-07-30 17:04:46
=======
version: 
Date: 2025-07-30 16:07:26
LastEditors: Joe Guo
LastEditTime: 2025-08-01 15:06:25
>>>>>>> feature/stream
'''


import logging
import json
import redis
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    TASK_QUEUE_NAME,
    TASK_RESULT_KEY_PREFIX,
    IMAGE_TASK_QUEUE_NAME,
    IMAGE_TASK_RESULT_KEY_PREFIX,
    COMBINED_TASK_QUEUE_NAME,
    COMBINED_TASK_RESULT_KEY_PREFIX
)

logger = logging.getLogger("redis_utils")

# 初始化Redis客户端
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB, 
    password=REDIS_PASSWORD
)

def add_extract_task(task_data: dict) -> str:
    """
    添加文本提取任务到队列
    
    参数:
        task_data: 任务数据
        
    返回:
        任务ID
    """
    try:
        task_id = task_data.get("request_id")
        logger.info(f"准备添加文本提取任务到队列: {task_id}")
        redis_client.rpush(TASK_QUEUE_NAME, json.dumps(task_data))
        logger.info(f"添加文本提取任务到队列: {task_id}")
        return task_id
    except Exception as e:
        logger.error(f"添加文本提取任务失败: {str(e)}")
        raise

def get_extract_task_result(task_id: str, timeout: int = 60) -> dict:
    """
    获取文本提取任务结果

    参数:
        task_id: 任务ID
        timeout: 超时时间(秒)

    返回:
        任务结果
    """
    try:
        key = f"{TASK_RESULT_KEY_PREFIX}{task_id}"
        logger.info(f"准备获取文本提取任务结果: {task_id}, timeout={timeout}")
        # 检查键类型，避免WRONGTYPE错误
        key_type = redis_client.type(key)
        if key_type != b'list' and redis_client.exists(key):
            logger.error(f"Redis键类型错误: {key} 类型为 {key_type}")
            return {"status": "error", "message": f"Redis key type error: {key_type.decode()}"}
        result = redis_client.blpop(key, timeout=timeout)
        if result:
            logger.info(f"获取到文本提取任务结果: {task_id}")
            return json.loads(result[1])
        logger.info(f"文本提取任务处理中: {task_id}")
        return {"status": "pending", "message": "任务处理中，请稍后再试"}
    except Exception as e:
        logger.error(f"获取文本提取任务结果失败: {str(e)}")
        raise

def add_image_task(task_data: dict) -> str:
    """
    添加图片描述任务到队列
    
    参数:
        task_data: 任务数据
        
    返回:
        任务ID
    """
    try:
        task_id = task_data.get("request_id")
        logger.info(f"准备添加图片描述任务到队列: {task_id}")
        redis_client.rpush(IMAGE_TASK_QUEUE_NAME, json.dumps(task_data))
        logger.info(f"添加图片描述任务到队列: {task_id}")
        return task_id
    except Exception as e:
        logger.error(f"添加图片描述任务失败: {str(e)}")
        raise

def get_image_task_result(task_id: str, timeout: int = 60) -> dict:
    """
    获取图片描述任务结果

    参数:
        task_id: 任务ID
        timeout: 超时时间(秒)

    返回:
        任务结果
    """
    try:
        key = f"{IMAGE_TASK_RESULT_KEY_PREFIX}{task_id}"
        logger.info(f"准备获取图片描述任务结果: {task_id}, timeout={timeout}")
        # 检查键类型，避免WRONGTYPE错误
        key_type = redis_client.type(key)
        if key_type != b'list' and redis_client.exists(key):
            logger.error(f"Redis键类型错误: {key} 类型为 {key_type}")
            return {"status": "error", "message": f"Redis key type error: {key_type.decode()}"}
        result = redis_client.blpop(key, timeout=timeout)
        if result:
            logger.info(f"获取到图片描述任务结果: {task_id}")
            return json.loads(result[1])
        logger.info(f"图片描述任务处理中: {task_id}")
        return {"status": "pending", "message": "任务处理中，请稍后再试"}
    except Exception as e:
        logger.error(f"获取图片描述任务结果失败: {str(e)}")
        raise

def add_combined_task(task_data: dict) -> str:
    """
    添加复合任务到队列
    
    参数:
        task_data: 任务数据
        
    返回:
        任务ID
    """
    try:
        task_id = task_data.get("request_id")
        logger.info(f"准备添加复合任务到队列: {task_id}")
        redis_client.rpush(COMBINED_TASK_QUEUE_NAME, json.dumps(task_data))
        logger.info(f"添加复合任务到队列: {task_id}")
        return task_id
    except Exception as e:
        logger.error(f"添加复合任务失败: {str(e)}")
        raise

def get_combined_task_result(task_id: str, timeout: int = 60) -> dict:
    """
    获取复合任务结果

    参数:
        task_id: 任务ID
        timeout: 超时时间(秒)

    返回:
        任务结果
    """
    try:
        key = f"{COMBINED_TASK_RESULT_KEY_PREFIX}{task_id}"
        logger.info(f"准备获取复合任务结果: {task_id}, timeout={timeout}")
        # 检查键类型，避免WRONGTYPE错误
        key_type = redis_client.type(key)
        if key_type != b'list' and redis_client.exists(key):
            logger.error(f"Redis键类型错误: {key} 类型为 {key_type}")
            return {"status": "error", "message": f"Redis key type error: {key_type.decode()}"}
        result = redis_client.blpop(key, timeout=timeout)
        if result:
            logger.info(f"获取到复合任务结果: {task_id}")
            return json.loads(result[1])
        logger.info(f"复合任务处理中: {task_id}")
        return {"status": "pending", "message": "任务处理中，请稍后再试"}
    except Exception as e:
        logger.error(f"获取复合任务结果失败: {str(e)}")
        raise