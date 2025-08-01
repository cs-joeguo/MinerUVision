'''
Descripttion: 复合任务消费者：负责处理复合任务队列中的任务，同时执行文本提取和图片描述
Author: Joe Guo
version: 3.0
Date: 2025-07-30 16:16:46
LastEditors: Joe Guo
LastEditTime: 2025-08-01 11:30:00
'''


import logging
import json
import asyncio
import shutil
import tempfile
import os
import subprocess
import fitz  # PyMuPDF库
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import torch
import requests
from requests.exceptions import RequestException
import aioredis
import re
import hashlib
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
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    file_handler = logging.FileHandler("logs/combined_consumer.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    # 可选：同时输出到控制台
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(stream_handler)

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


def find_libreoffice():
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


def find_chinese_font():
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


def convert_to_pdf(input_file, output_dir=None, max_attempts=3, libreoffice_path=None):
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


def is_image_visible(page, xref, min_area=100):
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

def replace_images_with_descriptions(pdf_path, output_path, descriptions):
    """
    将PDF中的图片替换为AI生成的描述文本
    :param pdf_path: 原始PDF路径
    :param output_path: 替换后PDF保存路径
    :param descriptions: 图片描述列表
    :return: 是否替换成功
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"无法打开PDF文件: {str(e)}")
        return False

    # 配置中文字体（兼容旧版本PyMuPDF）
    used_font = None
    # 尝试直接使用内置中文字体名（无需add_font）
    builtin_chinese_fonts = ["china-s", "simhei", "heiti", "song"]
    for font in builtin_chinese_fonts:
        try:
            # 测试字体是否可用（通过插入一个空文本框验证）
            test_page = doc.new_page()
            test_page.insert_textbox(
                fitz.Rect(100, 100, 200, 200),
                "",  # 空文本
                fontname=font
            )
            doc.delete_page(test_page.number)  # 删除测试页
            used_font = font
            logger.info(f"使用内置中文字体: {font}")
            break
        except:
            continue

    # 如果内置字体不可用，尝试通过字体文件路径直接引用（无需add_font）
    if used_font is None:
        font_paths = [
            # 项目内字体（优先）
            os.path.join(os.path.dirname(__file__), "fonts", "simhei.ttf"),
            # 系统字体
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/Library/Fonts/PingFang.ttc",
            "C:/Windows/Fonts/simhei.ttf"
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                used_font = font_path  # 直接使用字体文件路径
                logger.info(f"使用字体文件: {font_path}")
                break

    # 如果所有字体都不可用，使用默认字体
    if used_font is None:
        logger.warning("未找到可用中文字体，可能导致中文显示异常")
        used_font = "helv"  # 默认字体

    # 创建图片编号映射（按出现顺序）
    xref_to_desc = {desc["xref"]: desc for desc in descriptions}

    for page_num in range(doc.page_count):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        
        # 遍历页面中的图片
        for img in image_list:
            xref = img[0]
            if xref not in xref_to_desc:
                continue

            # 获取图片位置
            rects = page.get_image_rects(xref)
            if not rects:
                continue

            # 获取图片描述
            desc = xref_to_desc[xref]
            summary = desc.get("summary", "无描述")
            detail = desc.get("detail", "")
            text = f"图片描述: {summary}\n{detail}"

            # 处理每个图片位置（可能跨页或多位置）
            for rect in rects:
                # 创建白色覆盖层遮盖原图
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
                
                # 计算文本位置
                font_size = min(rect.width, rect.height) * 0.025
                text_rect = fitz.Rect(
                    rect.x0 + 10, rect.y0 + 10,
                    rect.x1 - 10, rect.y1 - 10
                )

                # 添加文本（使用上面确定的字体）
                page.insert_textbox(
                    text_rect,
                    text,
                    fontsize=font_size,
                    color=(0, 0, 0),
                    fontname=used_font,  # 直接使用字体名或字体文件路径
                    align=fitz.TEXT_ALIGN_LEFT
                )

    # 保存修改后的PDF
    try:
        doc.save(output_path)
        doc.close()
        logger.info(f"已生成替换图片后的PDF: {output_path}")
        return True
    except Exception as e:
        logger.error(f"保存替换后PDF失败: {str(e)}")
        return False

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


async def generate_image_descriptions(
    task_id: str,
    pdf_path: str
) -> List[Dict[str, Any]]:
    """生成PDF中所有可见图片的描述"""
    try:
        # 复用全局模型
        model, processor = load_qwen_model_once()
        logger.info(f"开始为PDF生成图片描述: {task_id}") 

        # 打开PDF
        doc = fitz.open(pdf_path)
        descriptions = []
        processed_xrefs = set()
        
        for page_num, page in enumerate(doc, start=1):
            image_list = page.get_images(full=True)
            
            for img in image_list:
                xref = img[0]
                
                if xref not in processed_xrefs and is_image_visible(page, xref):
                    processed_xrefs.add(xref)
                    
                    # 提取图片数据
                    try:
                        base_image = doc.extract_image(xref)
                        image_data = base_image["image"]
                        
                        # 保存临时图片用于处理
                        with tempfile.NamedTemporaryFile(suffix=f".{base_image['ext']}", delete=False) as f:
                            f.write(image_data)
                            temp_img_path = f.name
                        
                        # 生成图片描述
                        img_desc = process_single_image(temp_img_path, model=model, processor=processor)
                        
                        # 清理临时文件
                        os.unlink(temp_img_path)
                        
                        if img_desc and isinstance(img_desc, list) and len(img_desc) > 0:
                            desc_info = img_desc[0]
                            desc_info["xref"] = xref
                            desc_info["page"] = page_num
                            descriptions.append(desc_info)
                            
                    except Exception as e:
                        logger.error(f"处理图片xref={xref}失败: {str(e)}")
        
        doc.close()
        
        # 释放Qwen模型显存
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                logger.info("已释放Qwen模型显存")
            except Exception as e:
                logger.warning(f"释放Qwen模型显存失败: {str(e)}")
        
        return descriptions
    except Exception as e:
        logger.error(f"图片描述生成失败: {str(e)}")
        return []


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