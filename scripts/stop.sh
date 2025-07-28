#!/bin/bash
###
 # @Descripttion: 停止项目所有服务（API + 消费者）
 # @Author: Your Name
###

# 函数：停止指定进程
stop_process() {
  local process_name=$1
  local existing_pid=$(pgrep -f "$process_name")
  if [ -n "$existing_pid" ]; then
    echo "停止进程 $existing_pid（$process_name）..."
    kill "$existing_pid" || {
      echo "强制停止进程 $existing_pid..."
      kill -9 "$existing_pid"
    }
    sleep 2
  else
    echo "未找到进程：$process_name"
  fi
}

# 停止所有服务进程
stop_process "python main.py"
stop_process "python -m tasks.image_task_consumer"
stop_process "python -m tasks.task_consumer"

echo "所有服务已停止"