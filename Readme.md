# MinerUVision

MinerUVision 是一个基于 FastAPI 构建的文档智能处理服务，专注于提供图片理解和多格式文本提取功能。该系统集成了先进的 Qwen2.5-VL 视觉语言模型，能够对图像内容进行深度分析，并支持多种办公文档格式的处理与存储管理。

## 功能特点



*   **图像智能理解**：对图片或 PDF 中的图像内容进行分析，生成精准的概括性描述和详细说明

*   **多格式文本提取**：支持从 PDF、Office 文档（Word、Excel、PowerPoint）和图片中提取文本内容

*   **高级内容识别**：能够识别并提取文档中的公式、表格等结构化信息

*   **分布式处理架构**：支持本地 GPU 加速和远程设备协同处理，优化资源利用

*   **异步任务管理**：通过 Redis 实现任务队列，支持大文件异步处理和结果查询

*   **安全文件存储**：集成 MinIO 进行文件的安全存储、管理和访问控制

## 技术栈



*   **后端框架**：FastAPI（高性能 API 开发框架）

*   **视觉语言模型**：Qwen2.5-VL-7B-Instruct（用于图像理解和描述生成）

*   **文件存储**：MinIO（兼容 S3 的对象存储服务）

*   **任务队列**：Redis（用于任务调度和结果缓存）

*   **文档处理**：


    *   PyMuPDF（PDF 处理）

    *   LibreOffice（Office 文档转换）

    *   python-multipart（文件上传处理）

*   **部署**：UVicorn（ASGI 服务器）

*   **并行处理**：concurrent.futures（异步任务处理）

## 环境要求



*   Python 3.8 及以上版本

*   Conda 环境（推荐，便于依赖管理）

*   CUDA 11.7+（可选，用于 GPU 加速模型推理）

*   至少 16GB 内存（处理大型文档和模型加载）

*   LibreOffice 7.0+（用于 Office 文档转换）

*   Redis 6.2+（任务队列）

*   MinIO 服务器（文件存储）

## 安装步骤



1.  **克隆代码库**



```
git clone https://github.com/cs-joeguo/MinerUVision.git

cd MinerUVision
```



1.  **创建并激活 Conda 环境**



```
conda create -n mineru python=3.9

conda activate mineru
```



1.  **安装依赖包**



```
\# 安装 Python 依赖

pip install -r requirements.txt

\# 安装 LibreOffice（根据操作系统选择相应方法）

\# Ubuntu/Debian

sudo apt-get install libreoffice

\# CentOS/RHEL

sudo yum install libreoffice

\# macOS

brew install libreoffice
```



1.  **模型准备**

    下载 Qwen2.5-VL-7B-Instruct 模型，并放置在指定目录，然后在配置文件中更新模型路径。

2.  **环境配置**

    编辑 `config.py` 文件，配置以下关键参数：



```
\# MinIO 配置

MINIO\_ENDPOINT = "localhost:9000"

MINIO\_ACCESS\_KEY = "your-access-key"

MINIO\_SECRET\_KEY = "your-secret-key"

MINIO\_BUCKET = "mineru-bucket"

\# 模型配置

QWEN\_MODEL\_PATH = "/path/to/qwen2.5-vl-7b-instruct"

DEVICE = "cuda"  # 或 "cpu" 如果没有GPU

\# Redis 配置

REDIS\_HOST = "localhost"

REDIS\_PORT = 6379

REDIS\_DB = 0

\# 服务配置

API\_PORT = 8001

LIBREOFFICE\_PATH = "/usr/bin/libreoffice"  # 根据实际安装路径调整
```

## 启动服务

使用提供的启动脚本一键启动所有服务组件：



```
bash scripts/start.sh
```

该脚本会启动以下服务：



*   FastAPI 主服务（默认端口 8001）

*   图片描述任务消费者

*   文本提取任务消费者

如需单独启动某个组件：



```
\# 启动 API 服务

python main.py

\# 启动图片描述任务消费者

python tasks/image\_consumer.py

\# 启动文本提取任务消费者

python tasks/text\_consumer.py
```

## API 接口文档

服务启动后，可通过以下地址访问交互式 API 文档：



