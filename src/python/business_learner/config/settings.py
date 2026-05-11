"""
配置文件
"""

import os
from pathlib import Path

# 项目根目录（向上追溯到 sentinel-learner 根目录）
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# 数据路径配置（可通过环境变量覆盖）
DEFAULT_TASK_PATH = os.environ.get(
    "SENTINEL_TASK_PATH",
    str(PROJECT_ROOT / "data" / "tasks")
)

# OpenClaw Memory Skill 路径（可通过环境变量覆盖）
MEMORY_SKILL_PATH = os.environ.get(
    "OPENCLAW_MEMORY_PATH",
    str(PROJECT_ROOT.parent / "openclaw-memory-skill")
)

# Image Stitch Skill 路径（可通过环境变量覆盖）
IMAGE_STITCH_SKILL_PATH = os.environ.get(
    "IMAGE_STITCH_SKILL_PATH",
    str(PROJECT_ROOT.parent / ".trae" / "skills" / "image-stitch" / "stitch.py")
)

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
