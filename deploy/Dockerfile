# Sentinel Learner Server Deployment
# 服务端部署Dockerfile

FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    # 视频处理依赖
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # 工具
    ffmpeg \
    git \
    curl \
    # 清理
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制Python依赖
COPY src/python/business_learner/requirements.txt .
COPY src/python/llm/requirements.txt ./llm-requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r llm-requirements.txt

# 复制应用代码
COPY src/python/business_learner/ ./business_learner/
COPY src/python/llm/ ./llm/
COPY src/python/memory/ ./memory/

# 创建必要的目录
RUN mkdir -p /app/data/tasks /app/data/output /app/logs /app/config

# 复制配置文件
COPY config/ ./config/
COPY deploy/server_config.py ./business_learner/config/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV SENTINEL_LEARNER_MODE=server
ENV SENTINEL_LEARNER_HOST=0.0.0.0
ENV SENTINEL_LEARNER_PORT=8000
ENV TASK_STORAGE_PATH=/app/data/tasks
ENV OUTPUT_PATH=/app/data/output

# 暴露API端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "-m", "business_learner.server"]
