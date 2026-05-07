# Sentinel Learner 服务端部署方案

## 架构概述

```
┌─────────────────────────────────────────────────────────────────┐
│                     服务端部署架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌──────────────────┐     ┌──────────────┐ │
│  │   Client    │────►│  Sentinel Learner │────►│   Redis      │ │
│  │  (上传Task) │     │   (API Server)    │     │  (任务队列)   │ │
│  └─────────────┘     └────────┬─────────┘     └──────────────┘ │
│                               │                                 │
│                               ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Business Learning Engine                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │  │
│  │  │ 视频分析  │  │ API提取  │  │ DOM解析  │  │ LLM理解  │ │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │  │
│  │       └──────────────┴─────────────┴─────────────┘       │  │
│  │                          ▼                               │  │
│  │              ┌────────────────────┐                      │  │
│  │              │    数据融合引擎     │                      │  │
│  │              └─────────┬──────────┘                      │  │
│  │                        ▼                                 │  │
│  │              ┌────────────────────┐                      │  │
│  │              │  统一Memory适配器   │◄────────────────────┐│  │
│  │              └────────────────────┘                     ││  │
│  └─────────────────────────────────────────────────────────┼──┘  │
│                                                            │     │
│  ┌─────────────────────────────────────────────────────────┼──┐  │
│  │           OpenClaw Memory Skill (共享存储)               │  │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │  │
│  │  │  /shared/openclaw/memory/ontology/               │  │  │  │
│  │  │    ├── graph.jsonl  (知识图谱)                   │◄─┘  │  │
│  │  │    ├── schema.yaml  (本体定义)                   │     │  │
│  │  │    └── config.json  (配置)                       │     │  │
│  │  └──────────────────────────────────────────────────┘     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 快速安装

### 方式一：使用安装脚本（推荐）

```bash
# 1. 下载安装包
wget https://github.com/sentinel-learner/releases/download/v2.0.0/sentinel-learner-server.tar.gz
tar -xzf sentinel-learner-server.tar.gz
cd sentinel-learner-server

# 2. 运行安装脚本
sudo ./install.sh

# 3. 配置环境变量（可选）
export LLM_API_KEY="your-api-key"
export SHARED_MEMORY_PATH="/shared/openclaw"

# 4. 启动服务
sudo sentinel-learner start
```

### 方式二：使用Docker Compose

```bash
# 1. 克隆仓库
git clone https://github.com/sentinel-learner.git
cd sentinel-learner/deploy

# 2. 配置环境
cp .env.example .env
# 编辑 .env 文件，设置必要的配置

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

## API接口文档

### 1. 健康检查
```bash
GET /health
```

### 2. 提交学习任务
```bash
POST /api/v1/tasks
Content-Type: application/json

{
  "task_id": "task_12345",
  "task_name": "示例任务",
  "description": "学习某网站功能",
  "use_llm_vision": true,
  "create_long_screenshots": true
}
```

### 3. 上传任务数据
```bash
POST /api/v1/tasks/upload
Content-Type: multipart/form-data

task_file: [task_zip_file]
task_id: "task_12345"
use_llm_vision: true
```

### 4. 查询任务状态
```bash
GET /api/v1/tasks/{task_id}
```

### 5. 获取任务结果
```bash
GET /api/v1/tasks/{task_id}/result
```

### 6. 列出所有任务
```bash
GET /api/v1/tasks?status=completed&limit=10&offset=0
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SENTINEL_LEARNER_MODE` | 运行模式 | `server` |
| `SENTINEL_LEARNER_HOST` | 监听地址 | `0.0.0.0` |
| `SENTINEL_LEARNER_PORT` | 监听端口 | `8000` |
| `OPENCLAW_MEMORY_PATH` | OpenClaw Memory路径 | `/shared/openclaw-memory-skill` |
| `TASK_STORAGE_PATH` | Task数据存储路径 | `/app/data/tasks` |
| `OUTPUT_PATH` | 输出目录 | `/app/data/output` |
| `LLM_API_KEY` | LLM API密钥 | - |
| `LLM_BASE_URL` | LLM API地址 | `https://api.moonshot.cn/v1` |
| `MAX_CONCURRENT_TASKS` | 最大并发任务数 | `4` |
| `TASK_TIMEOUT_SECONDS` | 任务超时时间 | `300` |

