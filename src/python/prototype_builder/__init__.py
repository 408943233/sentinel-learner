"""
Prototype Builder for Sentinel Learner
产品原型构建系统
支持多源重建（DOM快照 → 资源文件 → 视频关键帧）
"""

from .core.prototype_builder import PrototypeBuilder
from .core.build_result import BuildResult, BuildQuality
from .evaluators.visual_evaluator import VisualEvaluator
from .reconstructors.dom_reconstructor import DOMReconstructor
from .reconstructors.resource_reconstructor import ResourceReconstructor

__all__ = [
    'PrototypeBuilder',
    'BuildResult',
    'BuildQuality',
    'VisualEvaluator',
    'DOMReconstructor',
    'ResourceReconstructor',
]
