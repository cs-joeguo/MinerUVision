'''
Descripttion: MinIO操作工具函数，包括客户端初始化、文件上传等功能
Author: Joe Guo
version: 
Date: 2025-07-25 16:59:03
LastEditors: Joe Guo
LastEditTime: 2025-08-01 10:00:00
'''

import logging
import datetime
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from fastapi import HTTPException
from config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    MINIO_BUCKET
)

logger = logging.getLogger("minio_utils")

# 初始化MinIO客户端
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

# 确保存储桶存在
if not minio_client.bucket_exists(MINIO_BUCKET):
    minio_client.make_bucket(MINIO_BUCKET)
    logger.info(f"创建MinIO存储桶: {MINIO_BUCKET}")
else:
    logger.info(f"MinIO存储桶已存在: {MINIO_BUCKET}")

def upload_to_minio(request_id: str, file_path: [str, Path], object_prefix: str = "") -> str:
    """
    上传文件到MinIO
    
    参数:
        request_id: 请求ID
        file_path: 本地文件路径（可以是字符串或Path对象）
        object_prefix: 对象前缀
        
    返回:
        预签名的文件URL
    """
    # 确保file_path是Path对象
    if isinstance(file_path, str):
        file_path = Path(file_path)
    
    # 构建对象名，包含日期、请求ID、前缀和文件名
    today = datetime.date.today().isoformat()
    object_name = f"{today}/{request_id}/{object_prefix}/{file_path.name}"
    
    try:
        logger.info(f"准备上传文件到MinIO: {file_path} -> {object_name}")
        # 上传文件
        minio_client.fput_object(
            MINIO_BUCKET,
            object_name,
            str(file_path)
        )
        
        # 获取预签名下载链接
        presigned_url = minio_client.presigned_get_object(
            MINIO_BUCKET,
            object_name,
            expires=datetime.timedelta(days=7)
        )
        
        logger.info(f"文件上传成功: {file_path} -> {presigned_url}")
        return presigned_url
    except S3Error as e:
        logger.error(f"MinIO上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO上传失败: {e.message}")

def upload_directory_to_minio(request_id: str, dir_path: [str, Path], prefix: str = "") -> dict:
    """
    上传目录到MinIO
    
    参数:
        request_id: 请求ID
        dir_path: 本地目录路径（可以是字符串或Path对象）
        prefix: 前缀
        
    返回:
        包含文件名和对应URL的字典
    """
    # 确保dir_path是Path对象
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)
    
    result = {}
    
    # 遍历目录下所有文件，递归上传
    for file_path in dir_path.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(dir_path)
            logger.info(f"准备上传目录文件到MinIO: {file_path}")
            presigned_url = upload_to_minio(request_id, file_path, f"{prefix}/{rel_path.parent}")
            result[str(rel_path)] = presigned_url
    
    logger.info(f"目录上传完成: {dir_path}")
    return result
