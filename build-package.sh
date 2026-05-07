#!/bin/bash
# Sentinel Learner Server 安装包构建脚本

set -e

# 版本号
VERSION="2.0.0"
PACKAGE_NAME="sentinel-learner-server-${VERSION}"
BUILD_DIR="./build/${PACKAGE_NAME}"

echo "======================================"
echo "Building Sentinel Learner Server Package"
echo "Version: ${VERSION}"
echo "======================================"

# 清理旧构建
rm -rf ./build
mkdir -p ${BUILD_DIR}

# 复制核心文件
echo "[1/6] Copying core files..."
cp -r src ${BUILD_DIR}/
cp -r config ${BUILD_DIR}/
cp -r deploy ${BUILD_DIR}/
cp README.md ${BUILD_DIR}/
cp package.json ${BUILD_DIR}/

# 创建必要的子目录
mkdir -p ${BUILD_DIR}/data/{tasks,output,logs}
mkdir -p ${BUILD_DIR}/config

# 创建示例配置文件
echo "[2/6] Creating example configs..."
cat > ${BUILD_DIR}/.env.example << 'EOF'
# Sentinel Learner Server 环境配置

# 运行模式
SENTINEL_LEARNER_MODE=server
SENTINEL_LEARNER_HOST=0.0.0.0
SENTINEL_LEARNER_PORT=8000

# 路径配置（根据实际环境修改）
TASK_STORAGE_PATH=/data/sentinel-learner/tasks
OUTPUT_PATH=/data/sentinel-learner/output
OPENCLAW_MEMORY_PATH=/shared/openclaw/openclaw-memory-skill

# LLM配置（必填）
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.moonshot.cn/v1

# 任务配置
MAX_CONCURRENT_TASKS=4
TASK_TIMEOUT_SECONDS=300
EOF

# 创建快速启动脚本
echo "[3/6] Creating quick start scripts..."
cat > ${BUILD_DIR}/quick-start.sh << 'EOF'
#!/bin/bash
# 快速启动脚本

echo "Sentinel Learner Server - 快速启动"
echo "===================================="

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装"
    echo "请先安装Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装"
    echo "请先安装Docker Compose"
    exit 1
fi

# 检查环境变量
if [ ! -f .env ]; then
    echo "创建环境配置文件..."
    cp .env.example .env
    echo "请编辑 .env 文件，配置必要的参数（特别是LLM_API_KEY）"
    exit 1
fi

# 启动服务
echo "启动服务..."
docker-compose -f deploy/docker-compose.yml up -d

echo ""
echo "===================================="
echo "服务已启动！"
echo "API地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo ""
echo "查看日志: docker-compose -f deploy/docker-compose.yml logs -f"
echo "停止服务: docker-compose -f deploy/docker-compose.yml down"
echo "===================================="
EOF

chmod +x ${BUILD_DIR}/quick-start.sh

# 创建Windows启动脚本
cat > ${BUILD_DIR}/quick-start.bat << 'EOF'
@echo off
chcp 65001 >nul
echo Sentinel Learner Server - 快速启动
echo ====================================

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装
    echo 请先安装Docker: https://docs.docker.com/get-docker/
    pause
    exit /b 1
)

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker Compose未安装
    pause
    exit /b 1
)

REM 检查环境变量
if not exist .env (
    echo 创建环境配置文件...
    copy .env.example .env
    echo 请编辑 .env 文件，配置必要的参数（特别是LLM_API_KEY）
    pause
    exit /b 1
)

REM 启动服务
echo 启动服务...
docker-compose -f deploy/docker-compose.yml up -d

echo.
echo ====================================
echo 服务已启动！
echo API地址: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.
echo 查看日志: docker-compose -f deploy/docker-compose.yml logs -f
echo 停止服务: docker-compose -f deploy/docker-compose.yml down
echo ====================================
pause
EOF

# 创建API测试脚本
cat > ${BUILD_DIR}/test-api.sh << 'EOF'
#!/bin/bash
# API测试脚本

API_BASE="http://localhost:8000"

echo "测试 Sentinel Learner API"
echo "=========================="

# 健康检查
echo "1. 健康检查..."
curl -s ${API_BASE}/health | jq .

# 系统信息
echo -e "\n2. 系统信息..."
curl -s ${API_BASE}/api/v1/info | jq .

# 列出任务
echo -e "\n3. 任务列表..."
curl -s ${API_BASE}/api/v1/tasks?limit=5 | jq .

echo -e "\n测试完成！"
EOF

chmod +x ${BUILD_DIR}/test-api.sh

# 创建Python客户端示例
cat > ${BUILD_DIR}/examples/python_client.py << 'EOF'
"""
Sentinel Learner Python Client
"""

import requests
import json
from pathlib import Path


class SentinelLearnerClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def health_check(self):
        """健康检查"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def get_info(self):
        """获取系统信息"""
        response = requests.get(f"{self.base_url}/api/v1/info")
        return response.json()
    
    def submit_task(self, task_id: str, use_llm_vision=True):
        """提交学习任务"""
        data = {
            "task_id": task_id,
            "use_llm_vision": use_llm_vision,
            "create_long_screenshots": True
        }
        response = requests.post(
            f"{self.base_url}/api/v1/tasks",
            json=data
        )
        return response.json()
    
    def upload_task(self, task_path: Path, task_id: str):
        """上传任务数据"""
        with open(task_path, 'rb') as f:
            files = {'task_file': f}
            data = {'task_id': task_id, 'use_llm_vision': 'true'}
            response = requests.post(
                f"{self.base_url}/api/v1/tasks/upload",
                files=files,
                data=data
            )
        return response.json()
    
    def get_task_status(self, task_id: str):
        """获取任务状态"""
        response = requests.get(f"{self.base_url}/api/v1/tasks/{task_id}")
        return response.json()
    
    def list_tasks(self, status=None, limit=100):
        """列出任务"""
        params = {'limit': limit}
        if status:
            params['status'] = status
        response = requests.get(f"{self.base_url}/api/v1/tasks", params=params)
        return response.json()
    
    def get_result(self, task_id: str, output_path: Path):
        """获取任务结果"""
        response = requests.get(f"{self.base_url}/api/v1/tasks/{task_id}/result")
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        return False


# 使用示例
if __name__ == "__main__":
    client = SentinelLearnerClient()
    
    # 健康检查
    print("Health:", client.health_check())
    
    # 系统信息
    print("Info:", client.get_info())
    
    # 提交任务
    # result = client.submit_task("task_12345")
    # print("Task submitted:", result)
EOF

mkdir -p ${BUILD_DIR}/examples

# 创建Node.js客户端示例
cat > ${BUILD_DIR}/examples/node_client.js << 'EOF'
/**
 * Sentinel Learner Node.js Client
 */

const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

class SentinelLearnerClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    async healthCheck() {
        const response = await axios.get(`${this.baseUrl}/health`);
        return response.data;
    }

    async getInfo() {
        const response = await axios.get(`${this.baseUrl}/api/v1/info`);
        return response.data;
    }

    async submitTask(taskId, useLlmVision = true) {
        const response = await axios.post(`${this.baseUrl}/api/v1/tasks`, {
            task_id: taskId,
            use_llm_vision: useLlmVision,
            create_long_screenshots: true
        });
        return response.data;
    }

    async uploadTask(taskPath, taskId) {
        const form = new FormData();
        form.append('task_file', fs.createReadStream(taskPath));
        form.append('task_id', taskId);
        form.append('use_llm_vision', 'true');

        const response = await axios.post(
            `${this.baseUrl}/api/v1/tasks/upload`,
            form,
            { headers: form.getHeaders() }
        );
        return response.data;
    }

    async getTaskStatus(taskId) {
        const response = await axios.get(`${this.baseUrl}/api/v1/tasks/${taskId}`);
        return response.data;
    }

    async listTasks(status = null, limit = 100) {
        const params = { limit };
        if (status) params.status = status;
        const response = await axios.get(`${this.baseUrl}/api/v1/tasks`, { params });
        return response.data;
    }
}

module.exports = SentinelLearnerClient;

// 使用示例
async function example() {
    const client = new SentinelLearnerClient();
    
    console.log('Health:', await client.healthCheck());
    console.log('Info:', await client.getInfo());
}

// example();
EOF

# 创建Postman集合
cat > ${BUILD_DIR}/examples/postman_collection.json << 'EOF'
{
  "info": {
    "name": "Sentinel Learner API",
    "description": "Sentinel Learner Server API Collection",
    "version": "2.0.0",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{base_url}}/health",
          "host": ["{{base_url}}"],
          "path": ["health"]
        }
      }
    },
    {
      "name": "Get System Info",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{base_url}}/api/v1/info",
          "host": ["{{base_url}}"],
          "path": ["api", "v1", "info"]
        }
      }
    },
    {
      "name": "Submit Task",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"task_id\": \"task_12345\",\n  \"task_name\": \"示例任务\",\n  \"description\": \"学习某网站功能\",\n  \"use_llm_vision\": true,\n  \"create_long_screenshots\": true\n}"
        },
        "url": {
          "raw": "{{base_url}}/api/v1/tasks",
          "host": ["{{base_url}}"],
          "path": ["api", "v1", "tasks"]
        }
      }
    },
    {
      "name": "Get Task Status",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{base_url}}/api/v1/tasks/{{task_id}}",
          "host": ["{{base_url}}"],
          "path": ["api", "v1", "tasks", "{{task_id}}"]
        }
      }
    },
    {
      "name": "List Tasks",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{base_url}}/api/v1/tasks?status=completed&limit=10",
          "host": ["{{base_url}}"],
          "path": ["api", "v1", "tasks"],
          "query": [
            {
              "key": "status",
              "value": "completed"
            },
            {
              "key": "limit",
              "value": "10"
            }
          ]
        }
      }
    }
  ],
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000"
    },
    {
      "key": "task_id",
      "value": "task_12345"
    }
  ]
}
EOF

echo "[4/6] Creating deployment scripts..."

# 创建生产环境部署脚本
cat > ${BUILD_DIR}/deploy/production-deploy.sh << 'EOF'
#!/bin/bash
# 生产环境部署脚本

set -e

INSTALL_DIR="/opt/sentinel-learner"
DATA_DIR="/data/sentinel-learner"

echo "生产环境部署"
echo "============"

# 创建目录
sudo mkdir -p $INSTALL_DIR $DATA_DIR/{tasks,output,logs}

# 复制文件
sudo cp -r ../* $INSTALL_DIR/

# 运行安装脚本
cd $INSTALL_DIR
sudo ./deploy/install.sh

echo "部署完成！"
echo "访问 http://your-server-ip:8000/docs 查看API文档"
EOF

chmod +x ${BUILD_DIR}/deploy/production-deploy.sh
mkdir -p ${BUILD_DIR}/deploy

# 创建docker-compose生产配置
cat > ${BUILD_DIR}/deploy/docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  sentinel-learner:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    image: sentinel-learner:${VERSION:-latest}
    container_name: sentinel-learner
    restart: always
    ports:
      - "${SENTINEL_LEARNER_PORT:-8000}:8000"
    environment:
      - SENTINEL_LEARNER_MODE=server
      - SENTINEL_LEARNER_HOST=0.0.0.0
      - SENTINEL_LEARNER_PORT=8000
      - OPENCLAW_MEMORY_PATH=/shared/openclaw-memory-skill
      - TASK_STORAGE_PATH=/app/data/tasks
      - OUTPUT_PATH=/app/data/output
      - REDIS_URL=redis://redis:6379/0
      - MAX_CONCURRENT_TASKS=${MAX_CONCURRENT_TASKS:-4}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL:-https://api.moonshot.cn/v1}
    volumes:
      - ${OPENCLAW_MEMORY_PATH:-/shared/openclaw}:/shared/openclaw:rw
      - ${TASK_STORAGE_PATH:-./data/tasks}:/app/data/tasks:rw
      - ${OUTPUT_PATH:-./data/output}:/app/data/output:rw
      - ./logs:/app/logs:rw
    depends_on:
      - redis
    networks:
      - sentinel-network
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G

  redis:
    image: redis:7-alpine
    container_name: sentinel-redis
    restart: always
    volumes:
      - redis-data:/data
    networks:
      - sentinel-network
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru

volumes:
  redis-data:

networks:
  sentinel-network:
    driver: bridge
EOF

echo "[5/6] Creating documentation..."

# 创建CHANGELOG
cat > ${BUILD_DIR}/CHANGELOG.md << 'EOF'
# Changelog

## [2.0.0] - 2026-05-07

### 新增
- 服务端API部署支持
- Docker容器化部署
- 任务队列管理（Redis）
- RESTful API接口
- Python/Node.js客户端SDK
- 生产环境部署脚本

### 改进
- 统一Memory适配器支持服务端模式
- 并发任务处理优化
- 健康检查和监控接口

### 修复
- 视频分析内存泄漏问题
- 长图拼接重叠检测
EOF

# 创建LICENSE
cat > ${BUILD_DIR}/LICENSE << 'EOF'
MIT License

Copyright (c) 2026 Sentinel Learner Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

echo "[6/6] Packaging..."

# 创建tar.gz包
cd build
tar -czf ${PACKAGE_NAME}.tar.gz ${PACKAGE_NAME}

# 创建zip包（Windows用户）
zip -r ${PACKAGE_NAME}.zip ${PACKAGE_NAME}

echo ""
echo "======================================"
echo "Build Complete!"
echo "======================================"
echo ""
echo "安装包已生成:"
echo "  - build/${PACKAGE_NAME}.tar.gz (Linux/Mac)"
echo "  - build/${PACKAGE_NAME}.zip (Windows)"
echo ""
echo "安装步骤:"
echo "  1. 解压安装包"
echo "  2. 编辑 .env 文件配置参数"
echo "  3. 运行 ./quick-start.sh 启动服务"
echo ""
echo "API文档: http://localhost:8000/docs"
echo "======================================"
