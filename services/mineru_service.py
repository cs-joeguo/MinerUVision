'''
MinerU处理服务
提供本地和远程MinerU处理功能
'''
import logging
import os
import subprocess
import asyncio
import requests
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import GPUtil
import torch
from config import (
    MINERU_EXECUTABLE,
    REMOTE_DEVICES,
    LOCAL_GPUS
)

logger = logging.getLogger("mineru_service")

# GPU状态管理
gpu_status = []
sync_gpu_lock = asyncio.Lock()
async_gpu_lock = asyncio.Lock()
gpu_semaphore = None

async def init_gpu_resources():  # 改为异步函数
    global gpu_status, gpu_semaphore
    async with sync_gpu_lock:  # 异步获取锁
        gpus = GPUtil.getGPUs()
        gpu_status = []
        for gpu in gpus:
            if gpu.memoryTotal > 0:
                gpu_status.append({
                    "id": gpu.id,
                    "status": "idle",
                    "memory_total": gpu.memoryTotal
                })
        gpu_count = len(gpu_status)
        gpu_semaphore = asyncio.Semaphore(gpu_count) if gpu_count > 0 else asyncio.Semaphore(0)
        logger.info(f"动态检测到 {gpu_count} 个可用GPU: {[g['id'] for g in gpu_status]}")

async def get_available_gpus(min_memory_mb):
    """
    获取可用GPU列表
    
    参数:
        min_memory_mb: 最小可用内存(MB)
        
    返回:
        可用GPU列表
    """
    async with async_gpu_lock:
        available = []
        for gpu in gpu_status:
            if gpu["status"] == "idle":
                try:
                    gpu_obj = GPUtil.getGPUs()[gpu["id"]]
                    if gpu_obj.memoryFree >= min_memory_mb:
                        available.append((gpu["id"], gpu_obj.memoryFree))
                except Exception as e:
                    logger.warning(f"检测GPU {gpu['id']} 状态失败: {e}")
        logger.info(f"可用GPU列表: {available}")
        return available

async def process_locally(request_id: str, input_path: Path, output_dir: Path, params: dict) -> dict:
    """
    本地处理文件
    
    参数:
        request_id: 请求ID
        input_path: 输入文件路径
        output_dir: 输出目录
        params: 处理参数
        
    返回:
        处理结果字典
    """
    global gpu_status, gpu_semaphore
    

    await init_gpu_resources()  # 添加 await 关键字
    if not gpu_status:
        logger.error("未检测到可用GPU")
        raise RuntimeError("未检测到可用GPU")

    min_memory_ratio = 0.7
    async with async_gpu_lock:
        if gpu_status:
            avg_total_memory = sum(g["memory_total"] for g in gpu_status) / len(gpu_status)
            min_required_memory = int(avg_total_memory * min_memory_ratio)
        else:
            min_required_memory = 12288
    
    async with gpu_semaphore:
        selected_gpu_id = None
        max_attempts = 10
        
        for attempt in range(max_attempts):
            available_gpus = await get_available_gpus(min_required_memory)
            logger.info(f"尝试第 {attempt+1} 次获取可用GPU，结果: {available_gpus}")
            if available_gpus:
                available_gpus.sort(key=lambda x: x[1], reverse=True)
                selected_gpu_id = available_gpus[0][0]
                
                async with async_gpu_lock:
                    for gpu in gpu_status:
                        if gpu["id"] == selected_gpu_id:
                            gpu["status"] = "busy"
                            logger.info(f"分配GPU {selected_gpu_id} 处理任务 {request_id}")
                            break
                break
            else:
                wait_time = 15 * (attempt + 1)
                logger.info(f"没有足够内存的GPU，尝试 {attempt+1}/{max_attempts}，等待{wait_time}秒...")
                await asyncio.sleep(wait_time)
        
        if selected_gpu_id is None:
            logger.error("多次尝试后仍没有可用的本地显卡")
            raise RuntimeError("多次尝试后仍没有可用的本地显卡")
        
        try:
            mineru_output_dir = output_dir / "output"
            mineru_output_dir.mkdir(exist_ok=True)
            logger.info(f"创建输出目录: {mineru_output_dir}")
            
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
            os.environ["CUDA_LAUNCH_BLOCKING"] = "1"
            
            cmd = [
                MINERU_EXECUTABLE,
                "-p", str(input_path),
                "-o", str(mineru_output_dir),
                "-m", params["method"],
                "-b", params["backend"],
                "-l", params["lang"],
                "--formula", str(params["formula"]).lower(),
                "--table", str(params["table"]).lower(),
                "--device", f"cuda:{0}",
                "--source", params["source"]
            ]
            
            if params["start_page"] is not None:
                cmd.extend(["-s", str(params["start_page"])])
            if params["end_page"] is not None:
                cmd.extend(["-e", str(params["end_page"])])
            if params["backend"] == "vlm-sglang-client" and params["sglang_url"]:
                cmd.extend(["-u", params["sglang_url"]])
            
            available_memory = "N/A"
            try:
                gpu_info = await get_available_gpus(min_required_memory)
                if gpu_info:
                    available_memory = f"{gpu_info[0][1]/1024:.2f} GB"
            except Exception as e:
                logger.warning(f"获取GPU内存信息失败: {e}")
            
            logger.info(f"在本地执行命令: {' '.join(cmd)}，使用实际显卡ID: {selected_gpu_id}，可用内存: {available_memory}")

            log_file = output_dir / "process.log"
            sub_env = os.environ.copy()
            sub_env["CUDA_VISIBLE_DEVICES"] = str(selected_gpu_id)
            
            with open(log_file, "w") as log_f:
                process = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT, text=True, env=sub_env)
                process.wait()
            
            logger.info(f"MinerU本地处理完成，返回码: {process.returncode}")
            if process.returncode != 0:
                error_msg = f"MinerU本地处理失败 (code: {process.returncode})"
                logger.error(error_msg)
                with open(log_file, "r") as f:
                    log_content = f.read()
                raise RuntimeError(f"{error_msg}\n日志详情:\n{log_content}")
            
            return {
                "output_dir": mineru_output_dir,
                "log_file": log_file,
                "gpu_id": selected_gpu_id,
                "status": "success"
            }
        
        except Exception as e:
            logger.error(f"处理请求 {request_id} 时发生异常: {str(e)}")
            return {
                "gpu_id": selected_gpu_id,
                "status": "error",
                "error_message": str(e),
                "log_file": output_dir / "process.log" if output_dir else None
            }
        
        finally:
            if selected_gpu_id is not None:
                async with async_gpu_lock:
                    for gpu in gpu_status:
                        if gpu["id"] == selected_gpu_id:
                            gpu["status"] = "idle"
                            logger.info(f"释放GPU {selected_gpu_id}，状态重置为idle")
                            break
                
                try:
                    if torch.cuda.is_available():
                        torch.cuda.synchronize(device=selected_gpu_id)
                        torch.cuda.empty_cache()
                    logger.info(f"已释放GPU {selected_gpu_id} 资源")
                except Exception as e:
                    logger.warning(f"释放GPU缓存失败: {str(e)}")

