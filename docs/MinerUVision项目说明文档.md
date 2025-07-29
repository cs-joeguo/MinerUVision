# MinerUVision项目说明文档 

## 目录 
- [一、项目概述](#一、项目概述) 
- [二、系统架构](#二、系统架构) 
- [三、环境配置](#三、环境配置) 
- [四、API接口说明](#四、API接口说明) 
- [五、部署与运行](#五、部署与运行) 
- [六、扩展与维护](#六、扩展与维护) 
- [七、常见问题](#七、常见问题) 
- [八、版本历史](#八、版本历史) 

## 一、项目概述 
MinerUVision是一个基于FastAPI构建的文件智能处理与分析服务，专注于文本提取和图片内容理解。通过集成多格式文件处理工具、AI视觉语言模型（Qwen2.5-VL）及分布式任务管理能力，实现对PDF、Office文档、图片等文件的自动化处理，支持本地与远程GPU协同工作，适用于文档内容结构化解析、图片智能描述生成等场景。

### 核心功能 
1. **多格式文本提取**：支持从PDF、Word、Excel、PPT等文件中提取文本、表格、公式，支持分页范围指定与格式保留  
2. **图片智能描述**：基于Qwen2.5-VL模型生成图片的概括性描述与详细内容解析，支持单张图片及PDF内嵌图片提取  
3. **分布式任务处理**：通过Redis实现任务队列管理，支持本地GPU与远程设备的任务分配与负载均衡  
4. **文件格式转换**：集成LibreOffice实现Office文件到PDF的自动转换，确保处理兼容性  
5. **设备资源监控**：实时监控本地与远程GPU设备状态、资源占用情况，优化任务调度  
6. **结果持久化存储**：通过MinIO存储原始文件、中间结果及最终处理产物，支持结果URL访问 

## 二、系统架构 
项目采用分层模块化设计，各组件松耦合且职责明确，整体架构分为6层，具体如下：

### 1. 客户端交互层 
- **请求入口**：接收用户上传的文件及处理参数（如提取范围、描述精度等）  
- **结果查询**：提供任务状态与处理结果的查询接口  

### 2. API服务层 
基于FastAPI实现的RESTful接口服务，包含3个核心路由模块：  
- **设备路由（device_routes.py）**：提供本地/远程设备状态查询、资源监控接口（`/devices`）  
- **文本提取路由（extract_routes.py）**：处理文本提取任务提交（`/extract-text`）与结果查询（`/extract-result`）  
- **图片描述路由（image_routes.py）**：处理图片描述任务提交（`/describe-image`）与结果查询（`/image-result`）  
- **健康检查路由**：提供系统组件健康状态检查（`/health`）  

### 3. 任务队列层 
基于Redis实现的异步任务调度系统，包含2类队列：  
- **文本提取队列（TASK_QUEUE_NAME）**：存储待处理的文本提取任务  
- **图片描述队列（IMAGE_TASK_QUEUE_NAME）**：存储待处理的图片描述任务  
- **结果缓存**：以`request_id`为键存储任务处理结果（前缀分别为`TASK_RESULT_KEY_PREFIX`和`IMAGE_TASK_RESULT_KEY_PREFIX`）  

### 4. 任务处理层 
包含2类消费者进程，负责异步处理队列任务：  
- **文本提取消费者（task_consumer.py）**：  
  - 核心逻辑：调用`process_task`函数，实现文件预处理（Office转PDF）、本地/远程处理分发、结果标准化与存储  
  - 处理流程：接收任务→文件预处理→选择本地/远程处理→结果上传MinIO→清理临时文件→更新任务结果  
- **图片描述消费者（image_task_consumer.py）**：  
  - 核心逻辑：调用`process_image_description_task`函数，实现图片提取（PDF内嵌/单张图片）、Qwen模型推理、结果生成  
  - 处理流程：接收任务→文件预处理→加载Qwen模型→提取图片→生成描述→结果上传MinIO→清理临时文件→更新任务结果  

### 5. 核心服务层 
封装核心业务逻辑，包含4个服务模块：  
- **Qwen模型服务（qwen_service.py）**：加载Qwen2.5-VL模型，提供图片描述生成（`qwen_describe_image`）、PDF图片提取（`extract_images_from_pdf`）功能  
- **MinerU处理服务（mineru_service.py）**：实现本地文本提取逻辑（`process_locally`），包含GPU资源分配、命令行调用、结果解析  
- **Office转换服务（office_service.py）**：基于LibreOffice实现Office文件转PDF（`convert_to_pdf`），支持自动查找LibreOffice路径  
- **远程处理服务**：实现远程设备任务分发与结果回收（`process_remotely`）  

### 6. 存储与资源层 
- **MinIO分布式存储**：存储上传文件、转换后的PDF、提取的文本/表格、生成的图片描述文件，通过`minio_utils.py`实现文件上传与URL生成  
- **本地文件系统**：存储临时文件（如上传文件的临时副本、处理中间结果），路径由`OUTPUT_BASE_DIR`配置  
- **GPU资源**：本地GPU（`LOCAL_GPUS`配置）与远程GPU设备（`REMOTE_DEVICES`配置），用于模型推理与文本提取计算  

### 详细架构流程图 
```
┌───────────────┐       ┌─────────────────────────────────────────┐
│   客户端      │       │           API服务层 (FastAPI)           │
│ (文件/查询)   │────▶  │  ┌──────────┐  ┌──────────┐  ┌────────┐  │
└───────────────┘       │  │设备路由   │  │提取路由   │  │图片路由│  │
                        │  │/devices   │  │/extract- │  │/describe│  │
                        │  └──────────┘  │ text     │  │-image   │  │
                        │                └──────────┘  └────────┘  │
                        └────────────────────┬──────────────────────┘
                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         任务队列层 (Redis)                           │
│  ┌─────────────────────┐           ┌─────────────────────┐          │
│  │     文本提取队列    │           │     图片描述队列    │          │
│  │ (mineru_task_queue) │           │ (image_description_ │          │
│  └───────────┬─────────┘           │ queue)              │          │
│              │                     └───────────┬─────────┘          │
│              │                                 │                    │
│  ┌───────────▼─────────┐           ┌───────────▼─────────┐          │
│  │     文本结果缓存    │           │     图片结果缓存    │          │
│  │ (mineru_task_result)│           │ (image_desc_result) │          │
│  └─────────────────────┘           └─────────────────────┘          │
└────────────────────┬──────────────────────────┬─────────────┘
                     │                          │
        ┌────────────▼──────────┐    ┌────────────▼─────────────┐
        │    任务处理层（消费者） │    │                          │
        │                       │    │                          │
        │  ┌────────────────────────┐│  ┌────────────────────┐   │
        │  │     文本提取消费者     ││  │    图片描述消费者   │   │
        │  │ (task_consumer.py)     ││  │ (image_task_consumer.py)│
        │  └───────────┬────────────┘│  └──────────┬─────────┘   │
        │              │             │             │              │
        └──────────────┼─────────────┘             │              │
                       │                           │              │
┌──────────────────────▼───────────────────────────▼──────────────┐
│                          核心服务层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────┐    │
│  │ Qwen模型服务│  │MinerU处理服务│  │Office转换服务│  │远程服务│    │
│  │(qwen_service)│  │(mineru_service)│(office_service)│      │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────┘    │
└──────────────────────┬───────────────────────────┬──────────────┘
                       │                           │
┌──────────────────────▼───────────────────────────▼──────────────┐
│                          存储与资源层                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐       │
│  │ MinIO存储   │  │本地临时存储 │  │ GPU资源 (本地/远程)  │       │
│  │(文件持久化)  │  │(OUTPUT_BASE_DIR)│ (LOCAL/REMOTE_DEVICES) │    │
│  └─────────────┘  └─────────────┘  └─────────────────────┘       │
└───────────────────────────────────────────────────────────────────┘
```

## 三、环境配置 

### 1. 基础环境要求 
- **操作系统**：Linux（推荐Ubuntu 20.04+），支持Windows（需调整路径配置）  
- **Python版本**：3.10（兼容PyTorch与FastAPI）  
- **依赖管理**：Conda（推荐）或pip  
- **硬件要求**：  
  - 本地GPU：NVIDIA GPU（支持CUDA 11.7+，显存≥10GB，推荐≥16GB以运行Qwen2.5-VL-7B）  
  - 内存：≥16GB（处理大文件时需更高）  
  - 磁盘：≥100GB（用于存储模型、临时文件与MinIO数据）  

### 2. 依赖安装 

#### 核心依赖列表（`requirements.txt`） 
```python
fastapi>=0.103.1          # API框架
uvicorn>=0.23.2           # ASGI服务器
minio>=7.2.7              # MinIO客户端
redis>=4.6.0              # Redis客户端
python-multipart>=0.0.6   # 文件上传处理
torch>=2.0.1              # 深度学习框架
transformers>=4.36.2      # 模型加载工具
qwen-vl-utils>=0.0.4      # Qwen模型工具
Pillow>=10.1.0            # 图片处理
PyMuPDF>=1.23.6           # PDF处理（提取图片）
python-dotenv>=1.0.0      # 环境变量管理
psutil>=5.9.6             # 系统资源监控
```

#### 安装命令 
```bash
# 创建并激活Conda环境
conda create -n mineru python=3.9
conda activate mineru

# 安装PyTorch（需匹配CUDA版本，示例为CUDA 11.8）
conda install pytorch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 pytorch-cuda=11.8 -c pytorch -c nvidia

# 安装其他依赖
pip install -r requirements.txt

# 安装LibreOffice（用于Office文件转换）
# Ubuntu: sudo apt-get install libreoffice
# CentOS: sudo yum install libreoffice
```

### 3. 配置文件修改（`config.py`） 
需根据实际环境调整以下核心配置：  
```python
# MinIO配置（必填）
MINIO_ENDPOINT = "192.168.230.27:9000"       # MinIO服务地址
MINIO_ACCESS_KEY = "admin"                    # 访问密钥
MINIO_SECRET_KEY = "Zjtx@2024CgAi"            # 密钥
MINIO_BUCKET = "mineru"                       # 存储桶名称（需提前创建）

# 模型配置（必填）
QWEN_MODEL_PATH = "/root/.cache/modelscope/hub/models/Qwen/Qwen2.5-VL-7B-Instruct"  # 模型本地路径

# 存储与路径配置（必填）
OUTPUT_BASE_DIR = "/data/mineru_output"       # 临时文件存储目录（需提前创建）

# 设备配置（按需调整）
REMOTE_DEVICES = [                            # 远程GPU设备列表
    {
        "name": "gpu-node-1",
        "ip": "192.168.230.29",
        "port": 8000,
        "device_type": "cuda",
        "status": "idle"
    }
]
LOCAL_GPUS = [{"id": 0, "status": "idle"}]    # 本地GPU列表

# Redis配置（必填）
REDIS_HOST = "localhost"
REDIS_PORT = 16379
REDIS_PASSWORD = "Zjtx@2024CgAi"
```

## 四、API接口说明 

### 1. 设备信息接口 
- **路径**：`/devices`  
- **方法**：GET  
- **描述**：查询本地与远程设备状态、资源可用性  
- **返回示例**：  
```json
{
  "local_devices": {
    "gpus": [{"id": 0, "status": "idle"}],
    "mineru_healthy": true,
    "libreoffice_status": "available",
    "libreoffice_path": "/usr/bin/libreoffice",
    "qwen_vl_status": "available",
    "qwen_vl_path": "/root/.cache/modelscope/hub/models/Qwen/Qwen2.5-VL-7B-Instruct"
  },
  "remote_devices": [
    {"name": "gpu-node-1", "ip": "192.168.230.29", "port": 8000, "status": "idle"}
  ]
}
```

### 2. 文本提取接口 

#### 提交任务 
- **路径**：`/extract-text`  
- **方法**：POST  
- **描述**：提交文本提取任务（支持PDF、Office文档）  
- **请求参数**：  
  - `file`：上传的文件（必填，支持`.pdf`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx`）  
  - `method`：处理方法（可选，默认"auto"）  
  - `backend`：后端引擎（可选，默认"auto"）  
  - `lang`：文本语言（可选，默认"zh"）  
  - `formula`：是否提取公式（可选，默认`true`）  
  - `table`：是否提取表格（可选，默认`true`）  
  - `start_page`：开始页码（可选，从1开始）  
  - `end_page`：结束页码（可选）  
  - `use_remote`：是否使用远程设备（可选，默认`false`）  
- **返回示例**：  
```json
{
  "status": "pending",
  "request_id": "a1b2c3d4-5678-90ef-ghij-klmnopqrstuv",
  "message": "任务已提交，请使用request_id查询结果",
  "task_id": 123
}
```

#### 查询结果 
- **路径**：`/extract-result`  
- **方法**：GET  
- **参数**：  
  - `request_id`：任务ID（必填）  
  - `timeout`：超时时间（秒，可选，默认60）  
- **返回示例**（成功）：  
```json
{
  "status": "success",
  "request_id": "a1b2c3d4-5678-90ef-ghij-klmnopqrstuv",
  "core_files": {
    "model_output.txt": "https://minio.example.com/mineru/output/a1b2c3d4/model_output.txt",
    "result.md": "https://minio.example.com/mineru/output/a1b2c3d4/result.md"
  },
  "pdf_url": "https://minio.example.com/mineru/pdf_output/a1b2c3d4/converted.pdf",
  "converted_from_office": true
}
```

### 3. 图片描述接口 

#### 提交任务 
- **路径**：`/describe-image`  
- **方法**：POST  
- **描述**：提交图片描述任务（支持单张图片或PDF中的图片）  
- **请求参数**：  
  - `file`：上传的文件（必填，支持`.jpg`, `.jpeg`, `.png`, `.pdf`）  
  - `libreoffice_path`：LibreOffice路径（可选，自动查找时可不填）  
- **返回示例**：  
```json
{
  "status": "pending",
  "request_id": "z9y8x7w6-5432-10vu-tsrq-ponmlkjihgfe",
  "message": "任务已提交，请使用request_id查询结果",
  "task_id": 124
}
```

#### 查询结果 
- **路径**：`/image-result`  
- **方法**：GET  
- **参数**：  
  - `request_id`：任务ID（必填）  
  - `timeout`：超时时间（秒，可选，默认60）  
- **返回示例**（成功）：  
```json
{
  "status": "success",
  "request_id": "z9y8x7w6-5432-10vu-tsrq-ponmlkjihgfe",
  "image_count": 2,
  "descriptions": [
    {
      "summary": "流程图展示系统架构",
      "detail": "图片为一个系统架构流程图，包含6个层级，分别是客户端交互层、API服务层、任务队列层、任务处理层、核心服务层和存储与资源层，各层级通过箭头连接展示数据流向...",
      "page": 1,
      "index": 1
    },
    {
      "summary": "表格展示设备状态",
      "detail": "图片为一个设备状态表格，包含设备名称、IP地址、端口和状态四列，共2行数据，分别展示本地GPU和远程设备的信息...",
      "page": 2,
      "index": 1
    }
  ],
  "descriptions_url": "https://minio.example.com/mineru/image_descriptions/z9y8x7w6/image_descriptions.md"
}
```

### 4. 健康检查接口 
- **路径**：`/health`  
- **方法**：GET  
- **描述**：检查系统核心组件健康状态  
- **返回示例**：  
```json
{
  "status": "healthy",
  "timestamp": "2025-08-01T14:30:00",
  "services": {
    "minio": {"healthy": true},
    "redis": {"healthy": true},
    "mineru_local": {"healthy": true},
    "libreoffice": {"healthy": true},
    "qwen_vl_model": {"healthy": true},
    "remote_devices": [{"name": "gpu-node-1", "healthy": true}]
  }
}
```

## 五、部署与运行 

### 1. 部署准备 
1. **基础设施部署**：  
   - 启动Redis服务（配置与`config.py`一致）  
   - 启动MinIO服务，创建指定存储桶（`MINIO_BUCKET`）  
   - 下载Qwen2.5-VL模型至`QWEN_MODEL_PATH`（可通过ModelScope或Hugging Face下载）  

2. **权限配置**：  
   - 确保项目目录（含`OUTPUT_BASE_DIR`）有读写权限  
   - 确保MinIO存储桶有读写权限  
   - （远程设备）确保本地服务可访问远程设备的API端口  

### 2. 一键启动（推荐） 
使用项目提供的`scripts/start.sh`脚本启动所有组件：  
```bash
# 1. 修改脚本配置（根据实际环境）
vim scripts/start.sh
# 调整以下参数：
# PROJECT_DIR="/path/to/your/project"  # 项目根目录（含main.py）
# CONDA_ENV="mineru"                   # Conda环境名称
# CONDA_SH_PATH="/path/to/conda.sh"    # Conda配置文件路径

# 2. 赋予执行权限
chmod +x scripts/start.sh

# 3. 启动服务
./scripts/start.sh
```

#### 脚本功能说明 
- 自动创建日志目录（`$PROJECT_DIR/logs`）  
- 检查项目目录、核心脚本及依赖是否存在  
- 停止已运行的服务进程（避免端口占用）  
- 启动3个核心进程：  
  - API服务（日志：`logs/api.log`）  
  - 图片描述消费者（日志：`logs/image_consumer.log`）  
  - 文本提取消费者（日志：`logs/text_consumer.log`）  
- 验证进程启动状态并输出结果  

### 3. 手动启动（调试用） 
```bash
# 激活环境
conda activate mineru

# 启动API服务（默认端口8000）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 启动文本提取消费者（新终端）
python -m tasks.task_consumer

# 启动图片描述消费者（新终端）
python -m tasks.image_task_consumer
```

### 4. 服务验证 
- 访问`http://localhost:8000/devices`查看设备状态，确认所有组件健康  
- 提交测试任务（如上传一个PDF文件调用`/extract-text`），检查任务是否正常处理  
- 查看日志文件排查启动或运行中的错误 

## 六、扩展与维护 

### 1. 功能扩展 

#### 新增文件类型支持 
1. 在`config.py`的`SUPPORTED_FILE_TYPES`中添加文件后缀：  
```python
SUPPORTED_FILE_TYPES = {
    # ... 现有配置 ...
    'new_type': ['.ext1', '.ext2']  # 新增类型
}
```
2. 在`utils/file_utils.py`的`preprocess_file`函数中添加预处理逻辑（如需转换）  
3. 在文本提取/图片描述服务中添加对应类型的处理逻辑  

#### 集成新模型 
1. 在`services/`目录下创建新模型服务文件（如`new_model_service.py`）  
2. 实现模型加载（参考`qwen_service.py`的`load_qwen_model`）与推理接口  
3. 在图片描述消费者中添加模型选择逻辑（可通过任务参数指定模型）  

#### 新增API接口 
1. 在`routes/`目录下创建新路由文件（如`new_routes.py`）  
2. 定义新接口并实现参数验证与任务提交逻辑  
3. 在`main.py`中注册新路由：  
```python
from routes.new_routes import router as new_router
app.include_router(new_router)
```

### 2. 维护建议 
- **日志管理**：  
  - 定期清理日志文件（保留最近30天）  
  - 配置日志轮转（如通过`logrotate`工具）  
- **资源监控**：  
  - 使用`nvidia-smi`监控GPU显存占用，避免OOM（内存溢出）  
  - 监控`OUTPUT_BASE_DIR`磁盘占用，及时清理临时文件  
- **配置备份**：  
  - 定期备份`config.py`与MinIO/Redis配置  
  - 记录远程设备信息与访问凭证  
- **依赖更新**：  
  - 每季度检查依赖更新，优先更新安全补丁  
  - 更新PyTorch时确保与CUDA版本兼容 

## 七、常见问题 

### 1. 服务启动失败 
- **排查步骤**：  
  1. 查看对应日志文件（`api.log`/`image_consumer.log`/`text_consumer.log`）  
  2. 检查Conda环境是否激活：`conda env list`确认`mineru`环境已激活  
  3. 验证核心文件存在：`main.py`、`tasks/task_consumer.py`等  
- **常见原因**：  
  - 端口被占用（修改`uvicorn`启动端口）  
  - 依赖缺失（重新安装`requirements.txt`）  
  - Redis/MinIO服务未启动（检查服务状态）  

### 2. 模型加载失败 
- **排查步骤**：  
  1. 确认`QWEN_MODEL_PATH`路径正确，模型文件完整（无缺失文件）  
  2. 检查GPU显存：`nvidia-smi`确认空闲显存≥10GB  
  3. 查看PyTorch版本与CUDA兼容性：`torch.cuda.is_available()`应返回`True`  
- **解决方案**：  
  - 重新下载模型（可能存在文件损坏）  
  - 关闭其他占用GPU的进程释放显存  
  - 降级PyTorch至兼容版本（如CUDA 11.7对应PyTorch 2.0.1）  

### 3. Office文件转换失败 
- **排查步骤**：  
  1. 检查LibreOffice是否安装：`which libreoffice`应返回路径  
  2. 查看转换日志（文本提取任务的`process.log`）  
- **解决方案**：  
  - 手动指定`libreoffice_path`参数（接口调用时）  
  - 升级LibreOffice至最新版本（支持更多格式）  
  - 对于复杂格式文件，尝试先手动转换为PDF再上传  

### 4. 任务处理超时 
- **排查步骤**：  
  1. 检查任务队列是否积压（Redis中`mineru_task_queue`长度）  
  2. 查看消费者日志，确认是否有任务卡住  
- **解决方案**：  
  - 增加消费者进程数量（启动多个`task_consumer.py`）  
  - 对于大文件，拆分后分批处理  
  - 调整`timeout`参数（最长建议不超过300秒） 

## 八、版本历史 

- **v1.0**（2025-07-29）  
  - 实现文本提取与图片描述核心功能  
  - 集成MinIO存储与Redis任务队列  
  - 支持本地GPU设备处理任务  
  - 提供基础API接口与设备监控功能