'''
Descripttion: 文件处理相关工具函数，包括文件类型判断、文件预处理等功能
Author: Joe Guo
version: 
Date: 2025-07-28 14:19:22
LastEditors: Joe Guo
LastEditTime: 2025-07-28 17:13:41
'''

from pathlib import Path
from typing import Optional, Dict, Any
import logging
from config import SUPPORTED_FILE_TYPES

logger = logging.getLogger("file_utils")

def get_file_type(file_path: Path) -> Optional[str]:
    """
    判断文件类型
    
    参数:
        file_path: 文件路径
        
    返回:
        文件类型字符串或None(不支持的类型)
    """
    file_ext = file_path.suffix.lower()
    # 遍历支持的类型，判断扩展名
    for type_name, extensions in SUPPORTED_FILE_TYPES.items():
        if file_ext in extensions:
            return type_name
    return None

def validate_file_type(file_path: Path) -> bool:
    """
    验证文件类型是否支持
    
    参数:
        file_path: 文件路径
        
    返回:
        布尔值，表示是否支持该文件类型
    """
    return get_file_type(file_path) is not None

def is_core_file(file_path: Path) -> bool:
    """
    判断是否为核心文件(需要返回给用户的文件)
    
    参数:
        file_path: 文件路径
        
    返回:
        布尔值，表示是否为核心文件
    """
    core_extensions = {".md", ".txt", ".json"}
    non_core_dirs = {"images", "layout", "intermediate"}
    
    # 跳过非核心目录下的文件
    if any(part in non_core_dirs for part in file_path.parts):
        return False
    
    return file_path.suffix.lower() in core_extensions

async def preprocess_file(input_path: Path, libreoffice_path: Optional[str] = None) -> Dict[str, Any]:
    """
    预处理文件：检查类型并在必要时转换为PDF
    
    参数:
        input_path: 输入文件路径
        libreoffice_path: LibreOffice路径
        
    返回:
        包含处理后路径、原始类型和转换信息的字典
    """
    from services.office_service import convert_to_pdf
    
    file_type = get_file_type(input_path)
    if not file_type:
        raise ValueError(f"不支持的文件类型: {input_path.suffix}")
    
    result = {
        "original_path": input_path,
        "original_type": file_type,
        "processed_path": input_path,
        "converted_to_pdf": False,
        "pdf_url": None
    }
    
    # 如果是Office文件，转换为PDF
    if file_type == 'office':
        logger.info(f"检测到Office文件 {input_path.name}，开始转换为PDF")
        
        pdf_path = convert_to_pdf(str(input_path), libreoffice_path)
        if not pdf_path or not Path(pdf_path).exists():
            raise RuntimeError("Office文件转换为PDF失败")
        
        result.update({
            "processed_path": Path(pdf_path),
            "converted_to_pdf": True,
            "original_path": input_path
        })
    
    return result

def normalize_core_files(core_files: dict) -> dict:
    """
    标准化core_files的键名
    
    参数:
        core_files: 原始核心文件字典
        
    返回:
        标准化后的核心文件字典
    """
    from config import CORE_FILE_KEY_MAPPING
    
    normalized = {}
    for original_key, url in core_files.items():
        # 根据文件后缀和特征选择对应的标准化键名
        for pattern, standard_key in CORE_FILE_KEY_MAPPING.items():
            if pattern in original_key:
                normalized[standard_key] = url
                break
        else:
            # 如果没有匹配到，使用原始文件名作为备份
            normalized[Path(original_key).name] = url
    return normalized
