# Business Learner 部署文档

## 架构概述

```
┌─────────────────────────────────────────────────────────────┐
│                    服务器部署架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Nginx      │    │   FastAPI    │    │  Redis       │  │
│  │   (反向代理)  │◄──►│   (API服务)  │◄──►│  (任务队列)   │  │
│  └──────────────┘    └──────┬───────┘    └──────────────┘  │
│                             │                               │
│                             ▼                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Business Learning Engine                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │  │
│  │  │ 视频分析  │ │ API提取  │ │ DOM解析  │             │  │
│  │  └──────────┘ └──────────┘ └──────────┘             │  │
│  │           ↓              ↓              ↓            │  │
│  │           └──────────────┬──────────────┘            │  │
│  │                          ▼                          │  │
│  │              ┌──────────────────┐                   │  │
│  │              │   数据融合引擎    │                   │  │
│  │              └────────┬─────────┘                   │  │
│  │                       ▼                             │  │
│  │              ┌──────────────────┐                   │  │
│  │              │  统一Memory适配器 │◄─────────────────┐│  │
│  │              └──────────────────┘                  ││  │
│  └────────────────────────────────────────────────────┼──┘  │
│                                                       │     │
│  ┌────────────────────────────────────────────────────┼──┐  │
│  │           OpenClaw Memory Skill (共享)              │  │  │
│  │  ┌──────────────────────────────────────────────┐  │  │  │
│  │  │  /shared/openclaw/memory/ontology/           │  │  │  │
│  │  │    ├── graph.jsonl  (知识图谱)               │◄─┘  │  │
│  │  │    ├── schema.yaml  (Schema定义)             │     │  │
│  │  │    └── config.json  (配置文件)               │     │  │
│  │  └──────────────────────────────────────────────┘     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 部署步骤

### 1. 环境准备

```bash
# 安装Python依赖
pip install -r requirements.txt

# 主要依赖
# - opencv-python (视频处理)
# - scikit-image (图像相似度)
# - pyyaml (Schema解析)
# - fastapi (API服务)
# - redis (任务队列)
```

### 2. 配置OpenClaw Memory Skill

```bash
# 在服务器上部署openclaw-memory-skill
# 确保所有服务共享同一个memory目录

# 创建共享目录
mkdir -p /shared/openclaw

# 复制openclaw-memory-skill到共享目录
cp -r /path/to/openclaw-memory-skill /shared/openclaw/

# 设置权限
chmod -R 775 /shared/openclaw
chown -R www-data:www-data /shared/openclaw
```

### 3. 环境变量配置

```bash
# 创建 .env 文件

# 运行模式
BUSINESS_LEARNER_MODE=server
BUSINESS_LEARNER_ENV=production

# 服务器配置
BUSINESS_LEARNER_HOST=0.0.0.0
BUSINESS_LEARNER_PORT=8000

# 共享Memory路径（关键配置）
OPENCLAW_MEMORY_PATH=/shared/openclaw/openclaw-memory-skill

# Task数据存储路径
TASK_STORAGE_PATH=/data/tasks

# 处理配置
MAX_CONCURRENT_TASKS=4
TASK_TIMEOUT_SECONDS=300

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 日志配置
LOG_LEVEL=INFO
LOG_PATH=/var/log/business-learner
```

### 4. 启动服务

```bash
# 开发模式（本地）
python -m business_learner.cli /path/to/task

# 服务器模式
export BUSINESS_LEARNER_MODE=server
export OPENCLAW_MEMORY_PATH=/shared/openclaw/openclaw-memory-skill
python -m business_learner.server
```

## 多Task知识冲突解决

### 冲突检测策略

```python
# 1. URL冲突检测
同一系统的多个Task发现相同URL的页面
→ 比较时间戳，保留最新的

# 2. 实体冲突检测
不同Task对同一业务实体的描述不同
→ 按权威等级解决（truth > reference > observation > manual）

# 3. 功能冲突检测
不同Task对同一功能的描述不同
→ 合并描述，标记差异
```

### 知识融合流程

```
新Task知识入库
    ↓
检测冲突
    ↓
┌─────────────┬─────────────┬─────────────┐
↓             ↓             ↓             ↓
无冲突       URL冲突       实体冲突      功能冲突
    ↓             ↓             ↓             ↓
直接入库    时间戳决定     权威等级决定   合并描述
```

## API接口

### 提交Task处理任务

```bash
POST /api/v1/tasks
Content-Type: multipart/form-data

Parameters:
- task_file: Task数据压缩包
- user_id: 上传用户ID
- task_name: 任务名称
- task_description: 任务描述
```

### 查询Task状态

```bash
GET /api/v1/tasks/{task_id}/status

Response:
{
  "task_id": "task_123",
  "status": "completed",
  "progress": 100,
  "result_url": "/api/v1/tasks/task_123/result"
}
```

### 获取系统知识摘要

```bash
GET /api/v1/systems/{system_name}/summary

Response:
{
  "system": "中国银河证券官网",
  "recordings_count": 5,
  "pages_count": 23,
  "entities_count": 45,
  "last_updated": "2026-05-06T10:00:00Z"
}
```

## 监控和维护

### 日志监控

```bash
# 查看处理日志
tail -f /var/log/business-learner/app.log

# 查看错误日志
tail -f /var/log/business-learner/error.log
```

### 知识图谱维护

```bash
# 清理过期知识（需要定期执行）
cd /shared/openclaw/openclaw-memory-skill
python scripts/ontology_optimized.py clean

# 压缩冗余知识
python scripts/ontology_optimized.py compress

# 验证知识图谱
python scripts/ontology_optimized.py validate
```

### 备份策略

```bash
# 定期备份知识图谱
cp /shared/openclaw/memory/ontology/graph.jsonl \
   /backup/graph_$(date +%Y%m%d).jsonl

# 备份Task数据
tar czf /backup/tasks_$(date +%Y%m%d).tar.gz /data/tasks
```

## 故障排查

### 常见问题

1. **Memory路径权限错误**
   ```bash
   # 检查权限
   ls -la /shared/openclaw/memory/ontology/
   
   # 修复权限
   chmod -R 775 /shared/openclaw
   chown -R www-data:www-data /shared/openclaw
   ```

2. **Task处理超时**
   ```bash
   # 增加超时时间
   export TASK_TIMEOUT_SECONDS=600
   ```

3. **Redis连接失败**
   ```bash
   # 检查Redis状态
   redis-cli ping
   
   # 重启Redis
   systemctl restart redis
   ```

## 性能优化

### 视频处理优化

```python
# 调整关键帧提取参数
VIDEO_CONFIG = {
    "similarity_threshold": 0.95,  # 提高阈值减少帧数
    "max_keyframes": 30,           # 限制最大帧数
    "frame_quality": 0.7           # 降低图片质量
}
```

### 并发控制

```python
# 限制并发处理数
MAX_CONCURRENT_TASKS = 4

# 使用Redis队列管理任务
```

## 安全考虑

1. **数据隔离**
   - 每个用户的Task数据存储在独立目录
   - 知识图谱按权限级别访问

2. **敏感信息过滤**
   - API响应中的密码、token自动过滤
   - DOM中的敏感输入字段标记

3. **访问控制**
   - API接口需要认证
   - 知识图谱查询权限控制
