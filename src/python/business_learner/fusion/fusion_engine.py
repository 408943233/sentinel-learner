"""
数据融合引擎
解决视频、API、DOM之间的冲突，生成统一视图
"""

from typing import List, Dict, Optional, Any
from dataclasses import asdict

from ..utils.models import (
    VideoFrame, APIEntity, DOMElement, PageUnderstanding,
    ConflictRecord, ConfidenceLevel, DataSource
)
from ..config.settings import FUSION_CONFIG


class FusionEngine:
    """数据融合引擎"""
    
    def __init__(self):
        """初始化融合引擎"""
        self.conflicts: List[ConflictRecord] = []
        self.config = FUSION_CONFIG["conflict_resolution"]
    
    def fuse_page_data(
        self,
        page_info,
        visual_elements: List[Dict],
        api_entities: List[APIEntity],
        dom_elements: List[DOMElement]
    ) -> PageUnderstanding:
        """
        融合页面数据
        
        Args:
            page_info: 页面信息
            visual_elements: 视频分析的视觉元素
            api_entities: API提取的实体
            dom_elements: DOM元素
            
        Returns:
            页面理解结果
        """
        understanding = PageUnderstanding(page_info=page_info)
        
        # 保存原始数据
        understanding.visual_elements = visual_elements
        understanding.api_entities = api_entities
        understanding.dom_structure = {
            "elements": [asdict(e) for e in dom_elements],
            "interactive_count": len([e for e in dom_elements if e.is_interactive])
        }
        
        # 融合元素
        understanding.fused_elements = self._fuse_elements(
            visual_elements, api_entities, dom_elements
        )
        
        # 检测冲突
        understanding.conflicts = self.conflicts
        
        # 评估整体可信度
        understanding.overall_confidence = self._calculate_confidence(
            len(visual_elements), len(api_entities), len(dom_elements), len(self.conflicts)
        )
        
        return understanding
    
    def _fuse_elements(
        self,
        visual_elements: List[Dict],
        api_entities: List[APIEntity],
        dom_elements: List[DOMElement]
    ) -> List[Dict]:
        """融合元素（简化版）"""
        fused = []
        
        # 1. 首先添加API实体（优先级最高）
        for entity in api_entities:
            fused.append({
                "type": "entity",
                "source": DataSource.API,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "attributes": entity.attributes,
                "confidence": entity.confidence.value
            })
        
        # 2. 添加DOM交互元素
        for elem in dom_elements:
            if elem.is_interactive and elem.text_content.strip():
                # 检查是否与API实体冲突
                conflict = self._check_text_conflict(
                    elem.text_content, api_entities
                )
                
                if conflict:
                    # 记录冲突
                    self._record_conflict(
                        element_id=f"dom_{elem.id}",
                        video_value=None,
                        dom_value=elem.text_content,
                        api_value=conflict.get('api_value'),
                        resolved_value=conflict.get('resolved'),
                        strategy=conflict.get('strategy')
                    )
                    
                    # 使用解决后的值
                    fused.append({
                        "type": "interactive_element",
                        "source": DataSource.DOM,
                        "tag": elem.tag,
                        "text": conflict.get('resolved'),
                        "original_text": elem.text_content,
                        "confidence": ConfidenceLevel.MEDIUM.value,
                        "conflict_resolved": True
                    })
                else:
                    fused.append({
                        "type": "interactive_element",
                        "source": DataSource.DOM,
                        "tag": elem.tag,
                        "text": elem.text_content,
                        "confidence": ConfidenceLevel.HIGH.value
                    })
        
        # 3. 添加视觉元素
        for visual in visual_elements:
            fused.append({
                "type": "visual",
                "source": DataSource.VIDEO,
                "event_type": visual.get('event_type'),
                "timestamp": visual.get('timestamp'),
                "frame_path": visual.get('frame_path'),
                "confidence": ConfidenceLevel.MEDIUM.value
            })
        
        return fused
    
    def _check_text_conflict(self, dom_text: str, api_entities: List[APIEntity]) -> Optional[Dict]:
        """检查文本冲突"""
        dom_text_clean = dom_text.strip().lower()
        
        for entity in api_entities:
            entity_name = entity.name.strip().lower()
            
            # 如果DOM文本与API实体名称相似但不完全相同
            if dom_text_clean != entity_name and (
                dom_text_clean in entity_name or entity_name in dom_text_clean
            ):
                # 文本类优先DOM
                return {
                    'api_value': entity.name,
                    'dom_value': dom_text,
                    'resolved': dom_text,  # DOM优先
                    'strategy': 'text_priority_dom'
                }
        
        return None
    
    def _record_conflict(
        self,
        element_id: str,
        video_value: Any,
        dom_value: Any,
        api_value: Any,
        resolved_value: Any,
        strategy: str
    ):
        """记录冲突"""
        conflict = ConflictRecord(
            element_id=element_id,
            video_value=video_value,
            dom_value=dom_value,
            api_value=api_value,
            resolved_value=resolved_value,
            resolution_strategy=strategy,
            confidence=ConfidenceLevel.MEDIUM
        )
        self.conflicts.append(conflict)
    
    def _calculate_confidence(
        self,
        visual_count: int,
        api_count: int,
        dom_count: int,
        conflict_count: int
    ) -> ConfidenceLevel:
        """计算整体可信度"""
        # 数据源越多越可信
        source_count = sum([visual_count > 0, api_count > 0, dom_count > 0])
        
        # 冲突越少越可信
        if conflict_count == 0 and source_count >= 2:
            return ConfidenceLevel.HIGH
        elif conflict_count <= 2 and source_count >= 2:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def get_conflict_summary(self) -> Dict:
        """获取冲突摘要"""
        return {
            "total_conflicts": len(self.conflicts),
            "by_strategy": self._group_conflicts_by_strategy(),
            "high_impact": len([c for c in self.conflicts if c.confidence == ConfidenceLevel.LOW])
        }
    
    def _group_conflicts_by_strategy(self) -> Dict:
        """按解决策略分组冲突"""
        groups = {}
        for conflict in self.conflicts:
            strategy = conflict.resolution_strategy
            if strategy not in groups:
                groups[strategy] = 0
            groups[strategy] += 1
        return groups


if __name__ == "__main__":
    # 测试
    from ..utils.models import PageInfo
    
    engine = FusionEngine()
    
    page_info = PageInfo(
        url="https://example.com",
        title="测试页面",
        page_type="test",
        business_domain="测试"
    )
    
    # 模拟数据
    visual = [{"event_type": "click", "timestamp": 1.0}]
    api = [APIEntity(entity_type="test", name="测试实体", attributes={}, source_url="")]
    dom = [DOMElement(id=1, tag="button", element_type=ElementType.BUTTON, text_content="提交", is_interactive=True)]
    
    result = engine.fuse_page_data(page_info, visual, api, dom)
    
    print(f"融合元素数: {len(result.fused_elements)}")
    print(f"冲突数: {len(result.conflicts)}")
    print(f"可信度: {result.overall_confidence.value}")
