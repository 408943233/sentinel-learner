"""
Task元数据管理模块
管理Task的上传、处理和版本信息
"""

import json
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class TaskStatus(Enum):
    """Task处理状态"""
    PENDING = "pending"           # 待处理
    PROCESSING = "processing"     # 处理中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 处理失败


@dataclass
class TargetSystem:
    """目标系统信息"""
    name: str
    domain: str
    system_type: str = ""         # financial_services, e-commerce, etc.
    primary_language: str = "zh-CN"
    description: str = ""


@dataclass
class RecorderInfo:
    """录制者信息"""
    user_id: str
    user_name: str = ""
    operator_name: str = ""  # 操作人姓名（用于冲突解决）
    department: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())
    recorder_version: str = "sentinel-browser-v1.0.0"


@dataclass
class UploadInfo:
    """上传信息"""
    uploaded_at: str = field(default_factory=lambda: datetime.now().isoformat())
    uploaded_by: str = ""
    source_ip: str = ""
    user_agent: str = ""


@dataclass
class ProcessingInfo:
    """处理信息"""
    status: str = TaskStatus.PENDING.value
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processor_version: str = "business-learner-v1.0.0"
    error_message: str = ""
    processing_duration: float = 0.0  # 处理耗时（秒）


@dataclass
class TaskMetadata:
    """Task完整元数据"""
    task_id: str
    task_name: str
    task_description: str = ""
    expected_outcome: str = ""
    
    # 录制信息
    recorder: RecorderInfo = field(default_factory=lambda: RecorderInfo(user_id=""))
    
    # 目标系统
    target_system: TargetSystem = field(default_factory=lambda: TargetSystem(name="", domain=""))
    
    # 上传信息
    upload: UploadInfo = field(default_factory=UploadInfo)
    
    # 处理信息
    processing: ProcessingInfo = field(default_factory=ProcessingInfo)
    
    # 标签和分类
    tags: List[str] = field(default_factory=list)
    category: str = ""  # 任务分类：探索、测试、培训等
    
    # 版本控制
    version: int = 1
    parent_task_id: Optional[str] = None  # 父任务ID（用于任务链）
    related_tasks: List[str] = field(default_factory=list)  # 相关任务
    
    # 权限
    visibility: str = "private"  # private, team, public
    allowed_users: List[str] = field(default_factory=list)
    
    # 扩展字段
    extra: Dict = field(default_factory=dict)
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class TaskMetadataManager:
    """Task元数据管理器"""
    
    def __init__(self, task_path: str):
        """
        初始化管理器
        
        Args:
            task_path: Task数据目录路径
        """
        self.task_path = Path(task_path)
        self.metadata_file = self.task_path / "metadata.json"
        self.learner_metadata_file = self.task_path / "learner_metadata.json"
        
    def load_metadata(self) -> Optional[TaskMetadata]:
        """
        加载Task元数据
        
        优先加载learner_metadata（如果存在），否则从metadata.json构建
        """
        # 尝试加载learner_metadata
        if self.learner_metadata_file.exists():
            with open(self.learner_metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return self._dict_to_metadata(data)
        
        # 从原始metadata.json构建
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                return self._build_from_raw_metadata(raw_data)
        
        return None
    
    def save_metadata(self, metadata: TaskMetadata):
        """保存Task元数据"""
        metadata.updated_at = datetime.now().isoformat()
        
        with open(self.learner_metadata_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(metadata), f, ensure_ascii=False, indent=2)
    
    def update_processing_status(self, status: TaskStatus, 
                                 error_message: str = "",
                                 duration: float = 0.0):
        """更新处理状态"""
        metadata = self.load_metadata()
        if not metadata:
            return
        
        metadata.processing.status = status.value
        metadata.processing.error_message = error_message
        
        if status == TaskStatus.PROCESSING:
            metadata.processing.started_at = datetime.now().isoformat()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            metadata.processing.completed_at = datetime.now().isoformat()
            metadata.processing.processing_duration = duration
        
        self.save_metadata(metadata)
    
    def _build_from_raw_metadata(self, raw_data: Dict) -> TaskMetadata:
        """从原始metadata.json构建完整元数据"""
        task_id = raw_data.get('task_id', self.task_path.name)
        
        # 构建录制者信息（支持 operator_name）
        recorder = RecorderInfo(
            user_id=raw_data.get('user_id', 'anonymous'),
            user_name=raw_data.get('user_name', ''),
            operator_name=raw_data.get('operator_name', ''),  # 从 metadata.json 读取操作人姓名
            recorded_at=raw_data.get('created_at', datetime.now().isoformat()),
            recorder_version=f"sentinel-browser-v{raw_data.get('browser_version', '1.0.0')}"
        )
        
        # 构建目标系统信息
        start_url = raw_data.get('start_url', '')
        domain = self._extract_domain(start_url)
        
        target_system = TargetSystem(
            name=self._infer_system_name(domain),
            domain=domain,
            system_type=self._infer_system_type(domain),
            primary_language="zh-CN"
        )
        
        # 构建Task名称和描述
        task_name = raw_data.get('task_name', '未命名任务')
        
        return TaskMetadata(
            task_id=task_id,
            task_name=task_name,
            task_description=f"Task recorded from {start_url}",
            recorder=recorder,
            target_system=target_system,
            created_at=raw_data.get('created_at', datetime.now().isoformat())
        )
    
    def _dict_to_metadata(self, data: Dict) -> TaskMetadata:
        """将字典转换为TaskMetadata"""
        # 处理嵌套对象
        recorder_data = data.get('recorder', {})
        recorder = RecorderInfo(**recorder_data) if recorder_data else RecorderInfo(user_id="")
        
        target_data = data.get('target_system', {})
        target_system = TargetSystem(**target_data) if target_data else TargetSystem(name="", domain="")
        
        upload_data = data.get('upload', {})
        upload = UploadInfo(**upload_data) if upload_data else UploadInfo()
        
        processing_data = data.get('processing', {})
        processing = ProcessingInfo(**processing_data) if processing_data else ProcessingInfo()
        
        return TaskMetadata(
            task_id=data.get('task_id', ''),
            task_name=data.get('task_name', ''),
            task_description=data.get('task_description', ''),
            expected_outcome=data.get('expected_outcome', ''),
            recorder=recorder,
            target_system=target_system,
            upload=upload,
            processing=processing,
            tags=data.get('tags', []),
            category=data.get('category', ''),
            version=data.get('version', 1),
            parent_task_id=data.get('parent_task_id'),
            related_tasks=data.get('related_tasks', []),
            visibility=data.get('visibility', 'private'),
            allowed_users=data.get('allowed_users', []),
            extra=data.get('extra', {}),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat())
        )
    
    def _extract_domain(self, url: str) -> str:
        """从URL提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return url
    
    def _infer_system_name(self, domain: str) -> str:
        """推断系统名称"""
        domain_lower = domain.lower()
        
        if 'chinastock' in domain_lower:
            return "中国银河证券官方网站"
        elif 'zhiye' in domain_lower:
            return "银河证券招聘系统"
        elif 'baidu' in domain_lower:
            return "百度"
        elif 'alibaba' in domain_lower:
            return "阿里巴巴"
        
        return domain
    
    def _infer_system_type(self, domain: str) -> str:
        """推断系统类型"""
        domain_lower = domain.lower()
        
        if any(kw in domain_lower for kw in ['bank', 'stock', 'finance', '证券', '银行']):
            return "financial_services"
        elif any(kw in domain_lower for kw in ['shop', 'mall', 'taobao', 'jd']):
            return "e-commerce"
        elif any(kw in domain_lower for kw in ['zhiye', 'job', 'hire', '招聘']):
            return "recruitment"
        
        return "generic"
    
    def load_or_create(self) -> TaskMetadata:
        """加载或创建元数据"""
        metadata = self.load_metadata()
        if metadata:
            return metadata
        
        # 创建默认元数据
        return TaskMetadata(
            task_id=self.task_path.name,
            task_name="未命名任务",
            task_description="",
            recorder=RecorderInfo(user_id="anonymous"),
            target_system=TargetSystem(name="未知系统", domain=""),
            created_at=datetime.now().isoformat()
        )
    
    def get_system_identifier(self) -> str:
        """获取系统唯一标识符"""
        metadata = self.load_metadata()
        if metadata and metadata.target_system:
            return f"{metadata.target_system.name}_{metadata.target_system.domain}"
        return self.task_path.name
    
    def to_knowledge_graph_format(self) -> Dict:
        """转换为知识图谱存储格式"""
        metadata = self.load_metadata()
        if not metadata:
            return {}
        
        return {
            "entity_type": "TaskRecording",
            "properties": {
                "task_id": metadata.task_id,
                "task_name": metadata.task_name,
                "description": metadata.task_description,
                "recorded_at": metadata.recorder.recorded_at,
                "recorded_by": metadata.recorder.user_id,
                "target_system": metadata.target_system.name,
                "target_domain": metadata.target_system.domain,
                "status": metadata.processing.status,
                "version": metadata.version
            },
            "metadata": {
                "source": "sentinel-browser",
                "authority_level": "observation",
                "confidence": 0.9
            }
        }

