#!/bin/bash
###
 # @Descripttion: 启动项目（API服务 + 图片描述消费者 + 文本提取消费者 + 复合任务消费者）
 # @Author: Joe Guo
 # @version: 1.2
 # @Date: 2025-07-30
### 

# 定义项目目录、Conda环境名称和日志文件路径（请根据实际情况修改）
PROJECT_DIR="/var/www/test/MinerUVision"  # 项目根目录（包含main.py的目录）
CONDA_ENV="mineru"       # Conda环境名称
API_LOG_FILE="$PROJECT_DIR/logs/api.log"              # API服务日志
IMAGE_CONSUMER_LOG="$PROJECT_DIR/logs/image_consumer.log"  # 图片描述消费者日志
TEXT_CONSUMER_LOG="$PROJECT_DIR/logs/text_consumer.log"    # 文本提取消费者日志
COMBINED_CONSUMER_LOG="$PROJECT_DIR/logs/combined_consumer.log"  # 复合任务消费者日志

# 创建日志目录（如果不存在）
mkdir -p "$PROJECT_DIR/logs"

# 检查项目目录是否存在
if [ ! -d "$PROJECT_DIR" ]; then
  echo "错误：项目目录 $PROJECT_DIR 不存在！"
  exit 1
fi

# 导航到项目目录
cd "$PROJECT_DIR" || {
  echo "错误：无法进入项目目录 $PROJECT_DIR！"
  exit 1
}

# 激活Conda环境（兼容不同的Conda安装路径）
CONDA_SH_PATH="/root/miniconda3/etc/profile.d/conda.sh"  # conda.sh路径
if [ ! -f "$CONDA_SH_PATH" ]; then
  # 尝试其他常见的Conda安装路径
  CONDA_SH_PATH="$HOME/anaconda3/etc/profile.d/conda.sh"
  if [ ! -f "$CONDA_SH_PATH" ]; then
    echo "错误：Conda配置文件不存在，请检查路径！"
    exit 1
  fi
fi
. "$CONDA_SH_PATH"
conda activate "$CONDA_ENV" || {
  echo "错误：无法激活Conda环境 $CONDA_ENV！"
  exit 1
}

# 函数：停止进程
stop_process() {
  local process_name=$1
  local existing_pid=$(pgrep -f "$process_name")
  if [ -n "$existing_pid" ]; then
    echo "发现已存在的$process_name进程 $existing_pid，正在停止..."
    kill "$existing_pid" || {
      echo "警告：停止进程 $existing_pid 失败，尝试强制停止..."
      kill -9 "$existing_pid"
    }
    sleep 2  # 等待进程停止
  fi
}

# 停止已存在的服务和消费者进程
stop_process "python main.py"
stop_process "python -m tasks.image_task_consumer"
stop_process "python -m tasks.task_consumer"  # 新增：停止文本提取消费者
stop_process "python -m tasks.combined_task_consumer"  # 新增：停止复合任务消费者

# 检查核心脚本是否存在
if [ ! -f "main.py" ]; then
  echo "错误：API服务脚本 main.py 不存在！"
  exit 1
fi
if [ ! -f "tasks/image_task_consumer.py" ]; then
  echo "错误：图片描述消费者脚本 tasks/image_task_consumer.py 不存在！"
  exit 1
fi
if [ ! -f "tasks/task_consumer.py" ]; then  # 新增：检查文本提取消费者
  echo "错误：文本提取消费者脚本 tasks/task_consumer.py 不存在！"
  exit 1
fi
if [ ! -f "tasks/combined_task_consumer.py" ]; then  # 新增：检查复合任务消费者
  echo "错误：复合任务消费者脚本 tasks/combined_task_consumer.py 不存在！"
  exit 1
fi

# 启动API服务（后台运行并记录日志）
echo "启动API服务..."
nohup python main.py > "$API_LOG_FILE" 2>&1 &
API_PID=$!

# 启动图片描述任务消费者
echo "启动图片描述任务消费者..."
nohup python -m tasks.image_task_consumer > "$IMAGE_CONSUMER_LOG" 2>&1 &
IMAGE_CONSUMER_PID=$!

# 新增：启动文本提取任务消费者
echo "启动文本提取任务消费者..."
nohup python -m tasks.task_consumer > "$TEXT_CONSUMER_LOG" 2>&1 &
TEXT_CONSUMER_PID=$!

# 新增：启动复合任务消费者
echo "启动复合任务消费者..."
nohup python -m tasks.combined_task_consumer > "$COMBINED_CONSUMER_LOG" 2>&1 &
COMBINED_CONSUMER_PID=$!

# 输出进程信息
echo "API服务已启动，进程ID：$API_PID，日志路径：$API_LOG_FILE"
echo "图片描述消费者已启动，进程ID：$IMAGE_CONSUMER_PID，日志路径：$IMAGE_CONSUMER_LOG"
echo "文本提取消费者已启动，进程ID：$TEXT_CONSUMER_PID，日志路径：$TEXT_CONSUMER_LOG"
echo "复合任务消费者已启动，进程ID：$COMBINED_CONSUMER_PID，日志路径：$COMBINED_CONSUMER_LOG"

# 简单验证启动状态
sleep 2
echo "启动验证："
if ps -p "$API_PID" > /dev/null; then
  echo "API服务启动成功"
else
  echo "API服务启动失败，请查看日志：$API_LOG_FILE"
fi

if ps -p "$IMAGE_CONSUMER_PID" > /dev/null; then
  echo "图片描述消费者启动成功"
else
  echo "图片描述消费者启动失败，请查看日志：$IMAGE_CONSUMER_LOG"
fi

# 新增：验证文本提取消费者启动状态
if ps -p "$TEXT_CONSUMER_PID" > /dev/null; then
  echo "文本提取消费者启动成功"
else
  echo "文本提取消费者启动失败，请查看日志：$TEXT_CONSUMER_LOG"
fi

# 新增：验证复合任务消费者启动状态
if ps -p "$COMBINED_CONSUMER_PID" > /dev/null; then
  echo "复合任务消费者启动成功"
else
  echo "复合任务消费者启动失败，请查看日志：$COMBINED_CONSUMER_LOG"
fi