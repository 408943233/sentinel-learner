# Sentinel Learner

Sentinel Browser 录制任务的学习与分析系统。通过分析录制数据，学习目标网站的业务知识和代码，并在本地还原网站进行模拟操作验证。

## 项目架构

```
sentinel-learner/
├── src/
│   ├── python/          # Python 模块 - AI处理核心
│   │   ├── knowledge_extractor/   # 知识提取
│   │   ├── similarity_evaluator/  # 相似度评估
│   │   └── llm/                   # 大模型接口
│   ├── node/            # Node.js 模块 - Web服务
│   │   ├── mock-server/           # 模拟服务器
│   │   ├── page-reconstructor/    # 页面还原
│   │   └── action-simulator/      # 操作模拟
│   └── shared/          # 共享类型定义和工具
├── tests/               # 测试用例
├── examples/            # 示例任务
├── config/              # 配置文件
└── docs/                # 文档
```

## 学习阶段

### 阶段1: 知识提取
- 解析 training_manifest.jsonl
- 分析 DOM 结构和变化
- 提取页面状态和业务逻辑
- 理解用户操作序列

### 阶段2: 本地还原
- 基于 network 资源重建静态页面
- 模拟 API 请求和响应
- 重建页面路由和导航
- 在本地启动模拟服务器

### 阶段3: 操作模拟与验证
- 大模型基于学习生成操作序列
- 在本地还原的页面上执行操作
- 对比模拟操作与原始录制的相似度
- 生成学习报告

## 快速开始

```bash
# 安装依赖
npm install
pip install -r requirements.txt

# 配置 Kimi API Key
cp config/config.example.json config/config.json
# 编辑 config.json 添加你的 API Key

# 运行示例
npm run example:learn -- --task=task_11_www.chinastock.com.cn_1778034751731
```

## 配置说明

### config.json
```json
{
  "llm": {
    "provider": "kimi",
    "api_key": "YOUR_API_KEY",
    "model": "kimi-k2.5",
    "base_url": "https://api.moonshot.cn/v1"
  },
  "paths": {
    "tasks_dir": "/path/to/sentinel-browser/output/collections",
    "output_dir": "./output"
  },
  "learning": {
    "max_events_per_batch": 50,
    "similarity_threshold": 0.85
  }
}
```
