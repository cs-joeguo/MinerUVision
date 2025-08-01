'''
Descripttion: PDF处理相关工具函数
Author: Joe Guo
Date: 2025-08-01
'''

import os
import subprocess
import time
import fitz  # PyMuPDF库
import logging
from typing import Tuple, Optional

logger = logging.getLogger("pdf_utils")
logger.setLevel(logging.INFO)


def find_libreoffice() -> Optional[str]:
    """自动查找LibreOffice的可执行文件路径"""
    if os.name == "nt":  # Windows系统
        possible_paths = [
            "C:\\Program Files\\LibreOffice\\program\\soffice.exe",
            "C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe",
            "C:\\Program Files\\LibreOffice 7\\program\\soffice.exe",
            "C:\\Program Files\\LibreOffice 6\\program\\soffice.exe"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        for path in os.environ["PATH"].split(os.pathsep):
            exe_path = os.path.join(path, "soffice.exe")
            if os.path.exists(exe_path):
                return exe_path
        return None
    else:  # Linux/macOS系统
        possible_paths = [
            "/usr/bin/soffice",
            "/usr/local/bin/soffice",
            "/opt/libreoffice/program/soffice"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None


def find_chinese_font() -> Optional[str]:
    """查找系统中可用的中文字体"""
    if os.name == "nt":  # Windows系统
        font_paths = [
            "C:\\Windows\\Fonts\\simsun.ttc",  # 宋体
            "C:\\Windows\\Fonts\\simhei.ttf",  # 黑体
            "C:\\Windows\\Fonts\\microsoftyahei.ttf",  # 微软雅黑
            "C:\\Windows\\Fonts\\msyh.ttc",  # 微软雅黑
        ]
    elif os.name == "posix":  # Linux/macOS系统
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/Library/Fonts/PingFang.ttc",  # macOS 系统字体
            "/System/Library/Fonts/PingFang.ttc",  # macOS 系统字体
        ]
    else:
        return None

    # 检查字体文件是否存在
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    # 如果没有找到预定义字体，尝试从系统字体中查找
    try:
        import matplotlib.font_manager as fm
        chinese_fonts = [f for f in fm.findSystemFonts() if any(
            font in f.lower() for font in ['simsun', 'simhei', 'microsoftyahei', 'pingfang', 'wqy']
        )]
        if chinese_fonts:
            return chinese_fonts[0]
    except Exception as e:
        logger.warning(f"查找系统字体时出错: {str(e)}")
    
    return None


def convert_to_pdf(
    input_file: str, 
    output_dir: Optional[str] = None, 
    max_attempts: int = 3, 
    libreoffice_path: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """将多种格式文件转换为PDF（支持Word、PowerPoint等）"""
    if not os.path.exists(input_file):
        logger.error(f"文件 '{input_file}' 不存在")
        return None, None
    
    # 确定文件类型
    ext = os.path.splitext(input_file)[1].lower()
    supported_types = {
        '.docx': 'word',
        '.doc': 'word',
        '.pptx': 'powerpoint',
        '.ppt': 'powerpoint',
        '.pdf': 'pdf',
        '.txt': 'text',
        '.md': 'markdown',
        '.jpg': 'image',
        '.jpeg': 'image',
        '.png': 'image'
    }
    
    if ext not in supported_types:
        logger.error(f"不支持的文件类型 '{ext}'")
        return None, None
    original_type = supported_types[ext]
    
    # 如果已是PDF，直接返回
    if original_type == 'pdf':
        return input_file, original_type
    
    # 确定输出路径
    if not output_dir:
        output_dir = os.path.dirname(input_file)
    os.makedirs(output_dir, exist_ok=True)
    
    file_name = os.path.splitext(os.path.basename(input_file))[0]
    pdf_path = os.path.join(output_dir, f"{file_name}.pdf")
    
    # 删除现有PDF（如果存在）
    if os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
            logger.info(f"已删除现有PDF文件: {pdf_path}")
        except Exception as e:
            logger.warning(f"无法删除现有PDF文件 '{pdf_path}': {str(e)}")
            return None, original_type
    
    # 查找LibreOffice
    if not libreoffice_path:
        libreoffice_path = find_libreoffice()
    if not libreoffice_path:
        logger.error("未找到LibreOffice安装路径")
        return None, original_type
    logger.info(f"使用LibreOffice路径: {libreoffice_path}")
    
    # 构建转换命令
    cmd = [
        libreoffice_path,
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        input_file
    ]
    
    # 尝试转换
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )
            
            # 等待转换完成
            time.sleep(2)
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                logger.info(f"成功转换为PDF: {pdf_path}")
                return pdf_path, original_type
            else:
                logger.warning(f"转换尝试 {attempt}/{max_attempts} 失败")
                logger.warning(f"错误输出: {result.stderr}")
                
                if attempt == max_attempts:
                    return None, original_type
                time.sleep(5)
                
        except subprocess.TimeoutExpired:
            logger.warning(f"转换尝试 {attempt}/{max_attempts} 超时")
        except Exception as e:
            logger.warning(f"转换尝试 {attempt}/{max_attempts} 出错: {str(e)}")
            
            if attempt == max_attempts:
                return None, original_type
            time.sleep(5)
    
    return None, original_type


def is_image_visible(page: fitz.Page, xref: int, min_area: int = 100) -> bool:
    """判断图片是否在页面上实际可见"""
    rects = page.get_image_rects(xref)
    if not rects:
        return False
    
    page_rect = page.rect
    page_width = page_rect.width
    page_height = page_rect.height
    
    for rect in rects:
        x0, y0, x1, y1 = rect
        width = x1 - x0
        height = y1 - y0
        area = width * height
        
        if (area > min_area and
            x1 > 0 and
            x0 < page_width and
            y1 > 0 and
            y0 < page_height):
            return True
    
    return False