"""
查询结果数据模型
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class EvidenceType(Enum):
    """证据类型"""
    TEXT = "text"           # 文本证据（DOM、API、日志）
    IMAGE = "image"         # 图像证据（视频关键帧）
    FUSION = "fusion"       # 融合证据（多源综合）


class ConfidenceLevel(Enum):
    """置信度等级"""
    HIGH = "high"           # ≥ 0.95
    MEDIUM = "medium"       # 0.85 - 0.95
    LOW = "low"             # < 0.85


@dataclass
class Evidence:
    """证据项"""
    id: str
    type: EvidenceType
    content: str
    source: str                          # 来源：dom/api/video/etc
    task_id: str
    confidence: float
    authority_level: str                 # truth/reference/observation/manual
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        if self.confidence >= 0.95:
            self.confidence_level = ConfidenceLevel.HIGH
        elif self.confidence >= 0.85:
            self.confidence_level = ConfidenceLevel.MEDIUM
        else:
            self.confidence_level = ConfidenceLevel.LOW


@dataclass
class QueryResult:
    """查询结果"""
    query: str
    answer: str
    confidence: float
    evidences: List[Evidence]
    total_found: int
    query_time_ms: float
    
    # 详细评分
    consistency_score: float = 0.0      # 证据一致性
    coverage_score: float = 0.0         # 问题覆盖度
    authority_score: float = 0.0        # 权威等级分
    
    def __post_init__(self):
        self.confidence_level = self._calculate_confidence_level()
        
    def _calculate_confidence_level(self) -> ConfidenceLevel:
        if self.confidence >= 0.95:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.85:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def to_dict(self) -> Dict:
        return {
            'query': self.query,
            'answer': self.answer,
            'confidence': self.confidence,
            'confidence_level': self.confidence_level.value,
            'answerable': self.confidence >= 0.95,
            'evidences': [
                {
                    'id': e.id,
                    'type': e.type.value,
                    'content': e.content[:200] + '...' if len(e.content) > 200 else e.content,
                    'source': e.source,
                    'confidence': e.confidence,
                    'authority_level': e.authority_level
                }
                for e in self.evidences[:5]  # 只返回前5个证据
            ],
            'total_found': self.total_found,
            'query_time_ms': self.query_time_ms,
            'breakdown': {
                'consistency': self.consistency_score,
                'coverage': self.coverage_score,
                'authority': self.authority_score
            }
        }
