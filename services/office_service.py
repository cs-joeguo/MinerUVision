'''
Office文档转PDF服务
提供Office文件到PDF的转换功能
'''
import logging
import subprocess
import os
import platform
from pathlib import Path
from config import SUPPORTED_FILE_TYPES

logger = logging.getLogger("office_service")

def find_libreoffice_path():
    """
    自动查找LibreOffice的安装路径

    返回:
        LibreOffice可执行文件路径或None
    """
    system = platform.system()
    logger.info(f"正在检测操作系统: {system}，查找LibreOffice路径")
    
    if system == "Windows":
        possible_paths = [
            "C:/Program Files/LibreOffice/program/soffice.exe",
            "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
            os.path.expanduser("~") + "/AppData/Local/LibreOffice/program/soffice.exe"
        ]
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            os.path.expanduser("~") + "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        ]
    elif system == "Linux":  # Linux
        possible_paths = [
            "/usr/bin/libreoffice",
            "/usr/local/bin/libreoffice",
            "/usr/bin/soffice",
            "/usr/local/bin/soffice"
        ]
    else:
        return None
    
    # 检查路径是否存在
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"检测到LibreOffice路径: {path}")
            return path

    logger.warning("未检测到LibreOffice路径")
    return None

def convert_to_pdf(input_file, libreoffice_path=None):
    """
    将Office文件转换为PDF

    参数:
        input_file: 输入文件路径
        libreoffice_path: LibreOffice路径

    返回:
        转换后的PDF文件路径或None
    """
    # 获取文件扩展名
    file_ext = Path(input_file).suffix.lower()
    file_name = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = os.path.dirname(input_file)
    output_file = os.path.join(output_dir, f"{file_name}.pdf")
    
    # 如果是PDF，不处理
    if file_ext == '.pdf':
        logger.info(f"{input_file} 是PDF文件，不进行处理")
        return input_file
    
    # 检查是否是支持的文件类型
    if file_ext not in SUPPORTED_FILE_TYPES['office']:
        logger.warning(f"不支持的Office文件类型: {file_ext}，支持的类型为: {', '.join(SUPPORTED_FILE_TYPES['office'])}")
        return None
    
    # 查找LibreOffice路径
    if not libreoffice_path:
        libreoffice_path = find_libreoffice_path()
        if not libreoffice_path:
            logger.error("未找到LibreOffice安装路径，请手动指定或安装LibreOffice")
            return None
    
    try:
        logger.info(f"开始将文件 {input_file} 转换为PDF，输出目录: {output_dir}")
        # 构建转换命令
        cmd = [
            libreoffice_path,
            "--headless",           # 无头模式，不显示界面
            "--convert-to", "pdf",  # 转换为PDF
            "--outdir", output_dir, # 输出目录
            input_file              # 输入文件
        ]
        
        # 执行转换命令
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        logger.info(f"LibreOffice转换命令执行完成，返回码: {result.returncode}")
        # 检查转换是否成功
        if result.returncode == 0 and os.path.exists(output_file):
            logger.info(f"文件 {input_file} 已成功转换为PDF: {output_file}")
            return output_file
        else:
            logger.error(f"转换失败，错误信息: {result.stderr}")
            return None
    
    except Exception as e:
        logger.error(f"转换过程中发生错误: {str(e)}")
        return None