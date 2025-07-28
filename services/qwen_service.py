'''
Qwen2.5-VL模型服务
提供图片描述生成功能
'''
import logging
import hashlib
import io
import torch
from PIL import Image
import fitz  # PyMuPDF库
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from config import QWEN_MODEL_PATH
import threading

logger = logging.getLogger("qwen_service")

# 模型全局变量
qwen_model = None
qwen_processor = None
model_lock = threading.Lock()

def load_qwen_model(model_path=QWEN_MODEL_PATH):
    """
    加载Qwen2.5-VL模型和处理器
    
    参数:
        model_path: 模型路径
        
    返回:
        模型和处理器的元组
    """
    global qwen_model, qwen_processor
    try:
        with model_lock:
            if qwen_model is None or qwen_processor is None:
                logger.info(f"开始加载Qwen2.5-VL模型: {model_path}")
                qwen_model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_path,
                    torch_dtype="auto",
                    device_map="auto"
                )
                qwen_processor = AutoProcessor.from_pretrained(model_path)
                logger.info("Qwen2.5-VL模型加载成功")
        return qwen_model, qwen_processor
    except Exception as e:
        raise RuntimeError(f"Qwen模型加载失败: {str(e)}")

def qwen_describe_image(image, model, processor):
    """
    使用Qwen2.5-VL模型生成图片描述
    
    参数:
        image: PIL Image对象
        model: 加载好的Qwen2.5-VL模型
        processor: 对应的处理器
        
    返回:
        包含概括和详细描述的字典
    """
    if not isinstance(image, Image.Image):
        raise TypeError("输入必须是PIL Image对象")
    
    # 构建提示消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},  # 直接传入内存中的图片
                {
                    "type": "text",
                    "text": "请先说明这张图片是什么东西（一句话概括，不加前缀），然后再用一段话详细描述图片中的内容（不要分点，不加任何前缀）。"
                }
            ]
        }
    ]
    
    # 处理输入
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    
    # 设备选择
    device = "cuda" if torch.cuda.is_available() else "cpu"
    inputs = inputs.to(device)
    
    # 模型生成
    generated_ids = model.generate(** inputs, max_new_tokens=512)
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    
    # 拆分结果并处理可能的前缀重复
    parts = output_text.split('\n', 1)
    summary = parts[0].strip() if len(parts) > 0 else ""
    
    # 处理详细描述
    detail = parts[1].strip() if len(parts) > 1 else summary
    for prefix in ["详细描述：", "详细描述: ", "1.", "2.", "- "]:
        if detail.startswith(prefix):
            detail = detail[len(prefix):].strip()
    # 替换可能的分点符号，确保为一段话
    detail = detail.replace("\n", " ").replace("  ", " ").replace("- ", "")
    
    return {"summary": summary, "detail": detail}

def extract_images_from_pdf(pdf_path, model=None, processor=None, generate_descriptions=True):
    """
    从PDF文件中提取图片并生成描述（含去重）
    
    参数:
        pdf_path: PDF文件路径
        model: Qwen模型
        processor: Qwen处理器
        generate_descriptions: 是否生成描述
        
    返回:
        图片描述列表
    """
    try:
        pdf_document = fitz.open(pdf_path)
        logger.info(f"成功打开PDF文件: {pdf_path}，总页数: {len(pdf_document)}")
        
        process_count = 0  # 统计处理的图片数量
        descriptions = []  # 存储所有图片的描述
        seen_image_hashes = set()  # 记录已处理的图片哈希，用于去重
        
        # 遍历每一页
        for page_number in range(len(pdf_document)):
            page = pdf_document[page_number]
            images = page.get_images(full=True)
            
            logger.info(f"第 {page_number + 1} 页发现 {len(images)} 张图片")
            
            # 处理每页中的图片
            for img_index, img in enumerate(images):
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                
                # 计算图片哈希值（用于去重）
                img_hash = hashlib.md5(image_bytes).hexdigest()
                if img_hash in seen_image_hashes:
                    logger.info(f"第 {page_number + 1} 页的第 {img_index + 1} 张图片已处理过，跳过")
                    continue
                seen_image_hashes.add(img_hash)
                
                # 用PIL加载图片到内存
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                except Exception as e:
                    logger.error(f"图片加载失败: {str(e)}，跳过该图片")
                    continue
                
                process_count += 1
                logger.info(f"已处理第 {process_count} 张图片（页码: {page_number + 1}，序号: {img_index + 1}）")
                
                # 生成图片描述
                if generate_descriptions and model and processor:
                    try:
                        desc = qwen_describe_image(image, model, processor)
                        logger.info(f"图片概括: {desc['summary']}")
                        descriptions.append({
                            "summary": desc["summary"],
                            "detail": desc["detail"],
                            "page": page_number + 1,  # 记录图片所在页码
                            "index": img_index + 1    # 记录图片在页内序号
                        })
                    except Exception as e:
                        logger.error(f"生成图片描述时出错: {str(e)}，跳过该图片")
        
        pdf_document.close()
        logger.info(f"图片提取完成，共处理 {process_count} 张图片")
        return descriptions
        
    except Exception as e:
        logger.error(f"处理PDF时出错: {str(e)}")
        return None

def process_single_image(image_path, model, processor):
    """
    处理单张图片并生成描述
    
    参数:
        image_path: 图片路径
        model: Qwen模型
        processor: Qwen处理器
        
    返回:
        图片描述列表
    """
    try:
        image = Image.open(image_path)
        desc = qwen_describe_image(image, model, processor)
        return [{
            "summary": desc["summary"],
            "detail": desc["detail"],
            "page": 1,  # 单张图片视为第1页
            "index": 1   # 单张图片视为第1张
        }]
    except Exception as e:
        logger.error(f"处理图片 {image_path} 时出错: {str(e)}")
        return None