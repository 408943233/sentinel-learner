"""
统一Memory适配器
支持本地模式和服务器模式
与OpenClaw Memory Skill集成
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from ..utils.models import TaskUnderstanding, PageUnderstanding, APIEntity
from ..utils.task_metadata import TaskMetadata, TaskMetadataManager


class UnifiedMemoryAdapter:
    """
    统一内存适配器
    
    支持两种模式：
    - local: 本地开发，使用本地memory目录
    - server: 服务器部署，使用共享memory目录
    
    路径配置（可通过环境变量覆盖）：
    - SENTINEL_WORKSPACE: 主图谱存储目录 (默认: ~/.openclaw/workspace)
    - OPENCLAW_SKILL_PATH: skill脚本目录 (默认: ~/.openclaw/extensions/openclaw-memory-skill)
    """
    
    def __init__(self, mode: str = "local", server_memory_path: Optional[str] = None):
        """
        初始化适配器
        
        Args:
            mode: 运行模式 ('local' 或 'server')
            server_memory_path: 服务器memory路径（server模式必填）
        """
        self.mode = mode
        
        # 读取环境变量或使用默认值
        self.workspace_base = Path(
            os.environ.get("SENTINEL_WORKSPACE", Path.home() / ".openclaw" / "workspace")
        )
        self.script_base = Path(
            os.environ.get("OPENCLAW_SKILL_PATH", Path.home() / ".openclaw" / "extensions" / "openclaw-memory-skill")
        )
        
        if mode == "server":
            if not server_memory_path:
                raise ValueError("Server模式需要提供server_memory_path")
            self.memory_base_path = Path(server_memory_path)
        else:
            # 本地模式：写入主图谱（workspace）
            self.memory_base_path = self.workspace_base
        
        # 数据文件路径（在workspace中）
        self.graph_path = self.memory_base_path / "memory" / "ontology" / "graph.jsonl"
        self.schema_path = self.memory_base_path / "memory" / "ontology" / "schema.yaml"
        
        # 脚本路径（在script_base中）
        self.script_path = self.script_base / "scripts" / "ontology_optimized.py"
        
        # 确保数据目录存在
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _run_skill_command(self, *args) -> tuple[bool, str]:
        """
        运行skill命令
        
        使用相对路径和正确的工作目录，避免安全路径检查问题
        注意：子命令必须在前，--graph/--schema 参数跟在后面
        
        Returns:
            (成功状态, 输出信息)
        """
        # 构建命令：子命令在前，--graph 跟在后面
        # 工作目录设为 workspace_base，这样相对路径才能正确解析
        cmd = ["python3", str(self.script_path)] + list(args)
        
        # 只在需要时添加 --graph 参数（跟在子命令后）
        if "--graph" not in args:
            cmd += ["--graph", "memory/ontology/graph.jsonl"]
        
        # --schema 只在 validate 命令中使用
        if "--schema" not in args and "validate" in args:
            cmd += ["--schema", "memory/ontology/schema.yaml"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.memory_base_path),  # 设置工作目录为数据目录
                env=subprocess.os.environ  # 继承当前环境变量
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except Exception as e:
            return False, str(e)
    
    def store_task_knowledge(self, task_result: TaskUnderstanding, 
                            metadata_manager: TaskMetadataManager):
        """
        存储Task知识到知识图谱
        
        Args:
            task_result: 任务理解结果
            metadata_manager: 元数据管理器
        """
        print(f"\n[UnifiedMemoryAdapter] 存储Task知识 (模式: {self.mode})...")
        
        # 1. 获取或创建目标系统实体
        metadata = metadata_manager.load_metadata()
        system_entity = self._get_or_create_system(metadata)
        
        # 2. 创建Task记录实体
        task_entity = self._create_task_entity(metadata, task_result)
        
        # 3. 建立系统-Task关系
        self._create_relation(
            from_id=system_entity["id"],
            rel_type="has_recording",
            to_id=task_entity["id"],
            properties={"recorded_at": metadata.recorder.recorded_at}
        )
        
        # 4. 存储页面知识（包含详细结构）
        for page in task_result.pages:
            page_entity = self._store_page_knowledge(page, task_entity["id"], system_entity["id"])
            
            # 4.1 存储页面详细结构（组件、布局、样式等）
            if page_entity:
                self._store_page_structure_detailed(
                    page, 
                    page_entity["id"], 
                    metadata_manager.task_path
                )
        
        # 5. 存储业务实体
        for entity in task_result.entities:
            self._store_business_entity(entity, system_entity["id"])
        
        # 6. 解决冲突
        self._resolve_system_conflicts(system_entity["id"])
        
        print(f"[UnifiedMemoryAdapter] Task知识存储完成")
    
    def _get_or_create_system(self, metadata) -> Dict:
        """获取或创建系统实体"""
        system_name = metadata.target_system.name
        system_domain = metadata.target_system.domain
        
        # 查询是否已存在
        existing = self._query_entity("System", {"name": system_name})
        
        if existing:
            print(f"  系统已存在: {system_name}")
            return existing[0]
        
        # 创建新系统实体
        props = json.dumps({
            "name": system_name,
            "domain": system_domain,
            "system_type": metadata.target_system.system_type,
            "description": f"目标系统: {system_name}"
        })
        
        success, output = self._run_skill_command(
            "create",
            "--type", "System",
            "--props", props,
            "--authority", "reference"  # 系统信息用reference等级
        )
        
        if success:
            print(f"  创建系统实体: {system_name}")
            try:
                return json.loads(output)
            except:
                return {"id": f"sys_{system_domain}", "type": "System"}
        else:
            print(f"  创建系统失败: {output}")
            return {"id": f"sys_{system_domain}", "type": "System"}
    
    def _create_task_entity(self, metadata, task_result) -> Dict:
        """创建Task实体"""
        props = json.dumps({
            "task_id": metadata.task_id,
            "name": metadata.task_name,
            "description": metadata.task_description,
            "recorded_by": metadata.recorder.user_id,
            "operator_name": metadata.recorder.operator_name,  # 操作人姓名（用于冲突解决）
            "recorded_at": metadata.recorder.recorded_at,
            "target_system": metadata.target_system.name,
            "pages_count": len(task_result.pages),
            "entities_count": len(task_result.entities)
        })
        
        # 使用 operator_name 作为 source（如果存在），否则使用默认值
        source = metadata.recorder.operator_name if metadata.recorder.operator_name else "sentinel-learner"
        
        success, output = self._run_skill_command(
            "create",
            "--type", "TaskRecording",
            "--props", props,
            "--source", source,  # 记录操作人作为数据来源
            "--authority", "observation"  # Task数据用observation等级
        )
        
        if success:
            print(f"  创建Task实体: {metadata.task_id}")
            try:
                return json.loads(output)
            except:
                return {"id": metadata.task_id, "type": "TaskRecording"}
        else:
            print(f"  创建Task失败: {output}")
            return {"id": metadata.task_id, "type": "TaskRecording"}
    
    def _store_page_knowledge(self, page: PageUnderstanding,
                             task_id: str, system_id: str) -> Optional[Dict]:
        """存储页面知识"""
        # 处理不同类型的confidence
        if hasattr(page.overall_confidence, 'value'):
            confidence_value = page.overall_confidence.value
        elif hasattr(page.overall_confidence, 'overall_confidence'):
            confidence_value = str(page.overall_confidence.overall_confidence)
        else:
            confidence_value = str(page.overall_confidence)

        page_props = json.dumps({
            "url": page.page_info.url,
            "title": page.page_info.title,
            "page_type": page.page_info.page_type,
            "domain": page.page_info.business_domain,
            "confidence": confidence_value
        })

        success, output = self._run_skill_command(
            "create",
            "--type", "WebPage",
            "--props", page_props,
            "--authority", "observation"
        )

        if success:
            try:
                page_entity = json.loads(output)
                # 建立关系：Task --recorded--> Page
                self._create_relation(
                    from_id=task_id,
                    rel_type="recorded",
                    to_id=page_entity["id"]
                )
                # 建立关系：System --has_page--> Page
                self._create_relation(
                    from_id=system_id,
                    rel_type="has_page",
                    to_id=page_entity["id"]
                )
                return page_entity
            except:
                pass
        return None

    def _store_page_structure_detailed(self, page: PageUnderstanding,
                                       page_entity_id: str, task_path: Path):
        """
        存储页面详细结构（组件、布局、样式等）

        读取 page_structure.json 并存储：
        1. Component 实体
        2. LayoutSection 实体
        3. StyleSystem 实体（CSS规则聚合）
        4. DesignToken 实体（颜色/字号/字体）
        """
        # 查找 page_structure.json
        structure_file = task_path / "analysis" / "page_structure.json"

        if not structure_file.exists():
            print(f"    ⚠️ 未找到页面结构文件: {structure_file}")
            return

        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
        except Exception as e:
            print(f"    ⚠️ 读取页面结构文件失败: {e}")
            return

        print(f"    📄 存储页面详细结构...")

        # 1. 存储组件
        components = structure_data.get('components', [])
        component_id_map = {}
        if components:
            print(f"      - 存储 {len(components)} 个组件...")
            component_id_map = self._store_components(components, page_entity_id)

        # 2. 存储布局区块
        layout_sections = structure_data.get('layout_sections', [])
        if layout_sections:
            print(f"      - 存储 {len(layout_sections)} 个布局区块...")
            self._store_layout_sections(layout_sections, page_entity_id, component_id_map)

        # 3. 存储样式系统
        css_rules = structure_data.get('external_css_rules', {})
        if css_rules:
            print(f"      - 存储 {len(css_rules)} 条CSS规则...")
            self._store_style_system(css_rules, page_entity_id)

        # 4. 存储设计令牌（颜色/字号/字体）
        color_palette = structure_data.get('color_palette', [])
        typography = structure_data.get('typography', {})
        if color_palette or typography:
            print(f"      - 存储设计令牌...")
            self._store_design_tokens(color_palette, typography, page_entity_id)

        # 5. 存储响应式断点
        self._store_breakpoints(structure_data, page_entity_id)

        # 6. 存储资源文件
        self._store_resources(task_path, page_entity_id)

        # 7. 存储视频关键帧
        self._store_video_keyframes(task_path, page_entity_id)

        # 8. 存储DOM快照
        self._store_dom_snapshots(task_path, page_entity_id)

    def _store_components(self, components: List[Dict], page_entity_id: str) -> Dict[str, str]:
        """
        存储组件实体 - 保留所有原始属性

        Returns:
            组件ID到实体ID的映射
        """
        component_id_map = {}

        for comp in components:
            try:
                # 保留所有原始属性，只进行必要的序列化和截断
                comp_props = self._serialize_component(comp)

                success, output = self._run_skill_command(
                    "create",
                    "--type", "Component",
                    "--props", json.dumps(comp_props),
                    "--authority", "observation"
                )

                if success:
                    comp_entity = json.loads(output)
                    comp_id = comp.get('id', '')
                    if comp_id:
                        component_id_map[comp_id] = comp_entity["id"]

                    # 建立关系：Page --contains--> Component
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="contains",
                        to_id=comp_entity["id"]
                    )
            except Exception as e:
                print(f"        ⚠️ 存储组件失败: {e}")
                continue

        return component_id_map

    def _serialize_component(self, comp: Dict) -> Dict:
        """序列化组件，保留所有属性"""
        props = {}

        # 基础属性
        props['id'] = comp.get('id', '')
        props['tag'] = comp.get('tag', '')
        props['type'] = comp.get('type', 'unknown')
        props['name'] = comp.get('name', '')[:200]
        props['text_content'] = comp.get('text_content', '')[:500]
        props['is_interactive'] = comp.get('is_interactive', False)
        props['depth'] = comp.get('depth', 0)

        # 类名（保留完整列表）
        class_names = comp.get('class_names', [])
        if class_names:
            props['class_names'] = json.dumps(class_names[:50])  # 最多50个类名

        # 属性（完整保留）
        attributes = comp.get('attributes', {})
        if attributes:
            # 截断过长的属性值
            truncated_attrs = {}
            for k, v in attributes.items():
                if isinstance(v, str):
                    truncated_attrs[k] = v[:200] if len(v) > 200 else v
                else:
                    truncated_attrs[k] = str(v)[:200]
            props['attributes'] = json.dumps(truncated_attrs, ensure_ascii=False)

        # 内联样式（完整保留）
        styles = comp.get('styles', {})
        if styles:
            props['styles'] = json.dumps(styles, ensure_ascii=False)

        # 计算样式
        computed_styles = comp.get('computed_styles', {})
        if computed_styles:
            props['computed_styles'] = json.dumps(computed_styles, ensure_ascii=False)

        # Bounding box（完整保留）
        bbox = comp.get('bounding_box', {})
        if bbox:
            props['bounding_box'] = json.dumps(bbox)
            props['x'] = bbox.get('x', 0)
            props['y'] = bbox.get('y', 0)
            props['width'] = bbox.get('width', 0)
            props['height'] = bbox.get('height', 0)

        # 层级关系
        children_ids = comp.get('children_ids', [])
        if children_ids:
            props['children_ids'] = json.dumps(children_ids[:100])  # 最多100个子组件

        parent_id = comp.get('parent_id', '')
        if parent_id:
            props['parent_id'] = parent_id

        # 事件处理器
        event_handlers = comp.get('event_handlers', [])
        if event_handlers:
            props['event_handlers'] = json.dumps(event_handlers[:20])

        return props

    def _store_layout_sections(self, sections: List[Dict], page_entity_id: str, component_id_map: Dict[str, str]):
        """
        存储布局区块实体 - 保留所有原始属性

        Args:
            sections: 布局区块列表
            page_entity_id: 页面实体ID
            component_id_map: 组件ID到实体ID的映射
        """
        section_id_map = {}

        # 第一轮：创建所有 section 实体
        for section in sections:
            try:
                section_props = self._serialize_layout_section(section)

                success, output = self._run_skill_command(
                    "create",
                    "--type", "LayoutSection",
                    "--props", json.dumps(section_props),
                    "--authority", "observation"
                )

                if success:
                    section_entity = json.loads(output)
                    section_id = section.get('id', '')
                    if section_id:
                        section_id_map[section_id] = section_entity["id"]

                    # 建立关系：Page --has_layout--> LayoutSection
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_layout",
                        to_id=section_entity["id"]
                    )
            except Exception as e:
                print(f"        ⚠️ 存储布局区块失败: {e}")
                continue

        # 第二轮：建立 section 之间的关系和 component 关系
        for section in sections:
            try:
                section_id = section.get('id', '')
                if section_id not in section_id_map:
                    continue

                section_entity_id = section_id_map[section_id]

                # 建立与 component 的关系
                component_ids = section.get('component_ids', [])
                for comp_id in component_ids:
                    if comp_id in component_id_map:
                        self._create_relation(
                            from_id=section_entity_id,
                            rel_type="contains_component",
                            to_id=component_id_map[comp_id]
                        )

                # 建立父子 section 关系
                parent_id = section.get('parent_section_id', '')
                if parent_id and parent_id in section_id_map:
                    self._create_relation(
                        from_id=section_id_map[parent_id],
                        rel_type="has_child_section",
                        to_id=section_entity_id
                    )

                child_sections = section.get('child_sections', [])
                for child_id in child_sections:
                    if child_id in section_id_map:
                        self._create_relation(
                            from_id=section_entity_id,
                            rel_type="has_child_section",
                            to_id=section_id_map[child_id]
                        )

            except Exception as e:
                print(f"        ⚠️ 建立布局区块关系失败: {e}")
                continue

    def _serialize_layout_section(self, section: Dict) -> Dict:
        """序列化布局区块，保留所有属性"""
        props = {}

        # 基础属性
        props['id'] = section.get('id', '')
        props['type'] = section.get('type', 'unknown')
        props['name'] = section.get('name', '')[:200]

        # 组件ID列表
        component_ids = section.get('component_ids', [])
        if component_ids:
            props['component_ids'] = json.dumps(component_ids[:100])

        # 父子关系
        parent_id = section.get('parent_section_id', '')
        if parent_id:
            props['parent_section_id'] = parent_id

        child_sections = section.get('child_sections', [])
        if child_sections:
            props['child_sections'] = json.dumps(child_sections[:50])

        # 样式
        styles = section.get('styles', {})
        if styles:
            props['styles'] = json.dumps(styles, ensure_ascii=False)

        # Bounding box
        bbox = section.get('bounding_box', {})
        if bbox:
            props['bounding_box'] = json.dumps(bbox)
            props['x'] = bbox.get('x', 0)
            props['y'] = bbox.get('y', 0)
            props['width'] = bbox.get('width', 0)
            props['height'] = bbox.get('height', 0)

        return props

    def _store_style_system(self, css_rules: Dict, page_entity_id: str):
        """
        存储样式系统实体
        同时创建聚合摘要和逐条CSS规则
        """
        try:
            # 1. 创建聚合摘要
            rule_count = len(css_rules)
            selector_samples = list(css_rules.keys())[:20]

            style_props = {
                "rule_count": rule_count,
                "selector_samples": json.dumps(selector_samples),
                "source": "external_css",
                "type": "style_system_summary"
            }

            success, output = self._run_skill_command(
                "create",
                "--type", "StyleSystem",
                "--props", json.dumps(style_props),
                "--authority", "observation"
            )

            if success:
                style_entity = json.loads(output)
                # 建立关系：Page --uses_styles--> StyleSystem
                self._create_relation(
                    from_id=page_entity_id,
                    rel_type="uses_styles",
                    to_id=style_entity["id"]
                )

                # 2. 逐条存储所有CSS规则（100%保留）
                print(f"      - 逐条存储所有 {len(css_rules)} 条CSS规则...")
                self._store_css_rules_individually(css_rules, style_entity["id"], page_entity_id)

        except Exception as e:
            print(f"        ⚠️ 存储样式系统失败: {e}")

    def _store_css_rules_individually(self, css_rules: Dict, style_system_id: str, page_entity_id: str):
        """
        逐条存储所有CSS规则（100%保留，不限制数量）

        Args:
            css_rules: CSS规则字典 {selector: declarations}
            style_system_id: 样式系统实体ID
            page_entity_id: 页面实体ID
        """
        stored_count = 0
        failed_count = 0
        total_count = len(css_rules)

        for selector, declarations in css_rules.items():
            try:
                # 序列化declarations
                if isinstance(declarations, dict):
                    decl_str = json.dumps(declarations, ensure_ascii=False)[:2000]
                elif isinstance(declarations, list):
                    decl_str = json.dumps(declarations, ensure_ascii=False)[:2000]
                else:
                    decl_str = str(declarations)[:2000]

                rule_props = {
                    "selector": selector[:500],  # 限制选择器长度
                    "declarations": decl_str,
                    "declaration_count": len(declarations) if isinstance(declarations, (dict, list)) else 0,
                    "source": "external_css"
                }

                success, output = self._run_skill_command(
                    "create",
                    "--type", "CSSRule",
                    "--props", json.dumps(rule_props),
                    "--authority", "observation"
                )

                if success:
                    rule_entity = json.loads(output)

                    # 建立关系：StyleSystem --has_rule--> CSSRule
                    self._create_relation(
                        from_id=style_system_id,
                        rel_type="has_rule",
                        to_id=rule_entity["id"]
                    )

                    # 建立关系：Page --has_css_rule--> CSSRule
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_css_rule",
                        to_id=rule_entity["id"]
                    )

                    stored_count += 1

            except Exception as e:
                failed_count += 1
                if failed_count <= 5:  # 只显示前5个错误
                    print(f"          ⚠️ 存储CSS规则失败 [{selector[:50]}...]: {e}")
                continue

        # 报告结果
        success_rate = (stored_count / total_count * 100) if total_count > 0 else 0
        print(f"        ✅ 成功存储 {stored_count}/{total_count} 条CSS规则 ({success_rate:.1f}%)")
        if failed_count > 0:
            print(f"        ⚠️ 失败 {failed_count} 条")

    def _store_design_tokens(self, color_palette: List, typography: Dict, page_entity_id: str):
        """存储设计令牌实体（颜色/字号/字体）"""
        try:
            # 存储颜色
            for color in color_palette[:50]:  # 限制数量
                if color:
                    token_props = {
                        "token_type": "color",
                        "value": color,
                        "name": f"color_{color.replace('#', '')}"
                    }

                    success, output = self._run_skill_command(
                        "create",
                        "--type", "DesignToken",
                        "--props", json.dumps(token_props),
                        "--authority", "observation"
                    )

                    if success:
                        token_entity = json.loads(output)
                        self._create_relation(
                            from_id=page_entity_id,
                            rel_type="has_design_token",
                            to_id=token_entity["id"]
                        )

            # 存储字号
            font_sizes = typography.get('font_sizes', [])
            for size in font_sizes[:20]:  # 限制数量
                if size:
                    token_props = {
                        "token_type": "font_size",
                        "value": str(size),
                        "name": f"font_size_{size}"
                    }

                    success, output = self._run_skill_command(
                        "create",
                        "--type", "DesignToken",
                        "--props", json.dumps(token_props),
                        "--authority", "observation"
                    )

                    if success:
                        token_entity = json.loads(output)
                        self._create_relation(
                            from_id=page_entity_id,
                            rel_type="has_design_token",
                            to_id=token_entity["id"]
                        )

            # 存储字体
            font_families = typography.get('font_families', [])
            for font in font_families[:10]:  # 限制数量
                if font:
                    token_props = {
                        "token_type": "font_family",
                        "value": font,
                        "name": f"font_{font.replace(' ', '_')[:30]}"
                    }

                    success, output = self._run_skill_command(
                        "create",
                        "--type", "DesignToken",
                        "--props", json.dumps(token_props),
                        "--authority", "observation"
                    )

                    if success:
                        token_entity = json.loads(output)
                        self._create_relation(
                            from_id=page_entity_id,
                            rel_type="has_design_token",
                            to_id=token_entity["id"]
                        )

        except Exception as e:
            print(f"        ⚠️ 存储设计令牌失败: {e}")

    def _store_resources(self, task_path: Path, page_entity_id: str):
        """
        存储资源文件实体

        分析 network/resources 目录中的资源文件
        """
        resources_dir = task_path / "network" / "resources"

        if not resources_dir.exists():
            print(f"      - 未找到资源目录")
            return

        # 获取所有资源文件
        resource_files = list(resources_dir.iterdir())
        print(f"      - 发现 {len(resource_files)} 个资源文件")

        stored_count = 0
        for resource_file in resource_files:
            try:
                # 从文件名解析信息
                filename = resource_file.name
                resource_props = self._parse_resource_filename(filename)

                # 添加文件信息
                resource_props['filename'] = filename[:200]
                resource_props['file_path'] = str(resource_file.relative_to(task_path))[:300]

                # 尝试获取文件大小
                try:
                    resource_props['file_size'] = resource_file.stat().st_size
                except:
                    resource_props['file_size'] = 0

                success, output = self._run_skill_command(
                    "create",
                    "--type", "Resource",
                    "--props", json.dumps(resource_props),
                    "--authority", "observation"
                )

                if success:
                    resource_entity = json.loads(output)

                    # 建立关系：Page --has_resource--> Resource
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_resource",
                        to_id=resource_entity["id"]
                    )

                    stored_count += 1

            except Exception as e:
                print(f"        ⚠️ 存储资源失败 [{filename[:50]}...]: {e}")
                continue

        print(f"        ✅ 成功存储 {stored_count} 个资源")

    def _parse_resource_filename(self, filename: str) -> Dict:
        """从资源文件名解析信息"""
        props = {}

        # 提取资源类型（从扩展名）
        if '.' in filename:
            ext = filename.split('.')[-1].lower()
            type_mapping = {
                'css': 'stylesheet',
                'js': 'script',
                'png': 'image',
                'jpg': 'image',
                'jpeg': 'image',
                'gif': 'image',
                'svg': 'image',
                'woff': 'font',
                'woff2': 'font',
                'ttf': 'font',
                'eot': 'font',
                'html': 'document',
                'json': 'data',
                'xml': 'data'
            }
            props['resource_type'] = type_mapping.get(ext, 'unknown')
        else:
            props['resource_type'] = 'unknown'

        # 尝试提取时间戳（文件名开头通常是时间戳）
        parts = filename.split('_')
        if parts and parts[0].isdigit():
            props['timestamp'] = int(parts[0])

        # 尝试提取原始URL信息（从文件名中的下划线分隔）
        if len(parts) > 1:
            # 最后一部分通常是原始文件名
            original_name = '_'.join(parts[1:]) if len(parts) > 2 else parts[-1]
            props['original_name'] = original_name[:200]

        return props

    def _store_video_keyframes(self, task_path: Path, page_entity_id: str):
        """
        存储视频关键帧实体

        分析 video/enhanced_final 目录中的关键帧截图
        """
        keyframes_dir = task_path / "video" / "enhanced_final"

        if not keyframes_dir.exists():
            # 尝试其他可能的路径
            keyframes_dir = task_path / "analysis" / "enhanced_final"

        if not keyframes_dir.exists():
            print(f"      - 未找到关键帧目录")
            return

        # 查找截图文件
        screenshot_files = list(keyframes_dir.glob("*.png")) + list(keyframes_dir.glob("*.jpg"))
        print(f"      - 发现 {len(screenshot_files)} 个关键帧")

        stored_count = 0
        for screenshot_file in screenshot_files:
            try:
                keyframe_props = {
                    'filename': screenshot_file.name[:200],
                    'file_path': str(screenshot_file.relative_to(task_path))[:300],
                    'type': 'screenshot'
                }

                # 尝试获取文件大小
                try:
                    keyframe_props['file_size'] = screenshot_file.stat().st_size
                except:
                    keyframe_props['file_size'] = 0

                success, output = self._run_skill_command(
                    "create",
                    "--type", "VideoKeyframe",
                    "--props", json.dumps(keyframe_props),
                    "--authority", "observation"
                )

                if success:
                    keyframe_entity = json.loads(output)

                    # 建立关系：Page --has_keyframe--> VideoKeyframe
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_keyframe",
                        to_id=keyframe_entity["id"]
                    )

                    stored_count += 1

            except Exception as e:
                print(f"        ⚠️ 存储关键帧失败: {e}")
                continue

        print(f"        ✅ 成功存储 {stored_count} 个关键帧")

    def _store_dom_snapshots(self, task_path: Path, page_entity_id: str):
        """
        存储DOM快照实体

        分析 dom/ 目录中的 snapshot 文件
        """
        dom_dir = task_path / "dom"

        if not dom_dir.exists():
            print(f"      - 未找到DOM目录")
            return

        # 查找 snapshot 文件
        snapshot_files = list(dom_dir.glob("snapshot_*.json"))
        print(f"      - 发现 {len(snapshot_files)} 个DOM快照")

        stored_count = 0
        for snapshot_file in snapshot_files:
            try:
                # 读取 snapshot 基本信息
                snapshot_info = self._extract_snapshot_info(snapshot_file)

                success, output = self._run_skill_command(
                    "create",
                    "--type", "DOMSnapshot",
                    "--props", json.dumps(snapshot_info),
                    "--authority", "observation"
                )

                if success:
                    snapshot_entity = json.loads(output)

                    # 建立关系：Page --has_snapshot--> DOMSnapshot
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_snapshot",
                        to_id=snapshot_entity["id"]
                    )

                    stored_count += 1

            except Exception as e:
                print(f"        ⚠️ 存储DOM快照失败: {e}")
                continue

        print(f"        ✅ 成功存储 {stored_count} 个DOM快照")

    def _extract_snapshot_info(self, snapshot_file: Path) -> Dict:
        """提取 snapshot 文件的基本信息"""
        info = {
            'filename': snapshot_file.name[:200],
            'file_path': str(snapshot_file)[-300:],  # 只保留路径末尾
            'type': 'dom_snapshot'
        }

        # 尝试从文件名提取时间戳
        parts = snapshot_file.stem.split('_')
        if len(parts) >= 2 and parts[1].isdigit():
            info['timestamp'] = int(parts[1])

        # 尝试读取文件获取更多信息
        try:
            with open(snapshot_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            rrweb_event = data.get('rrwebEvent', {})
            info['event_type'] = rrweb_event.get('type', 'unknown')
            info['timestamp'] = rrweb_event.get('timestamp', info.get('timestamp', 0))

            # 统计元素数量
            data_node = rrweb_event.get('data', {})
            nodes = data_node.get('nodes', [])
            info['node_count'] = len(nodes)

        except Exception:
            pass

        # 文件大小
        try:
            info['file_size'] = snapshot_file.stat().st_size
        except:
            info['file_size'] = 0

        return info

    def _store_breakpoints(self, structure_data: Dict, page_entity_id: str):
        """
        存储响应式断点实体

        从 page_structure 中提取 breakpoints 信息
        """
        breakpoints = structure_data.get('breakpoints', [])

        if not breakpoints:
            print(f"      - 未发现响应式断点")
            return

        print(f"      - 发现 {len(breakpoints)} 个断点")

        stored_count = 0
        for bp in breakpoints:
            try:
                bp_props = {
                    'name': bp.get('name', 'unknown')[:100],
                    'min_width': bp.get('min_width', 0),
                    'max_width': bp.get('max_width', 0),
                    'media_query': bp.get('media_query', '')[:500]
                }

                success, output = self._run_skill_command(
                    "create",
                    "--type", "Breakpoint",
                    "--props", json.dumps(bp_props),
                    "--authority", "observation"
                )

                if success:
                    bp_entity = json.loads(output)

                    # 建立关系：Page --has_breakpoint--> Breakpoint
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_breakpoint",
                        to_id=bp_entity["id"]
                    )

                    stored_count += 1

            except Exception as e:
                print(f"        ⚠️ 存储断点失败: {e}")
                continue

        print(f"        ✅ 成功存储 {stored_count} 个断点")

    def _store_business_entity(self, entity: APIEntity, system_id: str):
        """存储业务实体"""
        entity_props = json.dumps({
            "name": entity.name,
            "entity_type": entity.entity_type,
            "source_url": entity.source_url,
            "attributes": json.dumps(entity.attributes, ensure_ascii=False)[:500]  # 限制长度
        })
        
        # 根据实体类型选择类型
        entity_type = self._map_entity_type(entity.entity_type)
        
        success, output = self._run_skill_command(
            "create",
            "--type", entity_type,
            "--props", entity_props,
            "--authority", "observation"
        )
        
        if success:
            try:
                entity_obj = json.loads(output)
                # 建立关系：System --has_entity--> Entity
                self._create_relation(
                    from_id=system_id,
                    rel_type="has_entity",
                    to_id=entity_obj["id"]
                )
            except:
                pass
    
    def _create_relation(self, from_id: str, rel_type: str, 
                        to_id: str, properties: Dict = None):
        """创建实体关系"""
        props = json.dumps(properties or {})
        
        self._run_skill_command(
            "relate",
            "--from", from_id,
            "--rel", rel_type,
            "--to", to_id,
            "--props", props,
            "--authority", "observation"
        )
    
    def _query_entity(self, entity_type: str, where: Dict) -> List[Dict]:
        """查询实体"""
        where_json = json.dumps(where)
        
        success, output = self._run_skill_command(
            "query",
            "--type", entity_type,
            "--where", where_json
        )
        
        if success:
            try:
                return json.loads(output)
            except:
                return []
        return []
    
    def _resolve_system_conflicts(self, system_id: str):
        """
        解决系统知识冲突
        使用openclaw-memory-skill的ConflictManager逻辑
        """
        # 查询该系统的所有页面
        pages = self._query_related(system_id, "has_page")
        
        # 检测URL相同的页面（可能的冲突）
        url_map = {}
        for page in pages:
            url = page.get("properties", {}).get("url", "")
            if url in url_map:
                # 发现冲突：同一URL多个记录
                print(f"  检测到冲突: 页面 {url} 有多个记录")
                # 按时间戳决定保留哪个（新的覆盖旧的）
                # 实际应该使用ConflictManager.resolve_conflict
            else:
                url_map[url] = page
    
    def _query_related(self, entity_id: str, relation_type: str) -> List[Dict]:
        """查询相关实体"""
        success, output = self._run_skill_command(
            "related",
            "--id", entity_id,
            "--rel", relation_type,
            "--dir", "outgoing"
        )
        
        if success:
            try:
                return json.loads(output)
            except:
                return []
        return []
    
    def _map_entity_type(self, entity_type: str) -> str:
        """映射实体类型到skill类型"""
        type_mapping = {
            "announcement": "Document",
            "recruitment": "Task",
            "product": "Product",
            "service": "Service",
            "generic": "Entity"
        }
        return type_mapping.get(entity_type, "Entity")
    
    def get_system_knowledge_summary(self, system_name: str) -> Dict:
        """获取系统知识摘要"""
        # 查询系统实体
        systems = self._query_entity("System", {"name": system_name})
        
        if not systems:
            return {"error": "System not found"}
        
        system = systems[0]
        system_id = system["id"]
        
        # 查询相关实体
        recordings = self._query_related(system_id, "has_recording")
        pages = self._query_related(system_id, "has_page")
        entities = self._query_related(system_id, "has_entity")
        
        return {
            "system": system_name,
            "recordings_count": len(recordings),
            "pages_count": len(pages),
            "entities_count": len(entities),
            "recordings": [r.get("properties", {}).get("task_id", "") for r in recordings],
            "pages": [p.get("properties", {}).get("url", "") for p in pages[:5]]
        }