def check_remote_health(device: dict) -> bool:
    """
    检查远程设备健康状态
    
    参数:
        device: 设备信息字典
        
    返回:
        布尔值，表示设备是否健康
    """
    try:
        url = f"http://{device['ip']}:{device['port']}/health"
        logger.info(f"检查远程设备健康: {device['name']} {url}")
        response = requests.get(url, timeout=5)
        logger.info(f"远程设备 {device['name']} 健康检查返回码: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"远程设备 {device['name']} 健康检查失败: {str(e)}")
        return False

def get_available_remote_device() -> Optional[dict]:
    """
    获取可用的远程设备
    
    返回:
        可用设备信息或None
    """
    for device in REMOTE_DEVICES:
        health_status = check_remote_health(device)
        device["status"] = "idle" if health_status else "error"
        logger.info(f"远程设备 {device['name']} 状态: {device['status']}")
    
    for device in REMOTE_DEVICES:
        if device["status"] == "idle":
            return device
    return None

def mark_device_status(device_name: str, status: str) -> None:
    """
    更新设备状态
    
    参数:
        device_name: 设备名称
        status: 状态值
    """
    for device in REMOTE_DEVICES:
        if device["name"] == device_name:
            device["status"] = status
            logger.info(f"设置远程设备 {device_name} 状态为: {status}")
            break

async def process_remotely(request_id: str, input_path: Path, params: dict, max_retries=3) -> dict:
    """
    远程处理文件
    
    参数:
        request_id: 请求ID
        input_path: 输入文件路径
        params: 处理参数
        max_retries: 最大重试次数
        
    返回:
        处理结果字典
    """
    retries = 0
    while retries < max_retries:
        device = get_available_remote_device()
        if not device:
            logger.error("没有可用的远程设备")
            raise RuntimeError("没有可用的远程设备")
        
        mark_device_status(device["name"], "busy")
        logger.info(f"使用远程设备 {device['name']} ({device['ip']}:{device['port']}) 处理任务 {request_id} (尝试 {retries+1}/{max_retries})")
        
        try:
            with open(input_path, "rb") as f:
                file_content = f.read()
            logger.info(f"读取输入文件 {input_path}，大小: {len(file_content)} 字节")
            
            url = f"http://{device['ip']}:{device['port']}/extract-text"
            files = {"file": (input_path.name, file_content, "application/octet-stream")}
            
            data = {
                "method": params["method"],
                "backend": params["backend"],
                "lang": params["lang"],
                "formula": str(params["formula"]).lower(),
                "table": str(params["table"]).lower(),
                "device": device["device_type"],
                "source": params["source"],
                "return_all_files": str(params["return_all_files"]).lower()
            }
            
            if params["start_page"] is not None:
                data["start_page"] = str(params["start_page"])
            if params["end_page"] is not None:
                data["end_page"] = str(params["end_page"])
            if params["sglang_url"]:
                data["sglang_url"] = params["sglang_url"]
            
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('http://', adapter)
            
            logger.info(f"向远程设备 {device['name']} 发送POST请求: {url}，参数: {data}")
            response = session.post(
                url, 
                files=files, 
                data=data, 
                timeout=(10, 3600)
            )
            
            logger.info(f"远程设备 {device['name']} 返回状态码: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"远程处理失败: {response.text}")
                raise RuntimeError(f"远程处理失败: {response.text}")
            
            result = response.json()
            if result.get("status") != "success":
                logger.error(f"远程处理返回错误: {result.get('message', '未知错误')}")
                raise RuntimeError(f"远程处理返回错误: {result.get('message', '未知错误')}")
            
            logger.info(f"远程处理成功，设备: {device['name']}")
            return {
                "remote_result": result,
                "device_name": device["name"]
            }
        
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            retries += 1
            logger.warning(f"远程处理连接失败 (尝试 {retries}/{max_retries}): {str(e)}")
            await asyncio.sleep(2 **retries)
        except Exception as e:
            logger.error(f"远程处理发生未知错误: {str(e)}")
            raise
        finally:
            mark_device_status(device["name"], "idle")
            logger.info(f"远程设备 {device['name']} 状态重置为idle")
    
    logger.error(f"远程处理失败，已达到最大重试次数 ({max_retries})")
    raise RuntimeError(f"远程处理失败，已达到最大重试次数 ({max_retries})")