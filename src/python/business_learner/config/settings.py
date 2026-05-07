"""
配置文件
"""

from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据路径配置
DEFAULT_TASK_PATH = "/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778034751731"

# OpenClaw Memory Skill 路径
MEMORY_SKILL_PATH = "/Users/gaoyiwei/Documents/trae_projects/openclaw/openclaw-memory-skill"

# 视频分析配置
VIDEO_CONFIG = {
    "similarity_threshold": 0.95,  # 帧相似度阈值
    "max_keyframes": 50,           # 最大关键帧数
    "frame_quality": 0.8           # 输出图片质量
}

# LLM配置
LLM_CONFIG = {
    "model": "gpt-4-vision-preview",
    "max_tokens": 2000,
    "temperature": 0.3
}

# 数据融合配置
FUSION_CONFIG = {
    "conflict_resolution": {
        "text_priority": "dom",      # 文本类优先DOM
        "visual_priority": "video",  # 视觉类优先视频
        "entity_priority": "api"     # 业务实体优先API
    },
    "confidence_threshold": 0.7
}

# 输出配置
OUTPUT_CONFIG = {
    "save_keyframes": True,
    "save_analysis": True,
    "output_format": "json"
}
