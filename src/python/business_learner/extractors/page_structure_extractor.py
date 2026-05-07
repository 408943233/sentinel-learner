"""
页面结构提取器
提取页面布局、组件结构和样式信息
用于生成原型Demo
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import re


class LayoutType(Enum):
    """布局类型"""
    HEADER = "header"
    SIDEBAR = "sidebar"
    MAIN = "main"
    FOOTER = "footer"
    GRID = "grid"
    FLEX = "flex"
    CARD = "card"
    FORM = "form"
    TABLE = "table"
    LIST = "list"
    NAVIGATION = "navigation"
    UNKNOWN = "unknown"


class ComponentType(Enum):
    """组件类型"""
    BUTTON = "button"
    INPUT = "input"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    MODAL = "modal"
    DROPDOWN = "dropdown"
    TABS = "tabs"
    ACCORDION = "accordion"
    CAROUSEL = "carousel"
    MENU = "menu"
    SEARCH = "search"
    PAGINATION = "pagination"
    BREADCRUMB = "breadcrumb"
    ALERT = "alert"
    TOOLTIP = "tooltip"
    UNKNOWN = "unknown"


@dataclass
class StyleInfo:
    """样式信息"""
    # 布局
    display: str = ""
    position: str = ""
    width: str = ""
    height: str = ""
    margin: str = ""
    padding: str = ""
    
    # Flex/Grid
    flex_direction: str = ""
    justify_content: str = ""
    align_items: str = ""
    grid_template: str = ""
    gap: str = ""
    
    # 外观
    background_color: str = ""
    color: str = ""
    font_size: str = ""
    font_family: str = ""
    border: str = ""
    border_radius: str = ""
    box_shadow: str = ""
    
    # 其他
    z_index: str = ""
    overflow: str = ""
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class ComponentInfo:
    """组件信息"""
    id: str
    type: ComponentType
    name: str = ""  # 组件名称（如"搜索按钮"）
    description: str = ""  # 组件描述
    
    # 结构
    tag: str = ""
    class_names: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    # 样式
    styles: StyleInfo = field(default_factory=StyleInfo)
    computed_styles: Dict[str, str] = field(default_factory=dict)
    
    # 内容
    text_content: str = ""
    placeholder: str = ""
    
    # 层级
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    depth: int = 0
    
    # 交互
    is_interactive: bool = False
    event_handlers: List[str] = field(default_factory=list)
    
    # 位置（相对于视口）
    bounding_box: Dict[str, float] = field(default_factory=dict)  # x, y, width, height
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['type'] = self.type.value
        result['styles'] = self.styles.to_dict()
        return result


@dataclass
class LayoutSection:
    """布局区块"""
    id: str
    type: LayoutType
    name: str = ""  # 如"顶部导航栏"
    
    # 结构
    component_ids: List[str] = field(default_factory=list)
    parent_section_id: Optional[str] = None
    child_sections: List[str] = field(default_factory=list)
    
    # 样式
    styles: StyleInfo = field(default_factory=StyleInfo)
    
    # 位置
    bounding_box: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['type'] = self.type.value
        result['styles'] = self.styles.to_dict()
        return result


@dataclass
class PageStructure:
    """页面结构完整信息"""
    url: str
    title: str
    timestamp: int
    
    # 视口信息
    viewport: Dict[str, int] = field(default_factory=dict)  # width, height
    
    # 布局
    layout_sections: List[LayoutSection] = field(default_factory=list)
    
    # 组件
    components: List[ComponentInfo] = field(default_factory=list)
    
    # 样式系统
    color_palette: List[str] = field(default_factory=list)  # 颜色体系
    typography: Dict[str, Any] = field(default_factory=dict)  # 字体系统
    spacing_system: Dict[str, str] = field(default_factory=dict)  # 间距系统
    
    # CSS文件
    css_files: List[str] = field(default_factory=list)
    inline_styles: List[str] = field(default_factory=list)
    
    # 响应式断点
    breakpoints: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'url': self.url,
            'title': self.title,
            'timestamp': self.timestamp,
            'viewport': self.viewport,
            'layout_sections': [s.to_dict() for s in self.layout_sections],
            'components': [c.to_dict() for c in self.components],
            'color_palette': self.color_palette,
            'typography': self.typography,
            'spacing_system': self.spacing_system,
            'css_files': self.css_files,
            'inline_styles': self.inline_styles,
            'breakpoints': self.breakpoints
        }


class PageStructureExtractor:
    """页面结构提取器"""
    
    # 布局识别规则
    LAYOUT_PATTERNS = {
        LayoutType.HEADER: ['header', 'nav', 'navbar', 'top-bar', 'app-bar'],
        LayoutType.SIDEBAR: ['sidebar', 'side-menu', 'sidenav', 'drawer'],
        LayoutType.MAIN: ['main', 'content', 'container'],
        LayoutType.FOOTER: ['footer'],
        LayoutType.GRID: ['grid', 'row', 'col'],
        LayoutType.CARD: ['card', 'panel', 'box'],
        LayoutType.FORM: ['form', 'field'],
    }
    
    # 组件识别规则
    COMPONENT_PATTERNS = {
        ComponentType.BUTTON: ['button', 'btn', 'submit'],
        ComponentType.INPUT: ['input', 'textfield', 'form-control'],
        ComponentType.SELECT: ['select', 'dropdown', 'combobox'],
        ComponentType.MODAL: ['modal', 'dialog', 'popup', 'overlay'],
        ComponentType.TABS: ['tab', 'tabs'],
        ComponentType.MENU: ['menu', 'nav-menu'],
        ComponentType.SEARCH: ['search', 'searchbox'],
        ComponentType.PAGINATION: ['pagination', 'pager'],
    }
    
    def __init__(self, snapshot_path: str, resources_path: Optional[str] = None):
        """
        初始化提取器
        
        Args:
            snapshot_path: DOM snapshot文件路径
            resources_path: 资源文件路径（包含CSS）
        """
        self.snapshot_path = Path(snapshot_path)
        self.resources_path = Path(resources_path) if resources_path else None
        self.raw_data = self._load_snapshot()
        
    def _load_snapshot(self) -> Dict:
        """加载snapshot文件"""
        if not self.snapshot_path.exists():
            return {}
        with open(self.snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract(self) -> Optional[PageStructure]:
        """
        提取完整的页面结构
        
        Returns:
            PageStructure对象
        """
        if not self.raw_data:
            return None
        
        # 基本信息
        url = self.raw_data.get('url', '')
        title = self.raw_data.get('title', '')
        timestamp = self.raw_data.get('timestamp', 0)
        
        # 提取视口信息
        viewport = self._extract_viewport()
        
        # 提取组件
        components = self._extract_components()
        
        # 识别布局区块
        layout_sections = self._identify_layout_sections(components)
        
        # 提取样式系统
        color_palette = self._extract_color_palette(components)
        typography = self._extract_typography(components)
        spacing_system = self._extract_spacing_system(components)
        
        # 提取CSS文件
        css_files = self._extract_css_files()
        
        return PageStructure(
            url=url,
            title=title,
            timestamp=timestamp,
            viewport=viewport,
            layout_sections=layout_sections,
            components=components,
            color_palette=color_palette,
            typography=typography,
            spacing_system=spacing_system,
            css_files=css_files
        )
    
    def _extract_viewport(self) -> Dict[str, int]:
        """提取视口信息"""
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        data = rrweb_event.get('data', {})
        
        # 从rrweb的meta事件中提取
        if rrweb_event.get('type') == 4:  # Meta事件
            width = data.get('width', 1920)
            height = data.get('height', 1080)
            return {'width': width, 'height': height}
        
        return {'width': 1920, 'height': 1080}
    
    def _extract_components(self) -> List[ComponentInfo]:
        """提取所有组件"""
        components = []
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        nodes = rrweb_event.get('data', {}).get('nodes', [])
        
        for node in nodes:
            component = self._parse_component_node(node)
            if component:
                components.append(component)
        
        # 建立父子关系
        self._build_component_hierarchy(components, nodes)
        
        return components
    
    def _parse_component_node(self, node: Dict) -> Optional[ComponentInfo]:
        """解析组件节点"""
        node_type = node.get('type')
        node_id = node.get('id')
        
        if node_id is None or node_type != 2:  # 只处理元素节点
            return None
        
        tag = node.get('tagName', '').lower()
        attributes = node.get('attributes', {})
        
        # 识别组件类型
        component_type = self._identify_component_type(tag, attributes)
        
        # 提取类名
        class_attr = attributes.get('class', '')
        class_names = class_attr.split() if isinstance(class_attr, str) else []
        
        # 提取样式
        styles = self._extract_inline_styles(attributes.get('style', ''))
        
        # 提取文本内容
        text_content = self._extract_node_text(node)
        
        # 检查是否交互式
        is_interactive = self._is_interactive_element(tag, attributes)
        
        # 提取事件处理器
        event_handlers = self._extract_event_handlers(attributes)
        
        return ComponentInfo(
            id=f"comp_{node_id}",
            type=component_type,
            tag=tag,
            class_names=class_names,
            attributes=attributes,
            styles=styles,
            text_content=text_content,
            is_interactive=is_interactive,
            event_handlers=event_handlers
        )
    
    def _identify_component_type(self, tag: str, attributes: Dict) -> ComponentType:
        """识别组件类型"""
        class_attr = attributes.get('class', '')
        classes = class_attr.lower() if isinstance(class_attr, str) else ''
        
        # 根据标签识别
        if tag == 'button' or 'btn' in classes:
            return ComponentType.BUTTON
        elif tag == 'input':
            input_type = attributes.get('type', 'text')
            if input_type == 'checkbox':
                return ComponentType.CHECKBOX
            elif input_type == 'radio':
                return ComponentType.RADIO
            return ComponentType.INPUT
        elif tag == 'select':
            return ComponentType.SELECT
        elif tag in ['nav', 'menu'] or 'nav' in classes:
            return ComponentType.MENU
        
        # 根据类名识别
        for comp_type, patterns in self.COMPONENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in classes:
                    return comp_type
        
        return ComponentType.UNKNOWN
    
    def _extract_inline_styles(self, style_str: str) -> StyleInfo:
        """提取内联样式"""
        styles = StyleInfo()
        
        if not style_str:
            return styles
        
        # 解析样式字符串
        style_dict = {}
        for decl in style_str.split(';'):
            if ':' in decl:
                prop, val = decl.split(':', 1)
                style_dict[prop.strip()] = val.strip()
        
        # 映射到StyleInfo
        styles.display = style_dict.get('display', '')
        styles.position = style_dict.get('position', '')
        styles.width = style_dict.get('width', '')
        styles.height = style_dict.get('height', '')
        styles.margin = style_dict.get('margin', '')
        styles.padding = style_dict.get('padding', '')
        styles.background_color = style_dict.get('background-color', '')
        styles.color = style_dict.get('color', '')
        styles.font_size = style_dict.get('font-size', '')
        styles.border = style_dict.get('border', '')
        styles.border_radius = style_dict.get('border-radius', '')
        styles.flex_direction = style_dict.get('flex-direction', '')
        styles.justify_content = style_dict.get('justify-content', '')
        styles.align_items = style_dict.get('align-items', '')
        
        return styles
    
    def _extract_node_text(self, node: Dict) -> str:
        """提取节点文本内容"""
        texts = []
        
        # 从childNodes中提取文本
        child_ids = node.get('childNodes', [])
        # 这里需要查找对应的文本节点
        # 简化处理，实际应该递归查找
        
        return ' '.join(texts)
    
    def _is_interactive_element(self, tag: str, attributes: Dict) -> bool:
        """判断是否为交互式元素"""
        interactive_tags = {'button', 'a', 'input', 'textarea', 'select', 'option'}
        if tag in interactive_tags:
            return True
        
        # 检查是否有交互事件
        interactive_events = ['onclick', 'onchange', 'onsubmit', 'onkeydown']
        for event in interactive_events:
            if event in attributes:
                return True
        
        return False
    
    def _extract_event_handlers(self, attributes: Dict) -> List[str]:
        """提取事件处理器"""
        events = []
        event_prefixes = ['on', 'data-on']
        
        for attr in attributes.keys():
            for prefix in event_prefixes:
                if attr.startswith(prefix):
                    events.append(attr)
                    break
        
        return events
    
    def _build_component_hierarchy(self, components: List[ComponentInfo], nodes: List[Dict]):
        """建立组件层级关系"""
        node_map = {node.get('id'): node for node in nodes if node.get('id') is not None}
        comp_map = {comp.id: comp for comp in components}
        
        for comp in components:
            node_id = int(comp.id.replace('comp_', ''))
            node = node_map.get(node_id)
            
            if node:
                # 父节点
                parent_id = node.get('parentId')
                if parent_id is not None:
                    comp.parent_id = f"comp_{parent_id}"
                
                # 子节点
                child_ids = node.get('childNodes', [])
                comp.children_ids = [f"comp_{cid}" for cid in child_ids if cid in node_map]
    
    def _identify_layout_sections(self, components: List[ComponentInfo]) -> List[LayoutSection]:
        """识别布局区块"""
        sections = []
        section_id = 0
        
        for comp in components:
            layout_type = self._identify_layout_type(comp)
            
            if layout_type != LayoutType.UNKNOWN:
                section = LayoutSection(
                    id=f"section_{section_id}",
                    type=layout_type,
                    name=self._generate_section_name(comp, layout_type),
                    component_ids=[comp.id]
                )
                sections.append(section)
                section_id += 1
        
        return sections
    
    def _identify_layout_type(self, component: ComponentInfo) -> LayoutType:
        """识别布局类型"""
        classes = ' '.join(component.class_names).lower()
        tag = component.tag.lower()
        
        # 根据标签识别
        if tag == 'header':
            return LayoutType.HEADER
        elif tag == 'footer':
            return LayoutType.FOOTER
        elif tag == 'nav':
            return LayoutType.NAVIGATION
        elif tag == 'main':
            return LayoutType.MAIN
        
        # 根据类名识别
        for layout_type, patterns in self.LAYOUT_PATTERNS.items():
            for pattern in patterns:
                if pattern in classes:
                    return layout_type
        
        # 检查样式
        styles = component.styles
        if styles.display == 'grid':
            return LayoutType.GRID
        elif styles.display == 'flex':
            return LayoutType.FLEX
        
        return LayoutType.UNKNOWN
    
    def _generate_section_name(self, component: ComponentInfo, layout_type: LayoutType) -> str:
        """生成区块名称"""
        if component.text_content.strip():
            return f"{layout_type.value}: {component.text_content[:20]}"
        return layout_type.value
    
    def _extract_color_palette(self, components: List[ComponentInfo]) -> List[str]:
        """提取颜色体系"""
        colors = set()
        
        for comp in components:
            styles = comp.styles
            if styles.background_color:
                colors.add(styles.background_color)
            if styles.color:
                colors.add(styles.color)
            if styles.border:
                # 从border提取颜色
                border_color = self._extract_color_from_border(styles.border)
                if border_color:
                    colors.add(border_color)
        
        return list(colors)[:20]  # 限制数量
    
    def _extract_color_from_border(self, border: str) -> Optional[str]:
        """从border属性提取颜色"""
        # 简单匹配颜色值
        color_patterns = [
            r'#[a-fA-F0-9]{3,8}',  # hex
            r'rgb\([^)]+\)',        # rgb
            r'rgba\([^)]+\)',       # rgba
        ]
        for pattern in color_patterns:
            match = re.search(pattern, border)
            if match:
                return match.group(0)
        return None
    
    def _extract_typography(self, components: List[ComponentInfo]) -> Dict[str, Any]:
        """提取字体系统"""
        font_sizes = set()
        font_families = set()
        
        for comp in components:
            if comp.styles.font_size:
                font_sizes.add(comp.styles.font_size)
            if comp.styles.font_family:
                font_families.add(comp.styles.font_family)
        
        return {
            'font_sizes': list(font_sizes)[:10],
            'font_families': list(font_families)[:5],
            'heading_sizes': self._identify_heading_sizes(font_sizes)
        }
    
    def _identify_heading_sizes(self, font_sizes: set) -> Dict[str, str]:
        """识别标题字体大小层级"""
        # 简化处理，实际应该根据使用场景判断
        sizes = sorted(list(font_sizes), key=lambda x: self._parse_size(x), reverse=True)
        
        headings = {}
        for i, size in enumerate(sizes[:6]):
            headings[f'h{i+1}'] = size
        
        return headings
    
    def _parse_size(self, size: str) -> float:
        """解析尺寸值为数字"""
        match = re.match(r'([\d.]+)', size)
        return float(match.group(1)) if match else 0.0
    
    def _extract_spacing_system(self, components: List[ComponentInfo]) -> Dict[str, str]:
        """提取间距系统"""
        margins = set()
        paddings = set()
        gaps = set()
        
        for comp in components:
            if comp.styles.margin:
                margins.add(comp.styles.margin)
            if comp.styles.padding:
                paddings.add(comp.styles.padding)
            if comp.styles.gap:
                gaps.add(comp.styles.gap)
        
        return {
            'margins': list(margins)[:10],
            'paddings': list(paddings)[:10],
            'gaps': list(gaps)[:10]
        }
    
    def _extract_css_files(self) -> List[str]:
        """提取CSS文件列表"""
        css_files = []
        
        # 从snapshot中提取link标签
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        nodes = rrweb_event.get('data', {}).get('nodes', [])
        
        for node in nodes:
            if node.get('tagName', '').lower() == 'link':
                attrs = node.get('attributes', {})
                if attrs.get('rel') == 'stylesheet':
                    href = attrs.get('href', '')
                    if href:
                        css_files.append(href)
        
        return css_files
    
    def save(self, output_path: str):
        """保存提取的页面结构"""
        page_structure = self.extract()
        if page_structure:
            output_file = Path(output_path) / 'page_structure.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(page_structure.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"[PageStructure] 页面结构已保存: {output_file}")
