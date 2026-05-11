"""
DOM解析器
从rrweb snapshot中提取结构化信息
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class ElementType(Enum):
    """元素类型"""
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
    HEADER = "header"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass
class DOMElement:
    """DOM元素"""
    id: int
    tag: str
    element_type: ElementType
    attributes: Dict[str, Any] = field(default_factory=dict)
    text_content: str = ""
    children: List['DOMElement'] = field(default_factory=list)
    parent_id: Optional[int] = None
    xpath: str = ""
    css_selector: str = ""
    
    # 业务语义
    business_meaning: str = ""  # 业务含义（如"提交按钮"）
    is_interactive: bool = False
    is_visible: bool = True


@dataclass
class DOMSnapshot:
    """DOM快照"""
    timestamp: int
    url: str
    title: str
    root: DOMElement
    elements_map: Dict[int, DOMElement] = field(default_factory=dict)
    
    # 页面元信息
    page_type: str = ""
    business_domain: str = ""  # 业务领域（如"招聘"、"电商"）


class DOMParser:
    """DOM解析器"""
    
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
        'header': ElementType.HEADER,
        'footer': ElementType.FOOTER,
    }
    
    # 交互式标签
    INTERACTIVE_TAGS = {'button', 'a', 'input', 'textarea', 'select', 'option'}
    
    def __init__(self, snapshot_path: str):
        """
        初始化解析器
        
        Args:
            snapshot_path: rrweb snapshot文件路径
        """
        self.snapshot_path = Path(snapshot_path)
        self.raw_data = self._load_snapshot()
        
    def _load_snapshot(self) -> Dict:
        """加载snapshot文件"""
        if not self.snapshot_path.exists():
            return {}
            
        with open(self.snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def parse(self) -> Optional[DOMSnapshot]:
        """
        解析DOM快照
        
        Returns:
            DOMSnapshot对象
        """
        if not self.raw_data:
            return None
            
        # 提取基本信息
        timestamp = self.raw_data.get('timestamp', 0)
        url = self.raw_data.get('url', '')
        title = self.raw_data.get('title', '')
        
        # 解析rrweb事件
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        event_data = rrweb_event.get('data', {})
        
        # 获取节点数据
        nodes = event_data.get('nodes', [])
        if not nodes:
            return None
            
        # 构建元素映射
        elements_map = {}
        self._build_elements_map(nodes, elements_map)
        
        # 构建树结构
        root = self._build_tree(elements_map)
        
        # 推断页面类型
        page_type = self._infer_page_type(title, url)
        
        snapshot = DOMSnapshot(
            timestamp=timestamp,
            url=url,
            title=title,
            root=root,
            elements_map=elements_map,
            page_type=page_type
        )
        
        # 提取业务语义
        self._extract_business_semantics(snapshot)
        
        return snapshot
    
    def _build_elements_map(self, nodes: List[Dict], elements_map: Dict[int, DOMElement]):
        """构建元素映射表"""
        for node in nodes:
            node_id = node.get('id')
            if node_id is None:
                continue
                
            node_type = node.get('type')
            
            if node_type == 2:  # 元素节点
                tag = node.get('tagName', '').lower()
                attributes = node.get('attributes', {})
                
                # 确定元素类型
                element_type = self.TAG_TYPE_MAP.get(tag, ElementType.CONTAINER)
                
                # 检查是否交互式
                is_interactive = tag in self.INTERACTIVE_TAGS
                
                element = DOMElement(
                    id=node_id,
                    tag=tag,
                    element_type=element_type,
                    attributes=attributes,
                    is_interactive=is_interactive
                )
                
                elements_map[node_id] = element
                
            elif node_type == 3:  # 文本节点
                text = node.get('textContent', '')
                # 文本节点单独存储，后续关联到父元素
                elements_map[node_id] = DOMElement(
                    id=node_id,
                    tag='#text',
                    element_type=ElementType.TEXT,
                    text_content=text.strip()
                )
    
    def _build_tree(self, elements_map: Dict[int, DOMElement]) -> DOMElement:
        """构建DOM树"""
        # 找到根节点（通常是id最小的元素节点）
        root = None
        for node_id, element in sorted(elements_map.items()):
            if element.tag not in ['#text', 'html']:
                root = element
                break
        
        if not root:
            root = DOMElement(id=0, tag='div', element_type=ElementType.CONTAINER)
        
        # 从raw_data重新遍历建立父子关系
        nodes = self.raw_data.get('rrwebEvent', {}).get('data', {}).get('nodes', [])
        self._build_parent_child_relationships(nodes, elements_map)
        
        return root
    
    def _build_parent_child_relationships(self, nodes: List[Dict], elements_map: Dict[int, DOMElement]):
        """建立父子关系"""
        for node in nodes:
            node_id = node.get('id')
            child_nodes = node.get('childNodes', [])
            
            if node_id not in elements_map:
                continue
                
            parent = elements_map[node_id]
            
            for child_id in child_nodes:
                if child_id in elements_map:
                    child = elements_map[child_id]
                    child.parent_id = node_id
                    parent.children.append(child)
                    
                    # 如果子元素是文本，合并到父元素的text_content
                    if child.element_type == ElementType.TEXT and child.text_content:
                        if not parent.text_content:
                            parent.text_content = child.text_content
                        else:
                            parent.text_content += " " + child.text_content
    
    def _infer_page_type(self, title: str, url: str) -> str:
        """推断页面类型"""
        title_lower = title.lower()
        url_lower = url.lower()
        
        # 根据URL和标题推断页面类型
        if '招聘' in title_lower or 'campus' in url_lower or 'job' in url_lower:
            return 'recruitment'
        elif '产品' in title_lower or 'product' in url_lower:
            return 'product'
        elif '关于' in title_lower or 'about' in url_lower:
            return 'about'
        elif '首页' in title_lower or 'index' in url_lower or url.endswith('/'):
            return 'homepage'
        elif '登录' in title_lower or 'login' in url_lower:
            return 'login'
        elif '注册' in title_lower or 'register' in url_lower:
            return 'register'
        else:
            return 'generic'
    
    def _extract_business_semantics(self, snapshot: DOMSnapshot):
        """提取业务语义"""
        # 遍历所有元素，提取业务含义
        for element in snapshot.elements_map.values():
            if element.element_type in [ElementType.BUTTON, ElementType.LINK]:
                # 从文本内容推断业务含义
                text = element.text_content.strip()
                if text:
                    element.business_meaning = self._infer_business_meaning(text)
    
    def _infer_business_meaning(self, text: str) -> str:
        """从文本推断业务含义 - 增强版"""
        text = text.strip().lower()

        # 扩展的业务语义映射
        meaning_map = {
            # 基础操作
            '提交': 'submit_action',
            '保存': 'save_action',
            '取消': 'cancel_action',
            '删除': 'delete_action',
            '编辑': 'edit_action',
            '修改': 'edit_action',
            '查看': 'view_action',
            '详情': 'view_action',
            '搜索': 'search_action',
            '查询': 'search_action',
            '登录': 'login_action',
            '登陆': 'login_action',
            '注册': 'register_action',
            '下载': 'download_action',
            '上传': 'upload_action',
            '返回': 'back_navigation',
            '后退': 'back_navigation',
            '下一步': 'next_step',
            '上一步': 'previous_step',
            '首页': 'home_navigation',
            '主页': 'home_navigation',
            '更多': 'more_options',
            '展开': 'expand_action',
            '收起': 'collapse_action',
            '关闭': 'close_action',
            '确认': 'confirm_action',
            '确定': 'confirm_action',
            '申请': 'apply_action',
            '预约': 'book_action',
            '预订': 'book_action',
            '收藏': 'favorite_action',
            '分享': 'share_action',
            '点赞': 'like_action',
            '评论': 'comment_action',
            '转发': 'forward_action',
            '打印': 'print_action',
            '导出': 'export_action',
            '导入': 'import_action',
            '刷新': 'refresh_action',
            '重置': 'reset_action',
            '清空': 'clear_action',
            '筛选': 'filter_action',
            '排序': 'sort_action',
            '新增': 'create_action',
            '添加': 'create_action',
            '创建': 'create_action',
            # 招聘相关
            '投递': 'apply_job_action',
            '应聘': 'apply_job_action',
            '职位': 'job_position',
            '招聘': 'recruitment',
            '校招': 'campus_recruitment',
            '社招': 'social_recruitment',
            '实习': 'internship',
            '简历': 'resume',
            '面试': 'interview',
            '笔试': 'written_test',
            # 电商相关
            '购买': 'purchase_action',
            '立即购买': 'buy_now_action',
            '加入购物车': 'add_to_cart_action',
            '结算': 'checkout_action',
            '支付': 'payment_action',
            '优惠券': 'coupon',
            '促销': 'promotion',
            '折扣': 'discount',
        }

        for keyword, meaning in meaning_map.items():
            if keyword in text:
                return meaning

        return ''

    def extract_layout_info(self, snapshot: DOMSnapshot) -> Dict:
        """提取布局信息"""
        layout_info = {
            'total_elements': len(snapshot.elements_map),
            'element_types': {},
            'interactive_elements': [],
            'forms': [],
            'navigation': [],
            'content_sections': [],
            'business_actions': []
        }

        for element in snapshot.elements_map.values():
            # 统计元素类型
            elem_type = element.element_type.value
            layout_info['element_types'][elem_type] = layout_info['element_types'].get(elem_type, 0) + 1

            # 收集交互元素
            if element.is_interactive and element.text_content.strip():
                layout_info['interactive_elements'].append({
                    'id': element.id,
                    'tag': element.tag,
                    'text': element.text_content[:50],
                    'type': element.element_type.value,
                    'business_meaning': element.business_meaning
                })

            # 收集表单
            if element.element_type == ElementType.FORM:
                layout_info['forms'].append({
                    'id': element.id,
                    'children_count': len(element.children)
                })

            # 收集导航
            if element.element_type in [ElementType.NAV, ElementType.HEADER]:
                layout_info['navigation'].append({
                    'id': element.id,
                    'type': element.element_type.value,
                    'text': element.text_content[:100]
                })

            # 收集业务动作
            if element.business_meaning:
                layout_info['business_actions'].append({
                    'id': element.id,
                    'text': element.text_content[:50],
                    'action': element.business_meaning
                })

        return layout_info
    
    def extract_interactive_elements(self, snapshot: DOMSnapshot) -> List[DOMElement]:
        """提取所有交互式元素"""
        interactive = []
        for element in snapshot.elements_map.values():
            if element.is_interactive and element.text_content.strip():
                interactive.append(element)
        return interactive
    
    def extract_forms(self, snapshot: DOMSnapshot) -> List[DOMElement]:
        """提取所有表单"""
        forms = []
        for element in snapshot.elements_map.values():
            if element.element_type == ElementType.FORM:
                forms.append(element)
        return forms
    
    def extract_navigation(self, snapshot: DOMSnapshot) -> List[DOMElement]:
        """提取导航元素"""
        nav_elements = []
        for element in snapshot.elements_map.values():
            if element.element_type in [ElementType.NAV, ElementType.HEADER]:
                nav_elements.append(element)
        return nav_elements

