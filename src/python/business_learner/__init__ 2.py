"""
Business Learner - 业务学习系统

从sentinel-browser记录的task数据中学习业务功能
"""

__version__ = "1.0.0"

from .core.engine import BusinessLearningEngine
from .utils.models import TaskUnderstanding, PageUnderstanding

__all__ = [
    "BusinessLearningEngine",
    "TaskUnderstanding",
    "PageUnderstanding"
]
