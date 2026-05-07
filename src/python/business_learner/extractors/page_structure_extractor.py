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
class CSSClassDefinition:
    """CSS类定义"""
    class_name: str
    selector: str
    properties: Dict[str, str] = field(default_factory=dict)
    source_file: str = ""  # 来源CSS文件
    
    def to_dict(self) -> Dict:
        return {
            'class_name': self.class_name,
            'selector': self.selector,
            'properties': self.properties,
            'source_file': self.source_file
        }


@dataclass
class ResponsiveBreakpoint:
    """响应式断点定义"""
    query: str  # 媒体查询条件，如 "(max-width: 768px)"
    min_width: Optional[int] = None
    max_width: Optional[int] = None
    rules: Dict[str, Dict[str, str]] = field(default_factory=dict)  # 该断点下的CSS规则
    
    def to_dict(self) -> Dict:
        return {
            'query': self.query,
            'min_width': self.min_width,
            'max_width': self.max_width,
            'rules': self.rules
        }


@dataclass
class PageStructure:
    """页面结构完整信息（增强版）"""
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
    external_css_rules: Dict[str, Dict[str, str]] = field(default_factory=dict)  # 外部CSS规则
    
    # CSS类定义（新增）- 按类名索引，方便查找
    css_class_definitions: Dict[str, List[CSSClassDefinition]] = field(default_factory=dict)
    
    # 组件与CSS类的映射（新增）- 记录每个组件使用了哪些CSS类
    component_css_mapping: Dict[str, List[str]] = field(default_factory=dict)
    
    # 响应式断点（增强）
    breakpoints: List[ResponsiveBreakpoint] = field(default_factory=list)
    
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
            'external_css_rules': self.external_css_rules,
            'css_class_definitions': {
                k: [v.to_dict() for v in vs] 
                for k, vs in self.css_class_definitions.items()
            },
            'component_css_mapping': self.component_css_mapping,
            'breakpoints': [b.to_dict() for b in self.breakpoints]
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
        self.resources_path = Path(resources_path) if resources_path else self._auto_detect_resources_path()
        self.raw_data = self._load_snapshot()
        self.all_css_rules = {}  # 存储所有CSS规则（内联+外部）
        
    def _auto_detect_resources_path(self) -> Optional[Path]:
        """自动检测资源路径"""
        # 从snapshot路径推断task路径
        snapshot_dir = self.snapshot_path.parent
        
        # 尝试找到network/resources目录
        possible_paths = [
            snapshot_dir.parent / 'network' / 'resources',  # dom/../network/resources
            snapshot_dir / 'network' / 'resources',  # snapshot_dir/network/resources
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        return None
        
    def _load_snapshot(self) -> Dict:
        """加载snapshot文件"""
        if not self.snapshot_path.exists():
            return {}
        with open(self.snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract(self) -> Optional[PageStructure]:
        """
        提取完整的页面结构（增强版，包含所有CSS来源）
        
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
        
        # ========== 提取所有CSS来源 ==========
        print(f"[PageStructure] 开始提取CSS...")
        
        # 1. 从<style>标签提取CSS
        inline_styles = self._extract_all_styles_from_snapshot()
        for key, css_text in inline_styles.items():
            if key.startswith('style_'):
                rules = self._parse_css_rules(css_text)
                self.all_css_rules.update(rules)
        print(f"[PageStructure] 从<style>标签提取了 {len([k for k in inline_styles.keys() if k.startswith('style_')])} 个样式块")
        
        # 2. 从外部CSS文件提取（动态加载的样式）
        external_rules = self._load_external_css_files()
        self.all_css_rules.update(external_rules)
        print(f"[PageStructure] 从外部CSS文件提取了 {len(external_rules)} 条规则")
        
        # 3. 提取组件
        components = self._extract_components()
        print(f"[PageStructure] 提取了 {len(components)} 个组件")
        
        # 4. 为组件应用CSS规则（根据class匹配）
        self._apply_css_rules_to_components(components)
        print(f"[PageStructure] 已应用CSS规则到组件")
        
        # 5. 识别布局区块
        layout_sections = self._identify_layout_sections(components)
        print(f"[PageStructure] 识别了 {len(layout_sections)} 个布局区块")
        
        # 6. 提取样式系统（包含所有CSS来源）
        color_palette = self._extract_color_palette(components)
        color_palette.extend(self._extract_colors_from_css())
        color_palette = list(set(color_palette))  # 去重
        
        typography = self._extract_typography(components)
        css_fonts = self._extract_typography_from_css()
        typography['font_sizes'] = list(set(typography['font_sizes'] + css_fonts.get('font_sizes', [])))
        typography['font_families'] = list(set(typography['font_families'] + css_fonts.get('font_families', [])))
        
        spacing_system = self._extract_spacing_system(components)
        
        # 7. 提取CSS文件列表
        css_files = self._extract_css_files()
        
        # 8. 提取CSS类定义（新增）
        css_class_definitions = self._extract_css_class_definitions(components)
        
        # 9. 构建组件与CSS类的映射（新增）
        component_css_mapping = self._build_component_css_mapping(components)
        
        # 10. 提取响应式断点（新增）
        breakpoints = self._extract_responsive_breakpoints()
        
        print(f"[PageStructure] 提取完成:")
        print(f"  - {len(color_palette)} 种颜色")
        print(f"  - {len(typography['font_sizes'])} 种字号")
        print(f"  - {len(css_class_definitions)} 个CSS类定义")
        print(f"  - {len(component_css_mapping)} 个组件CSS映射")
        print(f"  - {len(breakpoints)} 个响应式断点")
        
        return PageStructure(
            url=url,
            title=title,
            timestamp=timestamp,
            viewport=viewport,
            layout_sections=layout_sections,
            components=components,
            color_palette=color_palette[:50],  # 增加到50
            typography=typography,
            spacing_system=spacing_system,
            css_files=css_files,
            inline_styles=list(inline_styles.values()) if inline_styles else [],
            external_css_rules=self.all_css_rules,
            css_class_definitions=css_class_definitions,
            component_css_mapping=component_css_mapping,
            breakpoints=breakpoints
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
            component = self._parse_component_node(node, nodes)
            if component:
                components.append(component)
        
        # 建立父子关系并计算深度
        self._build_component_hierarchy(components, nodes)
        
        return components
    
    def _parse_component_node(self, node: Dict, all_nodes: List[Dict] = None) -> Optional[ComponentInfo]:
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
        
        # 应用默认浏览器样式
        self._apply_default_styles(styles, tag)
        
        # 提取文本内容
        text_content = self._extract_node_text(node, all_nodes)
        
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
    
    def _apply_default_styles(self, styles: StyleInfo, tag: str):
        """应用默认浏览器样式"""
        # 块级元素默认 display: block
        block_tags = {
            'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'header', 'footer', 'main', 'section', 'article', 'aside', 'nav',
            'ul', 'ol', 'li', 'table', 'form', 'fieldset'
        }
        
        # 行内元素默认 display: inline
        inline_tags = {
            'span', 'a', 'strong', 'em', 'b', 'i', 'small', 'label',
            'code', 'kbd', 'samp', 'var', 'cite', 'dfn', 'abbr'
        }
        
        # 标题默认字体大小
        heading_sizes = {
            'h1': '2em', 'h2': '1.5em', 'h3': '1.17em',
            'h4': '1em', 'h5': '0.83em', 'h6': '0.67em'
        }
        
        # 应用默认 display
        if not styles.display:
            if tag in block_tags:
                styles.display = 'block'
            elif tag in inline_tags:
                styles.display = 'inline'
            elif tag in ('img', 'video', 'canvas', 'iframe'):
                styles.display = 'inline-block'
        
        # 应用标题默认字体大小
        if not styles.font_size and tag in heading_sizes:
            styles.font_size = heading_sizes[tag]
        
        # 链接默认颜色
        if tag == 'a' and not styles.color:
            styles.color = '#0000EE'  # 默认链接蓝色
        
        # 段落默认 margin
        if tag == 'p' and not styles.margin:
            styles.margin = '1em 0'
    
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
        """提取内联样式（增强版）"""
        styles = StyleInfo()
        
        if not style_str:
            return styles
        
        # 解析样式字符串
        style_dict = {}
        for decl in style_str.split(';'):
            if ':' in decl:
                prop, val = decl.split(':', 1)
                style_dict[prop.strip().lower()] = val.strip()
        
        # 布局
        styles.display = style_dict.get('display', '')
        styles.position = style_dict.get('position', '')
        styles.width = style_dict.get('width', '')
        styles.height = style_dict.get('height', '')
        styles.margin = style_dict.get('margin', style_dict.get('margin-top', ''))
        styles.padding = style_dict.get('padding', style_dict.get('padding-top', ''))
        
        # Flex/Grid
        styles.flex_direction = style_dict.get('flex-direction', '')
        styles.justify_content = style_dict.get('justify-content', '')
        styles.align_items = style_dict.get('align-items', '')
        styles.gap = style_dict.get('gap', '')
        styles.grid_template = style_dict.get('grid-template-columns', style_dict.get('grid-template-rows', ''))
        
        # 外观 - 颜色
        styles.background_color = style_dict.get('background-color', style_dict.get('background', ''))
        styles.color = style_dict.get('color', '')
        
        # 外观 - 字体
        styles.font_size = style_dict.get('font-size', '')
        styles.font_family = style_dict.get('font-family', '')
        font_weight = style_dict.get('font-weight', '')
        font_style = style_dict.get('font-style', '')
        line_height = style_dict.get('line-height', '')
        text_align = style_dict.get('text-align', '')
        
        # 外观 - 边框
        styles.border = style_dict.get('border', '')
        styles.border_radius = style_dict.get('border-radius', '')
        border_color = style_dict.get('border-color', '')
        border_width = style_dict.get('border-width', '')
        border_style = style_dict.get('border-style', '')
        
        # 效果
        styles.box_shadow = style_dict.get('box-shadow', '')
        opacity = style_dict.get('opacity', '')
        
        # 其他
        styles.z_index = style_dict.get('z-index', '')
        styles.overflow = style_dict.get('overflow', '')
        
        return styles
    
    def _extract_all_styles_from_snapshot(self) -> Dict[str, str]:
        """从snapshot中提取所有CSS样式（包括<style>标签）"""
        all_styles = {}
        
        rrweb_event = self.raw_data.get('rrwebEvent', {})
        nodes = rrweb_event.get('data', {}).get('nodes', [])
        
        for node in nodes:
            if node.get('type') == 2:  # 元素节点
                tag = node.get('tagName', '').lower()
                
                # 提取<style>标签内容
                if tag == 'style':
                    style_content = self._extract_style_tag_content(node, nodes)
                    if style_content:
                        all_styles[f'style_{node.get("id")}'] = style_content
                
                # 提取元素的class属性
                attrs = node.get('attributes', {})
                class_attr = attrs.get('class', '')
                if class_attr:
                    all_styles[f'class_{node.get("id")}'] = class_attr
        
        return all_styles
    
    def _load_external_css_files(self) -> Dict[str, Dict[str, str]]:
        """
        加载外部CSS文件（动态加载的样式）
        
        Returns:
            CSS规则字典 {selector: {property: value}}
        """
        all_rules = {}
        
        if not self.resources_path or not self.resources_path.exists():
            print(f"[PageStructure] 未找到资源路径: {self.resources_path}")
            return all_rules
        
        # 获取所有CSS文件
        css_files = list(self.resources_path.glob('*.css'))
        css_files.extend(self.resources_path.glob('*.css.css'))
        
        print(f"[PageStructure] 找到 {len(css_files)} 个CSS文件")
        
        loaded_count = 0
        for css_file in css_files:
            try:
                with open(css_file, 'r', encoding='utf-8', errors='ignore') as f:
                    css_content = f.read()
                
                if css_content.strip():
                    rules = self._parse_css_rules(css_content)
                    all_rules.update(rules)
                    loaded_count += 1
                    
                    if loaded_count <= 3:
                        print(f"[PageStructure]   加载: {css_file.name} ({len(rules)} 条规则)")
            except Exception as e:
                print(f"[PageStructure]   加载失败: {css_file.name} - {e}")
        
        print(f"[PageStructure] 成功加载 {loaded_count} 个CSS文件")
        return all_rules
    
    def _extract_css_class_definitions(self, components: List[ComponentInfo]) -> Dict[str, List[CSSClassDefinition]]:
        """
        提取CSS类定义，按类名组织
        
        Returns:
            {class_name: [CSSClassDefinition, ...]}
        """
        class_definitions: Dict[str, List[CSSClassDefinition]] = {}
        
        # 收集所有组件使用的class
        all_used_classes = set()
        for comp in components:
            all_used_classes.update(comp.class_names)
        
        print(f"[PageStructure] 组件使用了 {len(all_used_classes)} 个不同的class")
        
        # 为每个class找到对应的CSS规则
        for selector, properties in self.all_css_rules.items():
            # 跳过伪类和复杂选择器
            if ':' in selector or '[' in selector or '>' in selector or '+' in selector:
                continue
            
            # 提取class名
            class_matches = re.findall(r'\.([a-zA-Z_-][a-zA-Z0-9_-]*)', selector)
            
            for class_name in class_matches:
                if class_name not in class_definitions:
                    class_definitions[class_name] = []
                
                # 创建类定义
                class_def = CSSClassDefinition(
                    class_name=class_name,
                    selector=selector,
                    properties=properties.copy(),
                    source_file=""  # 可以后续添加来源追踪
                )
                class_definitions[class_name].append(class_def)
        
        # 只保留组件实际使用的class定义
        used_class_definitions = {
            k: v for k, v in class_definitions.items() 
            if k in all_used_classes
        }
        
        print(f"[PageStructure] 提取了 {len(used_class_definitions)} 个组件使用的class定义")
        return used_class_definitions
    
    def _build_component_css_mapping(self, components: List[ComponentInfo]) -> Dict[str, List[str]]:
        """
        构建组件与CSS类的映射关系
        
        Returns:
            {component_id: [class_name, ...]}
        """
        mapping = {}
        
        for comp in components:
            if comp.class_names:
                # 记录该组件使用的所有class
                mapping[comp.id] = comp.class_names.copy()
        
        print(f"[PageStructure] 建立了 {len(mapping)} 个组件的CSS类映射")
        return mapping
    
    def _extract_responsive_breakpoints(self) -> List[ResponsiveBreakpoint]:
        """
        提取响应式断点（@media查询）
        
        Returns:
            ResponsiveBreakpoint列表
        """
        breakpoints = []
        
        if not self.resources_path or not self.resources_path.exists():
            return breakpoints
        
        # 从所有CSS文件中提取@media规则
        css_files = list(self.resources_path.glob('*.css'))
        css_files.extend(self.resources_path.glob('*.css.css'))
        
        for css_file in css_files:
            try:
                with open(css_file, 'r', encoding='utf-8', errors='ignore') as f:
                    css_content = f.read()
                
                # 匹配@media查询
                media_pattern = r'@media\s+([^\{]+)\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
                media_matches = re.findall(media_pattern, css_content, re.DOTALL)
                
                for query, content in media_matches:
                    query = query.strip()
                    
                    # 解析min-width和max-width
                    min_width = None
                    max_width = None
                    
                    min_match = re.search(r'min-width:\s*(\d+)px', query)
                    if min_match:
                        min_width = int(min_match.group(1))
                    
                    max_match = re.search(r'max-width:\s*(\d+)px', query)
                    if max_match:
                        max_width = int(max_match.group(1))
                    
                    # 解析该断点下的规则
                    rules = self._parse_css_rules(content)
                    
                    if rules:
                        breakpoint = ResponsiveBreakpoint(
                            query=query,
                            min_width=min_width,
                            max_width=max_width,
                            rules=rules
                        )
                        breakpoints.append(breakpoint)
                        
            except Exception as e:
                continue
        
        # 去重并按宽度排序
        seen_queries = set()
        unique_breakpoints = []
        for bp in breakpoints:
            if bp.query not in seen_queries:
                seen_queries.add(bp.query)
                unique_breakpoints.append(bp)
        
        unique_breakpoints.sort(key=lambda x: x.max_width or 99999)
        
        print(f"[PageStructure] 提取了 {len(unique_breakpoints)} 个响应式断点")
        return unique_breakpoints
    
    def _extract_style_tag_content(self, style_node: Dict, all_nodes: List[Dict]) -> str:
        """提取<style>标签的CSS内容"""
        child_ids = style_node.get('childNodes', [])
        css_content = []
        
        node_map = {node.get('id'): node for node in all_nodes if node.get('id') is not None}
        
        for child_id in child_ids:
            child = node_map.get(child_id)
            if child and child.get('type') == 3:  # 文本节点
                text = child.get('textContent', '')
                if text.strip():
                    css_content.append(text)
        
        return '\n'.join(css_content)
    
    def _parse_css_rules(self, css_text: str) -> Dict[str, Dict[str, str]]:
        """解析CSS规则为字典"""
        rules = {}
        
        if not css_text:
            return rules
        
        # 简单的CSS解析（移除注释，提取规则）
        css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
        
        # 匹配选择器和声明块
        pattern = r'([^{]+)\{([^}]+)\}'
        matches = re.findall(pattern, css_text)
        
        for selector, declarations in matches:
            selector = selector.strip()
            if not selector:
                continue
            
            props = {}
            for decl in declarations.split(';'):
                if ':' in decl:
                    prop, val = decl.split(':', 1)
                    props[prop.strip()] = val.strip()
            
            if props:
                rules[selector] = props
        
        return rules
    
    def _extract_node_text(self, node: Dict, all_nodes: List[Dict] = None) -> str:
        """提取节点文本内容（递归查找所有子文本节点 + 属性文本）"""
        texts = []
        
        # 构建节点映射（如果提供了all_nodes）
        node_map = {}
        if all_nodes:
            node_map = {n.get('id'): n for n in all_nodes if n.get('id') is not None}
        
        def extract_text_recursive(current_node: Dict, depth: int = 0):
            """递归提取文本"""
            if depth > 50:  # 防止无限递归
                return
            
            node_type = current_node.get('type')
            
            # 如果是文本节点(type=3)，直接提取textContent
            if node_type == 3:
                text = current_node.get('textContent', '')
                if text and text.strip():
                    texts.append(text.strip())
                return
            
            # 如果是元素节点(type=2)，递归处理子节点
            if node_type == 2:
                # 提取属性文本（alt, placeholder, title, value）
                attributes = current_node.get('attributes', {})
                
                # 图片alt文本
                alt_text = attributes.get('alt', '').strip()
                if alt_text:
                    texts.append(f"[图片: {alt_text}]")
                
                # placeholder文本
                placeholder = attributes.get('placeholder', '').strip()
                if placeholder:
                    texts.append(f"[提示: {placeholder}]")
                
                # title文本
                title = attributes.get('title', '').strip()
                if title:
                    texts.append(f"[标题: {title}]")
                
                # value文本（对于input）
                if current_node.get('tagName', '').lower() == 'input':
                    value = attributes.get('value', '').strip()
                    if value:
                        texts.append(f"[值: {value}]")
                
                # 递归处理子节点
                child_ids = current_node.get('childNodes', [])
                for child_id in child_ids:
                    child_node = node_map.get(child_id)
                    if child_node:
                        extract_text_recursive(child_node, depth + 1)
        
        # 开始递归提取
        extract_text_recursive(node)
        
        # 合并文本并清理
        full_text = ' '.join(texts)
        # 清理多余空白
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        return full_text
    
    def _is_interactive_element(self, tag: str, attributes: Dict) -> bool:
        """判断是否为交互式元素（增强版）"""
        # 基础交互标签
        interactive_tags = {
            'button', 'a', 'input', 'textarea', 'select', 'option',
            'form', 'label', 'fieldset', 'legend',
            'details', 'summary', 'dialog'
        }
        if tag in interactive_tags:
            return True
        
        # 检查input类型
        if tag == 'input':
            input_type = attributes.get('type', 'text').lower()
            interactive_input_types = {
                'text', 'password', 'email', 'tel', 'url', 'search',
                'number', 'date', 'datetime-local', 'time', 'month', 'week',
                'checkbox', 'radio', 'file', 'range', 'color',
                'submit', 'button', 'reset', 'image'
            }
            if input_type in interactive_input_types:
                return True
        
        # HTML5 交互属性
        interactive_attrs = {
            'contenteditable',  # 可编辑内容
            'draggable',        # 可拖拽
            'tabindex',         # 可tab导航
        }
        for attr in interactive_attrs:
            if attr in attributes:
                return True
        
        # ARIA 交互角色
        aria_role = attributes.get('role', '').lower()
        interactive_roles = {
            'button', 'link', 'checkbox', 'radio', 'textbox', 'combobox',
            'listbox', 'menu', 'menubar', 'menuitem', 'menuitemcheckbox',
            'menuitemradio', 'option', 'scrollbar', 'searchbox', 'slider',
            'spinbutton', 'switch', 'tab', 'tabpanel', 'tooltip', 'tree',
            'treegrid', 'treeitem'
        }
        if aria_role in interactive_roles:
            return True
        
        # 检查是否有交互事件
        interactive_events = [
            'onclick', 'ondblclick', 'onmousedown', 'onmouseup', 'onmousemove',
            'onmouseenter', 'onmouseleave', 'onmouseover', 'onmouseout',
            'onkeydown', 'onkeyup', 'onkeypress',
            'onfocus', 'onblur', 'onchange', 'oninput', 'onselect',
            'onsubmit', 'onreset',
            'ondrag', 'ondrop', 'ondragstart', 'ondragend',
            'ontouchstart', 'ontouchend', 'ontouchmove'
        ]
        for event in interactive_events:
            if event in attributes:
                return True
        
        # 检查是否有常见的交互类名
        class_attr = attributes.get('class', '').lower()
        interactive_class_patterns = [
            'btn', 'button', 'click', 'link', 'nav', 'tab', 'menu',
            'dropdown', 'modal', 'popup', 'tooltip', 'accordion',
            'carousel', 'slider', 'switch', 'toggle'
        ]
        for pattern in interactive_class_patterns:
            if pattern in class_attr:
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
        """建立组件层级关系并计算深度"""
        node_map = {node.get('id'): node for node in nodes if node.get('id') is not None}
        comp_map = {comp.id: comp for comp in components}
        
        # 构建组件ID集合（只包含实际提取的组件）
        component_node_ids = {int(comp.id.replace('comp_', '')) for comp in components}
        
        # 构建父节点映射（根据childNodes反向推断，只考虑组件节点）
        parent_map = {}  # {child_id: parent_id}
        for node in nodes:
            node_id = node.get('id')
            # 只处理元素节点(type=2)且是组件的节点
            if node.get('type') != 2 or node_id not in component_node_ids:
                continue
            child_ids = node.get('childNodes', [])
            for child_id in child_ids:
                if child_id in component_node_ids:  # 只记录组件子节点
                    parent_map[child_id] = node_id
        
        # 第一遍：建立父子关系
        for comp in components:
            node_id = int(comp.id.replace('comp_', ''))
            node = node_map.get(node_id)
            
            if node:
                # 父节点 - 从parent_map中查找（只找组件父节点）
                parent_id = parent_map.get(node_id)
                if parent_id is not None:
                    comp.parent_id = f"comp_{parent_id}"
                
                # 子节点 - 只包含组件子节点
                child_ids = node.get('childNodes', [])
                comp.children_ids = [f"comp_{cid}" for cid in child_ids if cid in component_node_ids]
        
        # 第二遍：计算深度（从根节点开始递归）
        def calculate_depth(comp_id: str, visited: set = None) -> int:
            """递归计算组件深度"""
            if visited is None:
                visited = set()
            
            if comp_id in visited:
                return 0  # 防止循环引用
            
            visited.add(comp_id)
            comp = comp_map.get(comp_id)
            
            if not comp:
                return 0
            
            if comp.parent_id is None:
                return 0  # 根节点深度为0
            
            parent = comp_map.get(comp.parent_id)
            if not parent:
                return 0
            
            return calculate_depth(comp.parent_id, visited) + 1
        
        # 为每个组件计算深度
        for comp in components:
            comp.depth = calculate_depth(comp.id)
        
        # 第三遍：传播继承样式
        self._propagate_inherited_styles(components)
    
    def _propagate_inherited_styles(self, components: List[ComponentInfo]):
        """传播继承样式（字体、颜色等）"""
        comp_map = {comp.id: comp for comp in components}
        
        # 可继承的CSS属性
        inheritable_props = {
            'color', 'font-family', 'font-size', 'font-weight', 'font-style',
            'line-height', 'text-align', 'text-decoration', 'text-transform',
            'letter-spacing', 'word-spacing', 'white-space'
        }
        
        # 按深度排序，从父到子处理
        sorted_components = sorted(components, key=lambda c: c.depth)
        
        for comp in sorted_components:
            if not comp.parent_id:
                continue
            
            parent = comp_map.get(comp.parent_id)
            if not parent:
                continue
            
            # 继承字体颜色
            if not comp.styles.color and parent.styles.color:
                comp.styles.color = parent.styles.color
            
            # 继承字体族
            if not comp.styles.font_family and parent.styles.font_family:
                comp.styles.font_family = parent.styles.font_family
            
            # 继承字体大小
            if not comp.styles.font_size and parent.styles.font_size:
                comp.styles.font_size = parent.styles.font_size
            
            # 继承其他计算样式
            for prop in inheritable_props:
                if prop in parent.computed_styles:
                    if prop not in comp.computed_styles:
                        comp.computed_styles[prop] = parent.computed_styles[prop]
    
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
    
    def _apply_css_rules_to_components(self, components: List[ComponentInfo]):
        """根据class名将CSS规则应用到组件（支持复杂选择器）"""
        applied_count = 0
        
        # 构建组件class索引，用于快速查找
        component_class_index = {}
        for comp in components:
            for class_name in comp.class_names:
                if class_name not in component_class_index:
                    component_class_index[class_name] = []
                component_class_index[class_name].append(comp)
        
        # 遍历所有CSS规则，尝试匹配组件
        for selector, rules in self.all_css_rules.items():
            # 跳过伪类和媒体查询
            if ':' in selector or '@media' in selector or '@keyframes' in selector:
                continue
            
            # 提取选择器中的class名
            class_matches = re.findall(r'\.([a-zA-Z_-][a-zA-Z0-9_-]*)', selector)
            
            for class_name in class_matches:
                if class_name in component_class_index:
                    for comp in component_class_index[class_name]:
                        self._apply_rules_to_component(comp, rules)
                        applied_count += 1
        
        print(f"[PageStructure] 应用了 {applied_count} 次CSS规则到组件")
    
    def _apply_rules_to_component(self, component: ComponentInfo, rules: Dict[str, str]):
        """将CSS规则应用到组件（完整版）"""
        s = component.styles
        
        # ========== 颜色 ==========
        if 'color' in rules and not s.color:
            s.color = rules['color']
        if 'background-color' in rules and not s.background_color:
            s.background_color = rules['background-color']
        if 'background' in rules and not s.background_color:
            # 从background简写中提取颜色
            bg = rules['background']
            color_match = re.search(r'(#[a-fA-F0-9]{3,8}|rgb\([^)]+\)|rgba\([^)]+\))', bg)
            if color_match:
                s.background_color = color_match.group(1)
        if 'border-color' in rules and not s.border:
            s.border = f"1px solid {rules['border-color']}"
        
        # ========== 字体 ==========
        if 'font-size' in rules and not s.font_size:
            s.font_size = rules['font-size']
        if 'font-family' in rules and not s.font_family:
            s.font_family = rules['font-family']
        # 存储到computed_styles中以保留更多字体信息
        if 'font-weight' in rules:
            component.computed_styles['font-weight'] = rules['font-weight']
        if 'line-height' in rules:
            component.computed_styles['line-height'] = rules['line-height']
        if 'text-align' in rules:
            component.computed_styles['text-align'] = rules['text-align']
        
        # ========== 尺寸 ==========
        if 'width' in rules and not s.width:
            s.width = rules['width']
        if 'height' in rules and not s.height:
            s.height = rules['height']
        if 'min-width' in rules:
            component.computed_styles['min-width'] = rules['min-width']
        if 'min-height' in rules:
            component.computed_styles['min-height'] = rules['min-height']
        if 'max-width' in rules:
            component.computed_styles['max-width'] = rules['max-width']
        if 'max-height' in rules:
            component.computed_styles['max-height'] = rules['max-height']
        
        # ========== 间距（详细分解）==========
        # margin
        if 'margin' in rules and not s.margin:
            s.margin = rules['margin']
        if 'margin-top' in rules:
            component.computed_styles['margin-top'] = rules['margin-top']
        if 'margin-right' in rules:
            component.computed_styles['margin-right'] = rules['margin-right']
        if 'margin-bottom' in rules:
            component.computed_styles['margin-bottom'] = rules['margin-bottom']
        if 'margin-left' in rules:
            component.computed_styles['margin-left'] = rules['margin-left']
        
        # padding
        if 'padding' in rules and not s.padding:
            s.padding = rules['padding']
        if 'padding-top' in rules:
            component.computed_styles['padding-top'] = rules['padding-top']
        if 'padding-right' in rules:
            component.computed_styles['padding-right'] = rules['padding-right']
        if 'padding-bottom' in rules:
            component.computed_styles['padding-bottom'] = rules['padding-bottom']
        if 'padding-left' in rules:
            component.computed_styles['padding-left'] = rules['padding-left']
        
        # ========== 布局 ==========
        if 'display' in rules and not s.display:
            s.display = rules['display']
        if 'position' in rules and not s.position:
            s.position = rules['position']
        if 'top' in rules:
            component.computed_styles['top'] = rules['top']
        if 'right' in rules:
            component.computed_styles['right'] = rules['right']
        if 'bottom' in rules:
            component.computed_styles['bottom'] = rules['bottom']
        if 'left' in rules:
            component.computed_styles['left'] = rules['left']
        if 'z-index' in rules:
            s.z_index = rules['z-index']
        if 'overflow' in rules:
            s.overflow = rules['overflow']
        
        # Flex
        if 'flex-direction' in rules:
            s.flex_direction = rules['flex-direction']
        if 'justify-content' in rules:
            s.justify_content = rules['justify-content']
        if 'align-items' in rules:
            s.align_items = rules['align-items']
        if 'align-content' in rules:
            component.computed_styles['align-content'] = rules['align-content']
        if 'flex-wrap' in rules:
            component.computed_styles['flex-wrap'] = rules['flex-wrap']
        if 'gap' in rules:
            s.gap = rules['gap']
        if 'row-gap' in rules:
            component.computed_styles['row-gap'] = rules['row-gap']
        if 'column-gap' in rules:
            component.computed_styles['column-gap'] = rules['column-gap']
        
        # Grid
        if 'grid-template-columns' in rules:
            s.grid_template = rules['grid-template-columns']
        if 'grid-template-rows' in rules:
            if s.grid_template:
                s.grid_template += f" / {rules['grid-template-rows']}"
            else:
                s.grid_template = rules['grid-template-rows']
        
        # ========== 边框（详细）==========
        if 'border' in rules and not s.border:
            s.border = rules['border']
        if 'border-top' in rules:
            component.computed_styles['border-top'] = rules['border-top']
        if 'border-right' in rules:
            component.computed_styles['border-right'] = rules['border-right']
        if 'border-bottom' in rules:
            component.computed_styles['border-bottom'] = rules['border-bottom']
        if 'border-left' in rules:
            component.computed_styles['border-left'] = rules['border-left']
        if 'border-radius' in rules and not s.border_radius:
            s.border_radius = rules['border-radius']
        if 'border-width' in rules:
            component.computed_styles['border-width'] = rules['border-width']
        if 'border-style' in rules:
            component.computed_styles['border-style'] = rules['border-style']
        
        # ========== 效果 ==========
        if 'box-shadow' in rules and not s.box_shadow:
            s.box_shadow = rules['box-shadow']
        if 'opacity' in rules:
            component.computed_styles['opacity'] = rules['opacity']
        if 'transform' in rules:
            component.computed_styles['transform'] = rules['transform']
        if 'transition' in rules:
            component.computed_styles['transition'] = rules['transition']
        if 'cursor' in rules:
            component.computed_styles['cursor'] = rules['cursor']
    
    def _extract_colors_from_css(self) -> List[str]:
        """从所有CSS规则中提取颜色"""
        colors = set()
        color_pattern = r'(#[a-fA-F0-9]{3,8}|rgb\([^)]+\)|rgba\([^)]+\))'
        
        for selector, rules in self.all_css_rules.items():
            for prop, value in rules.items():
                if prop in ['color', 'background-color', 'background', 'border-color', 'border']:
                    matches = re.findall(color_pattern, value)
                    colors.update(matches)
        
        return list(colors)
    
    def _extract_typography_from_css(self) -> Dict[str, List[str]]:
        """从所有CSS规则中提取字体信息"""
        font_sizes = set()
        font_families = set()
        
        for selector, rules in self.all_css_rules.items():
            if 'font-size' in rules:
                font_sizes.add(rules['font-size'])
            if 'font-family' in rules:
                # 清理字体名称
                families = rules['font-family'].split(',')
                for fam in families:
                    fam = fam.strip().strip('"\'')
                    if fam:
                        font_families.add(fam)
        
        return {
            'font_sizes': list(font_sizes)[:20],
            'font_families': list(font_families)[:15]
        }
    
    def save(self, output_path: str):
        """保存提取的页面结构"""
        page_structure = self.extract()
        if page_structure:
            output_file = Path(output_path) / 'page_structure.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(page_structure.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"[PageStructure] 页面结构已保存: {output_file}")
