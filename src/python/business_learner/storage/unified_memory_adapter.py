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
        if components:
            print(f"      - 存储 {len(components)} 个组件...")
            self._store_components(components, page_entity_id)

        # 2. 存储布局区块
        layout_sections = structure_data.get('layout_sections', [])
        if layout_sections:
            print(f"      - 存储 {len(layout_sections)} 个布局区块...")
            self._store_layout_sections(layout_sections, page_entity_id, components)

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

    def _store_components(self, components: List[Dict], page_entity_id: str):
        """存储组件实体"""
        for comp in components:
            try:
                # 构建组件属性
                comp_props = {
                    "tag": comp.get('tag', ''),
                    "type": comp.get('type', 'unknown'),
                    "text_content": comp.get('text_content', '')[:200],  # 限制长度
                    "is_interactive": comp.get('is_interactive', False),
                }

                # 添加类名
                class_names = comp.get('class_names', [])
                if class_names:
                    comp_props["classes"] = ' '.join(class_names[:10])  # 限制数量

                # 添加 bounding_box
                bbox = comp.get('bounding_box', {})
                if bbox:
                    comp_props["x"] = bbox.get('x', 0)
                    comp_props["y"] = bbox.get('y', 0)
                    comp_props["width"] = bbox.get('width', 0)
                    comp_props["height"] = bbox.get('height', 0)

                # 添加样式（简化）
                styles = comp.get('styles', {})
                if styles:
                    comp_props["display"] = styles.get('display', '')
                    comp_props["position"] = styles.get('position', '')
                    comp_props["color"] = styles.get('color', '')
                    comp_props["background_color"] = styles.get('background_color', '')

                success, output = self._run_skill_command(
                    "create",
                    "--type", "Component",
                    "--props", json.dumps(comp_props),
                    "--authority", "observation"
                )

                if success:
                    comp_entity = json.loads(output)
                    # 建立关系：Page --contains--> Component
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="contains",
                        to_id=comp_entity["id"]
                    )
            except Exception as e:
                print(f"        ⚠️ 存储组件失败: {e}")
                continue

    def _store_layout_sections(self, sections: List[Dict], page_entity_id: str, components: List[Dict]):
        """存储布局区块实体"""
        # 创建组件ID到实体ID的映射（简化处理）
        for section in sections:
            try:
                section_props = {
                    "section_type": section.get('type', 'unknown'),
                    "name": section.get('name', '')[:100],
                }

                # 添加 bounding_box
                bbox = section.get('bounding_box', {})
                if bbox:
                    section_props["x"] = bbox.get('x', 0)
                    section_props["y"] = bbox.get('y', 0)
                    section_props["width"] = bbox.get('width', 0)
                    section_props["height"] = bbox.get('height', 0)

                success, output = self._run_skill_command(
                    "create",
                    "--type", "LayoutSection",
                    "--props", json.dumps(section_props),
                    "--authority", "observation"
                )

                if success:
                    section_entity = json.loads(output)
                    # 建立关系：Page --has_layout--> LayoutSection
                    self._create_relation(
                        from_id=page_entity_id,
                        rel_type="has_layout",
                        to_id=section_entity["id"]
                    )
            except Exception as e:
                print(f"        ⚠️ 存储布局区块失败: {e}")
                continue

    def _store_style_system(self, css_rules: Dict, page_entity_id: str):
        """存储样式系统实体（CSS规则聚合）"""
        try:
            # 统计CSS规则
            rule_count = len(css_rules)
            selector_samples = list(css_rules.keys())[:20]  # 取样前20个选择器

            style_props = {
                "rule_count": rule_count,
                "selector_samples": json.dumps(selector_samples),
                "source": "external_css"
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
        except Exception as e:
            print(f"        ⚠️ 存储样式系统失败: {e}")

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
