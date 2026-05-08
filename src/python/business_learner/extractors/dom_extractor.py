"""
DOM解析模块
从rrweb snapshot中提取DOM信息
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any

from ..utils.models import DOMElement, ElementType, PageInfo


class DOMExtractor:
    """DOM提取器"""
    
    # 标签到元素类型的映射
    TAG_TYPE_MAP = {
        'button': ElementType.BUTTON,
        'a': ElementType.LINK,
        'input': ElementType.INPUT,
        'textarea': ElementType.INPUT,
        'select': ElementType.INPUT,
        'img': ElementType.IMAGE,
        'h1': ElementType.HEADING,
        'h2': ElementType.HEADING,
        'h3': ElementType.HEADING,
        'h4': ElementType.HEADING,
        'h5': ElementType.HEADING,
        'h6': ElementType.HEADING,
        'ul': ElementType.LIST,
        'ol': ElementType.LIST,
        'table': ElementType.TABLE,
        'form': ElementType.FORM,
        'nav': ElementType.NAV,
    }
    
    INTERACTIVE_TAGS = {'button', 'a', 'input', 'textarea', 'select'}
    
    def __init__(self, snapshot_path: str):
        """
        初始化提取器
        
        Args:
            snapshot_path: DOM snapshot文件路径
        """
        self.snapshot_path = Path(snapshot_path)
        self.raw_data = self._load_snapshot()
    
    def _load_snapshot(self) -> Dict:
        """加载snapshot文件"""
        if not self.snapshot_path.exists():
            return {}
            
        with open(self.snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract_page_info(self) -> Optional[PageInfo]:
        """提取页面基本信息"""
        if not self.raw_data:
            return None
            
        return PageInfo(
            url=self.raw_data.get('url', ''),
            title=self.raw_data.get('title', ''),
            page_type=self._infer_page_type(),
            business_domain=self._infer_domain(),
            timestamp=self.raw_data.get('timestamp', 0)
        )
    
    def extract_elements(self) -> List[DOMElement]:
        """提取所有DOM元素"""
        elements = []
        
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        nodes = rrweb_event.get('data', {}).get('nodes', [])
        
        for node in nodes:
            element = self._parse_node(node)
            if element:
                elements.append(element)
        
        return elements
    
    def extract_interactive_elements(self) -> List[DOMElement]:
        """提取交互式元素"""
        all_elements = self.extract_elements()
        return [e for e in all_elements if e.is_interactive and e.text_content.strip()]
    
    def extract_text_content(self) -> str:
        """提取所有文本内容"""
        elements = self.extract_elements()
        texts = []
        
        for elem in elements:
            if elem.text_content.strip():
                texts.append(elem.text_content.strip())
        
        return ' '.join(texts)
    
    def _parse_node(self, node: Dict) -> Optional[DOMElement]:
        """解析单个节点"""
        node_type = node.get('type')
        node_id = node.get('id')
        
        if node_id is None:
            return None
        
        if node_type == 2:  # 元素节点
            tag = node.get('tagName', '').lower()
            attributes = node.get('attributes', {})
            
            element_type = self.TAG_TYPE_MAP.get(tag, ElementType.CONTAINER)
            is_interactive = tag in self.INTERACTIVE_TAGS
            
            # 提取文本内容（从子节点）
            text_content = self._extract_text_from_children(node)
            
            return DOMElement(
                id=node_id,
                tag=tag,
                element_type=element_type,
                attributes=attributes,
                text_content=text_content,
                is_interactive=is_interactive
            )
        
        elif node_type == 3:  # 文本节点
            text = node.get('textContent', '').strip()
            if text:
                return DOMElement(
                    id=node_id,
                    tag='#text',
                    element_type=ElementType.TEXT,
                    text_content=text
                )
        
        return None
    
    def _extract_text_from_children(self, node: Dict) -> str:
        """从子节点提取文本"""
        texts = []
        child_ids = node.get('childNodes', [])
        
        # 这里简化处理，实际需要递归查找
        # 由于rrweb的nodes是扁平化的，需要另外处理
        
        return ' '.join(texts)
    
    def _infer_page_type(self) -> str:
        """推断页面类型"""
        title = self.raw_data.get('title', '').lower()
        url = self.raw_data.get('url', '').lower()
        
        patterns = [
            (['campus', 'recruitment', 'job', '招聘'], 'recruitment'),
            (['announcement', '公告'], 'announcement'),
            (['product', '产品'], 'product'),
            (['about', '关于'], 'about'),
            (['index', 'home', '首页'], 'homepage'),
        ]
        
        for keywords, page_type in patterns:
            if any(k in title or k in url for k in keywords):
                return page_type
        
        return 'generic'
    
    def _infer_domain(self) -> str:
        """推断业务域"""
        url = self.raw_data.get('url', '').lower()
        
        if 'chinastock' in url:
            if 'zhiye' in url or 'campus' in url:
                return '银河证券-招聘系统'
            return '银河证券-官网'
        
        return '未知'

