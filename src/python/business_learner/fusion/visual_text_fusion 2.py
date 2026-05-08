"""
视觉-文本融合模块
将LLM视觉分析结果与DOM文本、API数据融合
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

from ..utils.models import PageUnderstanding, PageInfo, VisualElement


@dataclass
class VisualAnalysisResult:
    """视觉分析结果"""
    page_type: str = "unknown"
    layout_description: str = ""
    functions: List[str] = field(default_factory=list)
    ui_elements: List[Dict] = field(default_factory=list)
    content_summary: str = ""
    confidence: float = 0.0
    raw_analysis: Dict = field(default_factory=dict)


@dataclass
class TextAnalysisResult:
    """文本分析结果（DOM/API）"""
    title: str = ""
    url: str = ""
    text_content: str = ""
    interactive_elements: List[Dict] = field(default_factory=list)
    api_entities: List[Dict] = field(default_factory=list)
    structure: Dict = field(default_factory=dict)


@dataclass
class FusionConfidence:
    """融合置信度"""
    visual_confidence: float = 0.0
    text_confidence: float = 0.0
    overall_confidence: float = 0.0
    source_weights: Dict[str, float] = field(default_factory=dict)


class VisualTextFusionEngine:
    """视觉-文本融合引擎"""
    
    def __init__(self, visual_weight: float = 0.6, text_weight: float = 0.4):
        """
        初始化融合引擎
        
        Args:
            visual_weight: 视觉分析权重（用户认为视频更准确）
            text_weight: 文本分析权重
        """
        self.visual_weight = visual_weight
        self.text_weight = text_weight
    
    def fuse(self, 
             visual_result: Optional[VisualAnalysisResult],
             text_result: Optional[TextAnalysisResult],
             page_url: str = "") -> PageUnderstanding:
        """
        融合视觉和文本分析结果
        
        Args:
            visual_result: 视觉分析结果
            text_result: 文本分析结果
            page_url: 页面URL
            
        Returns:
            融合后的页面理解
        """
        # 创建基础PageInfo
        page_info = self._create_page_info(visual_result, text_result, page_url)
        
        # 融合页面类型
        page_type = self._fuse_page_type(visual_result, text_result)
        page_info.page_type = page_type
        
        # 融合功能描述
        functionality = self._fuse_functionality(visual_result, text_result)
        
        # 融合UI元素
        visual_elements = self._fuse_ui_elements(visual_result, text_result)
        
        # 计算置信度
        confidence = self._calculate_confidence(visual_result, text_result)
        
        # 生成业务摘要
        business_summary = self._generate_summary(
            visual_result, text_result, page_type, functionality
        )
        
        # 创建PageUnderstanding
        understanding = PageUnderstanding(
            page_info=page_info,
            visual_elements=visual_elements,
            functionality=functionality,
            business_summary=business_summary,
            overall_confidence=confidence
        )
        
        return understanding
    
    def _create_page_info(self, 
                         visual: Optional[VisualAnalysisResult],
                         text: Optional[TextAnalysisResult],
                         url: str) -> PageInfo:
        """创建页面信息"""
        # 优先使用文本数据（URL、标题等更准确）
        title = text.title if text and text.title else ""
        if not title and visual:
            # 从视觉分析中提取标题
            title = self._extract_title_from_visual(visual)
        
        return PageInfo(
            url=text.url if text and text.url else url,
            title=title,
            page_type="unknown",  # 后续融合确定
            load_time=0.0,
            dom_size=0
        )
    
    def _fuse_page_type(self, 
                       visual: Optional[VisualAnalysisResult],
                       text: Optional[TextAnalysisResult]) -> str:
        """融合页面类型"""
        # 视觉识别优先（用户认为视频更准确）
        if visual and visual.page_type != "unknown":
            return visual.page_type
        
        # 从URL推断
        if text and text.url:
            return self._infer_page_type_from_url(text.url)
        
        return "unknown"
    
    def _infer_page_type_from_url(self, url: str) -> str:
        """从URL推断页面类型"""
        url_lower = url.lower()
        
        if any(x in url_lower for x in ['/list', '/category', '/catalog']):
            return "list"
        elif any(x in url_lower for x in ['/detail', '/item', '/product/', '/article/']):
            return "detail"
        elif any(x in url_lower for x in ['/search', '/find', '/query']):
            return "search"
        elif any(x in url_lower for x in ['/form', '/submit', '/apply']):
            return "form"
        elif any(x in url_lower for x in ['/login', '/signin', '/auth']):
            return "auth"
        elif any(x in url_lower for x in ['/home', '/index', '/main']):
            return "home"
        
        return "content"
    
    def _fuse_functionality(self,
                           visual: Optional[VisualAnalysisResult],
                           text: Optional[TextAnalysisResult]) -> List[str]:
        """融合功能描述"""
        functions = []
        
        # 视觉识别的功能（高权重）
        if visual and visual.functions:
            for func in visual.functions:
                functions.append(f"[视觉] {func}")
        
        # 文本识别的功能
        if text and text.interactive_elements:
            for elem in text.interactive_elements:
                elem_type = elem.get('type', '')
                elem_text = elem.get('text', '')
                if elem_type and elem_text:
                    functions.append(f"[DOM] {elem_type}: {elem_text}")
        
        # API识别的功能
        if text and text.api_entities:
            for entity in text.api_entities:
                entity_type = entity.get('entity_type', '')
                if entity_type:
                    functions.append(f"[API] 数据实体: {entity_type}")
        
        # 去重和排序
        return list(dict.fromkeys(functions))
    
    def _fuse_ui_elements(self,
                         visual: Optional[VisualAnalysisResult],
                         text: Optional[TextAnalysisResult]) -> List[VisualElement]:
        """融合UI元素"""
        elements = []
        
        # 视觉识别的元素
        if visual and visual.ui_elements:
            for i, elem in enumerate(visual.ui_elements):
                elements.append(VisualElement(
                    element_id=f"visual_{i}",
                    element_type=elem.get('type', 'unknown'),
                    description=elem.get('description', ''),
                    location=elem.get('location', {}),
                    confidence=0.8  # 视觉识别置信度
                ))
        
        # DOM识别的元素
        if text and text.interactive_elements:
            for i, elem in enumerate(text.interactive_elements):
                # 检查是否已存在（基于位置和类型）
                if not self._element_exists(elements, elem):
                    elements.append(VisualElement(
                        element_id=f"dom_{i}",
                        element_type=elem.get('tag', 'unknown'),
                        description=elem.get('text', ''),
                        location={
                            'xpath': elem.get('xpath', ''),
                            'selector': elem.get('selector', '')
                        },
                        confidence=0.6  # DOM识别置信度
                    ))
        
        return elements
    
    def _element_exists(self, existing: List[VisualElement], new_elem: Dict) -> bool:
        """检查元素是否已存在"""
        new_text = new_elem.get('text', '').lower()
        new_type = new_elem.get('type', '').lower()
        
        for elem in existing:
            if (elem.description.lower() == new_text and 
                elem.element_type.lower() == new_type):
                return True
        
        return False
    
    def _calculate_confidence(self,
                             visual: Optional[VisualAnalysisResult],
                             text: Optional[TextAnalysisResult]) -> FusionConfidence:
        """计算融合置信度"""
        visual_conf = visual.confidence if visual else 0.0
        text_conf = 0.7 if text and text.text_content else 0.0
        
        # 加权计算
        if visual and text:
            overall = (visual_conf * self.visual_weight + 
                      text_conf * self.text_weight)
        elif visual:
            overall = visual_conf * 0.9  # 单一来源降低置信度
        elif text:
            overall = text_conf * 0.8
        else:
            overall = 0.0
        
        return FusionConfidence(
            visual_confidence=visual_conf,
            text_confidence=text_conf,
            overall_confidence=overall,
            source_weights={
                "visual": self.visual_weight,
                "text": self.text_weight
            }
        )
    
    def _generate_summary(self,
                         visual: Optional[VisualAnalysisResult],
                         text: Optional[TextAnalysisResult],
                         page_type: str,
                         functionality: List[str]) -> str:
        """生成业务摘要"""
        parts = []
        
        # 页面类型
        parts.append(f"这是一个{page_type}页面。")
        
        # 视觉描述
        if visual and visual.layout_description:
            parts.append(f"页面布局：{visual.layout_description}")
        
        # 内容摘要
        if visual and visual.content_summary:
            parts.append(f"内容概览：{visual.content_summary}")
        elif text and text.text_content:
            # 截取前200字符
            content = text.text_content[:200].replace('\n', ' ')
            parts.append(f"页面内容：{content}...")
        
        # 功能列表
        if functionality:
            parts.append(f"主要功能：{', '.join(functionality[:5])}")
        
        return '\n'.join(parts)
    
    def _extract_title_from_visual(self, visual: VisualAnalysisResult) -> str:
        """从视觉分析结果中提取标题"""
        # 从UI元素中查找标题
        for elem in visual.ui_elements:
            if elem.get('type') in ['h1', 'title', 'header']:
                return elem.get('description', '')
        
        # 从内容摘要中提取
        if visual.content_summary:
            lines = visual.content_summary.split('\n')
            if lines:
                return lines[0][:50]
        
        return ""
    
    def batch_fuse(self,
                  visual_results: Dict[str, VisualAnalysisResult],
                  text_results: Dict[str, TextAnalysisResult]) -> Dict[str, PageUnderstanding]:
        """
        批量融合多个页面
        
        Args:
            visual_results: 页面URL -> 视觉分析结果
            text_results: 页面URL -> 文本分析结果
            
        Returns:
            页面URL -> 融合后的理解
        """
        results = {}
        
        # 获取所有页面URL
        all_urls = set(visual_results.keys()) | set(text_results.keys())
        
        for url in all_urls:
            visual = visual_results.get(url)
            text = text_results.get(url)
            
            understanding = self.fuse(visual, text, url)
            results[url] = understanding
        
        return results


if __name__ == "__main__":
    # 测试
    engine = VisualTextFusionEngine(visual_weight=0.6, text_weight=0.4)
    
    # 模拟视觉分析结果
    visual = VisualAnalysisResult(
        page_type="list",
        layout_description="左侧导航，右侧内容列表",
        functions=["浏览公告", "搜索公告", "筛选分类"],
        ui_elements=[
            {"type": "search_box", "description": "搜索框"},
            {"type": "filter", "description": "分类筛选"},
            {"type": "list", "description": "公告列表"}
        ],
        content_summary="显示证券公告列表页面",
        confidence=0.85
    )
    
    # 模拟文本分析结果
    text = TextAnalysisResult(
        title="公告列表 - 中国银河证券",
        url="https://www.chinastock.com.cn/newsite/cgs/gg/gglb/",
        text_content="公告列表页面，包含多个公告条目",
        interactive_elements=[
            {"type": "button", "text": "搜索", "tag": "button"},
            {"type": "link", "text": "下一页", "tag": "a"}
        ],
        api_entities=[
            {"entity_type": "announcement", "data": {}}
        ]
    )
    
    # 融合
    result = engine.fuse(visual, text, text.url)
    
    print("融合结果:")
    print(f"页面类型: {result.page_info.page_type}")
    print(f"页面标题: {result.page_info.title}")
    print(f"置信度: {result.overall_confidence.overall_confidence:.2f}")
    print(f"功能数量: {len(result.functionality)}")
    print(f"UI元素数量: {len(result.visual_elements)}")
    print(f"\n业务摘要:\n{result.business_summary}")