*   **Swagger UI**: [http://localhost](http://localhost:8001/docs)[:8001/](http://localhost:8001/docs)[docs](http://localhost:8001/docs)


    *   提供完整的 API 列表和交互式测试功能

*   **ReDoc**: [http://localhost](http://localhost:8001/redoc)[:8001/](http://localhost:8001/redoc)[redoc](http://localhost:8001/redoc)


    *   提供更详细的 API 文档和结构说明

### 主要 API 接口

#### 图片描述接口



1.  **提交图片描述任务**

*   端点: `POST /describe-image`

*   参数:


    *   `file`: 上传的图片或 PDF 文件

    *   `detail_level`: 描述详细程度（可选，默认: medium）

*   返回：包含任务 ID 的 JSON 响应，用于查询结果

1.  **查询图片描述结果**

*   端点: `GET /image-result?task_id={task_id}`

*   参数: `task_id`: 任务 ID

*   返回：包含图片描述结果的 JSON 响应

#### 文本提取接口



1.  **提交文本提取任务**

*   端点: `POST /extract-text`

*   参数:


    *   `file`: 上传的文档文件（支持 PDF、Office 文档、图片）

    *   `extract_tables`: 是否提取表格（可选，默认: true）

    *   `extract_formulas`: 是否提取公式（可选，默认: true）

*   返回：包含任务 ID 的 JSON 响应

1.  **查询文本提取结果**

*   端点: `GET /extract-result?task_id={task_id}`

*   参数: `task_id`: 任务 ID

*   返回：包含提取的文本、表格和公式的 JSON 响应

#### 系统信息接口



1.  **健康检查**

*   端点: `GET /health`

*   返回：系统健康状态信息

1.  **设备状态查询**

*   端点: `GET /devices`

*   返回：可用计算设备（CPU/GPU）状态信息

## 项目结构



```
MinerUVision/

├── routes/                  # API 路由定义

│   ├── \_\_init\_\_.py

│   ├── image\_routes.py      # 图片描述相关路由

│   ├── text\_routes.py       # 文本提取相关路由

│   └── system\_routes.py     # 系统信息相关路由

├── services/                # 核心业务逻辑

│   ├── \_\_init\_\_.py

│   ├── image\_service.py     # 图片处理服务

│   ├── text\_service.py      # 文本提取服务

│   └── storage\_service.py   # MinIO 存储服务

├── tasks/                   # 任务处理

│   ├── \_\_init\_\_.py

│   ├── image\_consumer.py    # 图片描述任务消费者

│   ├── text\_consumer.py     # 文本提取任务消费者

│   └── task\_queue.py        # 任务队列管理

├── utils/                   # 工具函数

│   ├── \_\_init\_\_.py

│   ├── document\_utils.py    # 文档处理工具

│   ├── model\_utils.py       # 模型加载和推理工具

│   └── logger.py            # 日志配置

├── config.py                # 全局配置参数

├── main.py                  # 应用入口点

├── requirements.txt         # 项目依赖列表

├── scripts/                 # 脚本文件

│   ├── start.sh             # 启动所有服务

│   └── stop.sh              # 停止所有服务

└── logs/                    # 日志文件（运行时生成）

&#x20;   ├── api.log

&#x20;   ├── image\_consumer.log

&#x20;   └── text\_consumer.log
```

## 日志管理

系统日志默认保存在 `logs` 目录下，包含三类日志：



*   `api.log`: API 服务访问和错误日志

*   `image_consumer.log`: 图片描述任务处理日志

*   `text_consumer.log`: 文本提取任务处理日志

日志配置可在 `utils/``logger.py` 中调整，包括日志级别、格式和滚动策略。

## 使用示例

### 图片描述示例



1.  提交图片描述任务：



```
curl -X POST "http://localhost:8001/describe-image" -H "accept: application/json" -H "Content-Type: multipart/form-data" -F "file=@example.jpg;type=image/jpeg"
```

返回结果：



```
{"task\_id": "abc123456", "status": "pending"}
```



1.  查询结果：



```
curl "http://localhost:8001/image-result?task\_id=abc123456"
```

返回结果：



```
{

&#x20; "task\_id": "abc123456",

&#x20; "status": "completed",

&#x20; "summary": "一张包含办公桌和电脑的办公室照片",

&#x20; "details": "图片展示了一个现代化的办公环境，中央是一张木质办公桌，上面放置了一台笔记本电脑、一个台灯和一些文件。背景中可以看到书架和窗户，整体环境整洁有序。",

&#x20; "processing\_time": 4.2

}
```

### 文本提取示例



1.  提交文本提取任务：



```
curl -X POST "http://localhost:8001/extract-text" -H "accept: application/json" -H "Content-Type: multipart/form-data" -F "file=@report.pdf;type=application/pdf" -F "extract\_tables=true"
```



1.  查询提取结果（使用返回的 task\_id）：



```
curl "http://localhost:8001/extract-result?task\_id=def789012"
```

## 注意事项



1.  模型首次加载可能需要较长时间，请耐心等待服务初始化完成

2.  处理大型文档或高分辨率图片时，建议使用异步接口并通过任务 ID 查询结果

3.  确保 LibreOffice 服务正确安装并在系统 PATH 中，否则 Office 文档处理会失败

4.  对于 GPU 加速，需确保已安装正确版本的 CUDA 和 cuDNN

5.  生产环境中应配置适当的认证和授权机制，保护 API 访问安全

6.  调整 Redis 和 MinIO 的配置以适应实际的性能和安全需求

## 性能优化建议



1.  对于高并发场景，可增加任务消费者实例数量

2.  大型模型建议部署在具有足够 VRAM 的 GPU 上（至少 16GB）

3.  考虑使用模型量化技术减少内存占用并提高推理速度

4.  对频繁访问的结果进行缓存，减少重复处理

5.  调整 MinIO 存储策略，对不同类型的文件设置合理的生命周期管理

## 维护与更新



*   定期更新依赖包以获取安全补丁和性能改进

*   监控系统资源使用情况，及时调整配置

*   关注 Qwen2.5-VL 模型的更新，适时升级以获得更好的性能

## 维护者



*   Joe Guo ([cs-joeguo](https://github.com/cs-joeguo))

如有任何问题或建议，请提交 Issue 或联系维护者。

> （注：文档部分内容可能由 AI 生成）