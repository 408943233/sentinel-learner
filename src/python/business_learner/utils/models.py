"""
数据模型定义
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime


class DataSource(Enum):
    """数据源类型"""
    VIDEO = "video"
    API = "api"
    DOM = "dom"
    MANIFEST = "manifest"


class ConfidenceLevel(Enum):
    """可信度等级"""
    HIGH = "high"      # 多源一致
    MEDIUM = "medium"  # 单源可靠
    LOW = "low"        # 冲突或不确定


class ElementType(Enum):
    """DOM元素类型"""
    TEXT = "text"
    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    IMAGE = "image"
    CONTAINER = "container"
    HEADING = "heading"
    LIST = "list"
    TABLE = "table"
    FORM = "form"
    NAV = "nav"
    UNKNOWN = "unknown"


@dataclass
class VideoFrame:
    """视频帧数据"""
    timestamp: float
    frame_number: int
    image_path: str
    event_type: str
    event_data: Dict
    similarity_score: float = 1.0


@dataclass
class APIEntity:
    """API业务实体"""
    entity_type: str
    name: str
    attributes: Dict[str, Any]
    source_url: str
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH


@dataclass
class DOMElement:
    """DOM元素"""
    id: int
    tag: str
    element_type: ElementType
    attributes: Dict[str, Any] = field(default_factory=dict)
    text_content: str = ""
    xpath: str = ""
    is_interactive: bool = False


@dataclass
class PageInfo:
    """页面信息"""
    url: str
    title: str
    page_type: str
    business_domain: str = ""
    timestamp: int = 0
    text_content: str = ""
    dom_size: int = 0
    load_time: float = 0.0


@dataclass
class UserAction:
    """用户操作"""
    timestamp: float
    action_type: str
    target: str
    semantic_label: str = ""
    business_intent: str = ""


@dataclass
class BusinessProcess:
    """业务流程"""
    name: str
    description: str
    steps: List[UserAction] = field(default_factory=list)
    start_page: str = ""
    end_page: str = ""


@dataclass
class VisualElement:
    """视觉元素"""
    element_id: str
    element_type: str
    description: str
    location: Dict = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class ConflictRecord:
    """冲突记录"""
    element_id: str
    video_value: Any
    dom_value: Any
    api_value: Any
    resolved_value: Any
    resolution_strategy: str
    confidence: ConfidenceLevel


@dataclass
class PageUnderstanding:
    """页面理解结果"""
    page_info: PageInfo
    
    # 各数据源提取的信息
    visual_elements: List[Dict] = field(default_factory=list)  # 视频分析
    api_entities: List[APIEntity] = field(default_factory=list)  # API实体
    dom_structure: Dict = field(default_factory=dict)  # DOM结构
    
    # 融合结果
    fused_elements: List[Dict] = field(default_factory=list)
    conflicts: List[ConflictRecord] = field(default_factory=list)
    
    # 业务理解
    business_summary: str = ""
    functionality: List[str] = field(default_factory=list)
    
    overall_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


@dataclass
class TaskUnderstanding:
    """任务理解结果"""
    task_id: str
    business_system: str
    business_domain: str
    
    pages: List[PageUnderstanding] = field(default_factory=list)
    processes: List[BusinessProcess] = field(default_factory=list)
    entities: List[APIEntity] = field(default_factory=list)
    
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