### 目录结构

```
/opt/sentinel-learner/          # 安装目录
├── docker-compose.yml          # Docker编排配置
├── Dockerfile                  # Docker镜像定义
├── server.py                   # API服务主程序
├── install.sh                  # 安装脚本
├── .env                        # 环境变量配置
├── src/                        # 源代码
│   └── python/
│       └── business_learner/   # 业务学习模块
├── config/                     # 配置文件
└── data/                       # 数据目录（挂载卷）
    ├── tasks/                  # Task数据
    ├── output/                 # 输出结果
    └── logs/                   # 日志文件
```

## 与OpenClaw集成

### 1. 共享Memory配置

确保OpenClaw Memory Skill已部署在共享路径：

```bash
/shared/openclaw/
└── openclaw-memory-skill/
    ├── memory/
    │   └── ontology/
    │       ├── graph.jsonl     # 知识图谱数据
    │       ├── schema.yaml     # 本体定义
    │       └── config.json     # 配置文件
    └── scripts/
        └── ontology_optimized.py
```

### 2. 权限设置

```bash
# 设置共享目录权限
sudo chown -R 1000:1000 /shared/openclaw
sudo chmod -R 775 /shared/openclaw
```

### 3. 验证连接

```bash
# 检查Memory连接
curl http://localhost:8000/api/v1/info
```

## 管理命令

```bash
# 启动服务
sudo sentinel-learner start

# 停止服务
sudo sentinel-learner stop

# 重启服务
sudo sentinel-learner restart

# 查看状态
sudo sentinel-learner status

# 查看日志
sudo sentinel-learner logs

# 进入容器
sudo sentinel-learner shell

# 更新版本
sudo sentinel-learner update
```

## 系统服务

```bash
# 使用systemctl管理
sudo systemctl start sentinel-learner
sudo systemctl stop sentinel-learner
sudo systemctl restart sentinel-learner
sudo systemctl status sentinel-learner

# 设置开机自启
sudo systemctl enable sentinel-learner
```

## 监控与日志

### 查看服务日志
```bash
# 实时日志
docker-compose logs -f sentinel-learner

# 最近100行
docker-compose logs --tail=100 sentinel-learner
```

### 健康检查
```bash
# API健康检查
curl http://localhost:8000/health

# 系统信息
curl http://localhost:8000/api/v1/info
```

## 故障排查

### 1. 服务无法启动
```bash
# 检查Docker状态
sudo systemctl status docker

# 检查端口占用
sudo netstat -tulpn | grep 8000

# 查看详细日志
sudo journalctl -u sentinel-learner -f
```

### 2. Memory连接失败
```bash
# 检查Memory路径
ls -la /shared/openclaw/openclaw-memory-skill

# 检查权限
sudo chown -R 1000:1000 /shared/openclaw
```

### 3. 任务处理失败
```bash
# 查看任务日志
curl http://localhost:8000/api/v1/tasks/{task_id}

# 查看容器日志
docker-compose logs sentinel-learner | grep ERROR
```

## 性能优化

### 1. 调整并发数
编辑 `.env` 文件：
```bash
MAX_CONCURRENT_TASKS=8
```

### 2. 增加内存限制
编辑 `docker-compose.yml`：
```yaml
services:
  sentinel-learner:
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G
```

### 3. 使用GPU加速（可选）
```yaml
services:
  sentinel-learner:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 安全建议

1. **API密钥保护**：使用环境变量或Docker Secrets管理LLM API密钥
2. **网络隔离**：使用Docker网络隔离，避免直接暴露端口
3. **定期备份**：定期备份 `/shared/openclaw` 和任务数据
4. **日志审计**：启用访问日志，定期审计

## 更新升级

```bash
# 1. 备份数据
cp -r /data/sentinel-learner /data/sentinel-learner-backup

# 2. 拉取新版本
cd /opt/sentinel-learner
git pull origin main

# 3. 重新构建
docker-compose build --no-cache

# 4. 重启服务
docker-compose up -d
```

## 技术支持

- 文档：https://docs.sentinel-learner.com
- 问题反馈：https://github.com/sentinel-learner/issues
- 邮箱：support@sentinel-learner.com
