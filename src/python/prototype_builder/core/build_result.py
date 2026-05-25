"""
构建结果数据模型
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from pathlib import Path


class BuildQuality(Enum):
    """构建质量等级"""
    EXCELLENT = "excellent"    # ≥ 95%
    GOOD = "good"              # 85-95%
    ACCEPTABLE = "acceptable"  # 70-85%
    POOR = "poor"              # < 70%


class DataSource(Enum):
    """数据源类型"""
    DOM_SNAPSHOT = "dom_snapshot"      # DOM 快照（最精确）
    RESOURCE_FILES = "resource_files"  # 资源文件
    VIDEO_KEYFRAME = "video_keyframe"  # 视频关键帧
    FAILED = "failed"                  # 构建失败


@dataclass
class QualityMetrics:
    """质量指标"""
    ssim_score: float = 0.0            # 结构相似度
    layout_score: float = 0.0          # 布局相似度
    element_score: float = 0.0         # 元素完整性
    style_score: float = 0.0           # 样式一致性
    overall_score: float = 0.0         # 综合评分
    
    def evaluate_quality(self) -> BuildQuality:
        """评估质量等级"""
        if self.overall_score >= 0.95:
            return BuildQuality.EXCELLENT
        elif self.overall_score >= 0.85:
            return BuildQuality.GOOD
        elif self.overall_score >= 0.70:
            return BuildQuality.ACCEPTABLE
        else:
            return BuildQuality.POOR


@dataclass
class BuildResult:
    """构建结果"""
    task_id: str
    source: DataSource
    output_path: Optional[Path] = None
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    
    # 构建信息
    build_time_ms: float = 0.0
    source_files: List[str] = field(default_factory=list)
    
    # 降级信息
    downgrade_from: Optional[DataSource] = None
    downgrade_reason: Optional[str] = None
    
    # 错误信息
    error_message: Optional[str] = None
    
    def is_success(self) -> bool:
        """是否构建成功"""
        return self.output_path is not None and self.output_path.exists()
    
    def meets_target(self, target_score: float = 0.95) -> bool:
        """是否达到目标分数"""
        return self.quality.overall_score >= target_score
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'source': self.source.value,
            'output_path': str(self.output_path) if self.output_path else None,
            'quality': {
                'ssim': self.quality.ssim_score,
                'layout': self.quality.layout_score,
                'element': self.quality.element_score,
                'style': self.quality.style_score,
                'overall': self.quality.overall_score,
                'level': self.quality.evaluate_quality().value
            },
            'build_time_ms': self.build_time_ms,
            'source_files': self.source_files,
            'downgrade_from': self.downgrade_from.value if self.downgrade_from else None,
            'downgrade_reason': self.downgrade_reason,
            'error': self.error_message,
            'success': self.is_success(),
            'meets_target': self.meets_target()
        }
