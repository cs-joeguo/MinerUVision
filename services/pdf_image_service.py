'''
Descripttion: PDF图片处理相关服务
Author: Joe Guo
version: 
Date: 2025-08-01 14:27:20
LastEditors: Joe Guo
LastEditTime: 2025-08-01 15:05:20
'''


import os
import tempfile
import torch
import fitz  # PyMuPDF库
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from utils.pdf_utils import is_image_visible
from services.qwen_service import load_qwen_model_once, process_single_image

logger = logging.getLogger("pdf_image_service")
logger.setLevel(logging.INFO)


def replace_images_with_descriptions(
    pdf_path: str, 
    output_path: str, 
    descriptions: List[Dict[str, Any]]
) -> bool:
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

    # 如果内置字体不可用，尝试通过字体文件路径直接引用
    if used_font is None:
        font_paths = [
            # 项目内字体（优先）
            os.path.join(os.path.dirname(__file__), "..", "utils", "fonts", "simhei.ttf"),
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