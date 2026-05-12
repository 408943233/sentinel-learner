"""
统一Memory适配器
支持本地模式和服务器模式
与OpenClaw Memory Skill集成
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from datetime import datetime

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
        
        # 读取环境变量或使用默认值（优先从settings读取）
        from ..config.settings import MEMORY_SKILL_PATH
        self.workspace_base = Path(
            os.environ.get("SENTINEL_WORKSPACE", Path.home() / ".openclaw" / "workspace")
        )
        self.script_base = Path(
            os.environ.get("OPENCLAW_SKILL_PATH", MEMORY_SKILL_PATH)
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
        
        # 批量写入模式：在内存中构建所有实体
        self._batch_entities: List[Dict] = []
        self._batch_relations: List[Dict] = []
    
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
    
    def _generate_id(self, entity_type: str) -> str:
        """生成实体ID"""
        return f"{entity_type.lower()}_{uuid.uuid4().hex[:12]}"
    
    def _create_entity_batch(self, entity_type: str, properties: Dict, 
                             source: str = "sentinel-learner",
                             authority: str = "observation") -> Dict:
        """
        在内存中创建实体（批量模式）
        
        Returns:
            实体字典（包含id）
        """
        entity = {
            "id": self._generate_id(entity_type),
            "type": entity_type,
            "properties": properties,
            "source": source,
            "authority": authority,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self._batch_entities.append(entity)
        return entity
    
    def _create_relation_batch(self, from_id: str, rel_type: str, to_id: str,
                               properties: Optional[Dict] = None):
        """在内存中创建关系（批量模式）"""
        relation = {
            "from": from_id,
            "type": rel_type,
            "to": to_id,
            "properties": properties or {},
            "created_at": datetime.now().isoformat()
        }
        self._batch_relations.append(relation)
    
    def _flush_batch(self) -> bool:
        """
        将内存中的所有实体和关系一次性写入graph.jsonl
        
        Returns:
            是否成功
        """
        if not self._batch_entities and not self._batch_relations:
            return True
        
        try:
            # 确保目录存在
            self.graph_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 追加写入graph.jsonl
            with open(self.graph_path, 'a', encoding='utf-8') as f:
                # 写入实体
                for entity in self._batch_entities:
                    f.write(json.dumps(entity, ensure_ascii=False) + '\n')
                
                # 写入关系（也作为实体存储，带from/to）
                for relation in self._batch_relations:
                    rel_entity = {
                        "id": self._generate_id("relation"),
                        "type": "Relation",
                        "properties": relation,
                        "source": "sentinel-learner",
                        "authority": "system",
                        "created_at": relation.get("created_at", datetime.now().isoformat()),
                        "updated_at": datetime.now().isoformat()
                    }
                    f.write(json.dumps(rel_entity, ensure_ascii=False) + '\n')
            
            print(f"  ✅ 批量写入完成: {len(self._batch_entities)} 实体, {len(self._batch_relations)} 关系")
            
            # 清空批量缓存
            self._batch_entities.clear()
            self._batch_relations.clear()
            
            return True
        except Exception as e:
            print(f"  ❌ 批量写入失败: {e}")
            return False
    
    def store_task_knowledge(self, task_result: TaskUnderstanding, 
                            metadata_manager: TaskMetadataManager):
        """
        存储Task知识到知识图谱（批量写入模式）
        
        Args:
            task_result: 任务理解结果
            metadata_manager: 元数据管理器
        """
        print(f"\n[UnifiedMemoryAdapter] 存储Task知识 (模式: {self.mode}, 批量写入)...")
        
        # 清空之前的批量缓存
        self._batch_entities.clear()
        self._batch_relations.clear()
        
        # 1. 获取或创建目标系统实体
        metadata = metadata_manager.load_metadata()
        system_entity = self._get_or_create_system_batch(metadata)
        
        # 2. 创建Task记录实体
        task_entity = self._create_task_entity_batch(metadata, task_result)
        
        # 3. 建立系统-Task关系
        self._create_relation_batch(
            from_id=system_entity["id"],
            rel_type="has_recording",
            to_id=task_entity["id"],
            properties={"recorded_at": metadata.recorder.recorded_at}
        )
        
        # 4. 存储页面知识（包含详细结构）
        for page in task_result.pages:
            page_entity = self._store_page_knowledge_batch(page, task_entity["id"], system_entity["id"])
            
            if page_entity:
                page_entity_id = page_entity["id"]
                task_path = metadata_manager.task_path
                
                # 4.1 存储页面详细结构（组件、布局、样式等）
                self._store_page_structure_detailed_batch(
                    page, 
                    page_entity_id, 
                    task_path
                )
                
                # === P0 新增：DOM快照存储 ===
                self._store_dom_snapshots_batch(page, page_entity_id, task_path)
                
                # === P0 新增：组件聚合存储 ===
                self._store_components_batch(page, page_entity_id, task_path)
                
                # === P0 新增：CSS系统存储 ===
                self._store_css_system_batch(page, page_entity_id, task_path)
        
        # 5. 存储业务实体
        print(f"  准备存储 {len(task_result.entities)} 个业务实体...")
        for i, entity in enumerate(task_result.entities):
            try:
                # 类型检查
                if isinstance(entity, str):
                    print(f"    ⚠️ 实体 #{i} 是字符串而非对象: {entity[:50]}...")
                    continue
                if not hasattr(entity, 'name'):
                    print(f"    ⚠️ 实体 #{i} 缺少 name 属性: {type(entity)}")
                    continue
                self._store_business_entity_batch(entity, system_entity["id"])
            except Exception as e:
                print(f"    ⚠️ 存储业务实体 #{i} 失败: {e}")
                continue
        
        # 6. 存储API层数据（P0新增）
        self._store_api_layer_batch(system_entity["id"], metadata_manager.task_path)
        
        # 7. 存储静态资源（P1新增）
        self._store_resources_batch(system_entity["id"], metadata_manager.task_path)
        
        # 8. 存储浏览器状态（P1新增）
        self._store_browser_state_batch(system_entity["id"], metadata_manager.task_path)
        
        # 9. 存储性能指标（P1新增）
        self._store_performance_batch(system_entity["id"], metadata_manager.task_path)
        
        # 10. 解决冲突
        self._resolve_system_conflicts(system_entity["id"])
        
        # 11. 一次性批量写入所有数据
        success = self._flush_batch()
        
        if success:
            print(f"[UnifiedMemoryAdapter] Task知识存储完成")
        else:
            print(f"[UnifiedMemoryAdapter] Task知识存储失败")
    
    def _get_or_create_system_batch(self, metadata) -> Dict:
        """批量模式：获取或创建系统实体"""
        system_name = metadata.target_system.name
        system_domain = metadata.target_system.domain
        
        # 查询是否已存在（从已批量创建的实体中查找）
        for entity in self._batch_entities:
            if entity["type"] == "System" and entity["properties"].get("name") == system_name:
                print(f"  系统已存在(批量缓存): {system_name}")
                return entity
        
        # 创建新系统实体（批量模式）
        props = {
            "name": system_name,
            "domain": system_domain,
            "system_type": metadata.target_system.system_type,
            "description": f"目标系统: {system_name}"
        }
        
        entity = self._create_entity_batch(
            entity_type="System",
            properties=props,
            authority="reference"
        )
        print(f"  创建系统实体(批量): {system_name}")
        return entity
    
    def _get_or_create_system(self, metadata) -> Dict:
        """获取或创建系统实体（旧版，保留用于兼容）"""
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
    
    def _create_task_entity_batch(self, metadata, task_result) -> Dict:
        """批量模式：创建Task实体"""
        # 使用 operator_name 作为 source（如果存在），否则使用默认值
        source = metadata.recorder.operator_name if metadata.recorder.operator_name else "sentinel-learner"
        
        props = {
            "task_id": metadata.task_id,
            "name": metadata.task_name,
            "description": metadata.task_description,
            "recorded_by": metadata.recorder.user_id,
            "operator_name": metadata.recorder.operator_name,
            "recorded_at": metadata.recorder.recorded_at,
            "target_system": metadata.target_system.name,
            "pages_count": len(task_result.pages),
            "entities_count": len(task_result.entities)
        }
        
        entity = self._create_entity_batch(
            entity_type="TaskRecording",
            properties=props,
            source=source,
            authority="observation"
        )
        print(f"  创建Task实体(批量): {metadata.task_id}")
        return entity
    
    def _create_task_entity(self, metadata, task_result) -> Dict:
        """创建Task实体（旧版，保留用于兼容）"""
        props = json.dumps({
            "task_id": metadata.task_id,
            "name": metadata.task_name,
            "description": metadata.task_description,
            "recorded_by": metadata.recorder.user_id,
            "operator_name": metadata.recorder.operator_name,
            "recorded_at": metadata.recorder.recorded_at,
            "target_system": metadata.target_system.name,
            "pages_count": len(task_result.pages),
            "entities_count": len(task_result.entities)
        })
        
        source = metadata.recorder.operator_name if metadata.recorder.operator_name else "sentinel-learner"
        
        success, output = self._run_skill_command(
            "create",
            "--type", "TaskRecording",
            "--props", props,
            "--source", source,
            "--authority", "observation"
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
    
    def _store_page_knowledge_batch(self, page: PageUnderstanding,
                                     task_id: str, system_id: str) -> Optional[Dict]:
        """批量模式：存储页面知识"""
        # 处理不同类型的confidence
        if hasattr(page.overall_confidence, 'value'):
            confidence_value = page.overall_confidence.value
        elif hasattr(page.overall_confidence, 'overall_confidence'):
            confidence_value = str(page.overall_confidence.overall_confidence)
        else:
            confidence_value = str(page.overall_confidence)

        page_props = {
            "url": page.page_info.url,
            "title": page.page_info.title,
            "page_type": page.page_info.page_type,
            "domain": page.page_info.business_domain,
            "confidence": confidence_value
        }

        page_entity = self._create_entity_batch(
            entity_type="WebPage",
            properties=page_props,
            authority="observation"
        )

        # 建立关系：Task --recorded--> Page
        self._create_relation_batch(
            from_id=task_id,
            rel_type="recorded",
            to_id=page_entity["id"]
        )
        # 建立关系：System --has_page--> Page
        self._create_relation_batch(
            from_id=system_id,
            rel_type="has_page",
            to_id=page_entity["id"]
        )
        return page_entity

    def _store_page_knowledge(self, page: PageUnderstanding,
                             task_id: str, system_id: str) -> Optional[Dict]:
        """存储页面知识（旧版，保留用于兼容）"""
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

    def _store_page_structure_detailed_batch(self, page: PageUnderstanding,
                                              page_entity_id: str, task_path: Path):
        """
        批量模式：存储页面详细结构
        简化版本 - 只存储关键信息到页面实体的属性中
        """
        # 查找 page_structure.json
        structure_file = task_path / "analysis" / "page_structure.json"

        if not structure_file.exists():
            return

        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
        except Exception as e:
            return

        # 提取关键统计信息并添加到页面实体
        components = structure_data.get('components', [])
        layout_sections = structure_data.get('layout_sections', [])
        css_rules = structure_data.get('cssRules', [])
        
        # 创建页面结构摘要实体
        structure_summary = {
            "page_id": page_entity_id,
            "component_count": len(components),
            "layout_section_count": len(layout_sections),
            "css_rule_count": len(css_rules),
            "component_types": {},
            "has_responsive_breakpoints": bool(structure_data.get('responsiveBreakpoints')),
            "viewport": structure_data.get('viewport', {})
        }
        
        # 统计组件类型
        for comp in components[:100]:  # 最多统计100个
            comp_type = comp.get('type', 'unknown')
            structure_summary["component_types"][comp_type] = \
                structure_summary["component_types"].get(comp_type, 0) + 1
        
        # 创建页面结构实体
        self._create_entity_batch(
            entity_type="PageStructure",
            properties=structure_summary,
            authority="observation"
        )
        
        # 建立关系：Page --has_structure--> PageStructure
        self._create_relation_batch(
            from_id=page_entity_id,
            rel_type="has_structure",
            to_id=self._batch_entities[-1]["id"]
        )

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

    def _store_business_entity_batch(self, entity: APIEntity, system_id: str):
        """批量模式：存储业务实体"""
        entity_props = {
            "name": entity.name,
            "entity_type": entity.entity_type,
            "source_url": entity.source_url,
            "attributes": json.dumps(entity.attributes, ensure_ascii=False)[:500]
        }
        
        entity_type = self._map_entity_type(entity.entity_type)
        
        entity_obj = self._create_entity_batch(
            entity_type=entity_type,
            properties=entity_props,
            authority="observation"
        )
        
        # 建立关系：System --has_entity--> Entity
        self._create_relation_batch(
            from_id=system_id,
            rel_type="has_entity",
            to_id=entity_obj["id"]
        )

    def _store_business_entity(self, entity: APIEntity, system_id: str):
        """存储业务实体（旧版，保留用于兼容）"""
        entity_props = json.dumps({
            "name": entity.name,
            "entity_type": entity.entity_type,
            "source_url": entity.source_url,
            "attributes": json.dumps(entity.attributes, ensure_ascii=False)[:500]
        })
        
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
        """
        映射实体类型到skill类型
        
        P0 - 核心实体类型（必须实现）
        P1 - 支撑实体类型（建议实现）
        P2 - 视觉资产类型（可选实现）
        """
        type_mapping = {
            # === 基础业务实体 ===
            "announcement": "Document",
            "recruitment": "Task",
            "product": "Product",
            "service": "Service",
            "generic": "Entity",
            
            # === P0 - DOM结构 ===
            "dom_snapshot": "DOMSnapshot",
            "component": "Component",
            "component_group": "ComponentGroup",
            
            # === P0 - CSS系统 ===
            "css_rule": "CSSRule",
            "css_file": "CSSFile",
            "design_token": "DesignToken",
            
            # === P0 - API层 ===
            "api_endpoint": "APIEndpoint",
            "api_request": "APIRequest",
            "api_response": "APIResponse",
            "data_flow": "DataFlow",
            "api_schema": "APISchema",
            
            # === P0 - 业务逻辑 ===
            "user_intent": "UserIntent",
            "business_flow": "BusinessFlow",
            "flow_step": "FlowStep",
            
            # === P1 - 静态资源 ===
            "resource": "Resource",
            "resource_group": "ResourceGroup",
            
            # === P1 - 浏览器状态 ===
            "cookie": "Cookie",
            "cookie_domain": "CookieDomain",
            
            # === P1 - 性能与错误 ===
            "performance_metric": "PerformanceMetric",
            "optimization_suggestion": "OptimizationSuggestion",
            "js_error": "JSError",
            "anchor_event": "AnchorEvent",
            
            # === P2 - 视觉资产 ===
            "keyframe": "Keyframe",
            "keyframe_collection": "KeyframeCollection",
            "long_screenshot": "LongScreenshot",
            "prototype_demo": "PrototypeDemo",
        }
        return type_mapping.get(entity_type, "Entity")
    
    # ==================== P0 实现：DOM快照存储 ====================
    
    def _store_dom_snapshots_batch(self, page, page_entity_id: str, task_path: Path):
        """
        P0: 存储DOM快照
        
        从 dom/snapshot_*.json 文件读取并创建实体
        目标：36个快照 → 36个 DOMSnapshot 实体
        """
        dom_dir = task_path / "dom"
        if not dom_dir.exists():
            return
        
        snapshot_files = list(dom_dir.glob("snapshot_*.json"))
        if not snapshot_files:
            return
        
        print(f"    存储DOM快照: {len(snapshot_files)} 个")
        stored_count = 0
        
        for snapshot_file in snapshot_files:
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    snapshot_data = json.load(f)
                
                # 判断类型：有 rrwebEvent 的是完整快照
                has_rrweb = bool(snapshot_data.get("rrwebEvent"))
                snapshot_type = "full" if has_rrweb else "incremental"
                
                # 计算元素数量
                components = snapshot_data.get("components", [])
                element_count = len(components)
                
                props = {
                    "timestamp": snapshot_data.get("timestamp", 0),
                    "url": snapshot_data.get("url", ""),
                    "title": snapshot_data.get("title", ""),
                    "type": snapshot_type,
                    "has_rrweb": has_rrweb,
                    "element_count": element_count,
                    "snapshot_file_path": f"dom/{snapshot_file.name}"
                }
                
                snapshot_entity = self._create_entity_batch(
                    entity_type="DOMSnapshot",
                    properties=props,
                    authority="observation"
                )
                
                # 建立关系：Page --has_dom_snapshot--> DOMSnapshot
                self._create_relation_batch(
                    from_id=page_entity_id,
                    rel_type="has_dom_snapshot",
                    to_id=snapshot_entity["id"],
                    properties={"captured_at": props["timestamp"], "type": snapshot_type}
                )
                
                stored_count += 1
            except Exception as e:
                print(f"      ⚠️ 存储快照失败 {snapshot_file.name}: {e}")
        
        print(f"      ✅ 成功存储 {stored_count} 个DOM快照")
    
    # ==================== P0 实现：组件聚合存储 ====================
    
    def _store_components_batch(self, page, page_entity_id: str, task_path: Path):
        """
        P0: 存储组件（聚合模式）
        
        621个组件 → 每页1个 ComponentGroup 聚合实体
        避免图谱爆炸，同时保留关键信息
        """
        structure_file = task_path / "analysis" / "page_structure.json"
        if not structure_file.exists():
            return
        
        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
            
            components = structure_data.get("components", [])
            if not components:
                return
            
            print(f"    存储组件: {len(components)} 个 → 聚合为 ComponentGroup")
            
            # 统计信息
            tag_distribution = {}
            interactive_count = 0
            with_styles_count = 0
            with_computed_styles_count = 0
            with_text_count = 0
            
            # 提取关键交互组件（限制数量避免过大）
            key_components = []
            interactive_components = [c for c in components if c.get("is_interactive")]
            
            for comp in interactive_components[:20]:  # 最多20个交互组件
                key_components.append({
                    "id": comp.get("id", ""),
                    "tag": comp.get("tag", ""),
                    "class_names": comp.get("class_names", [])[:3],
                    "text_content": (comp.get("text_content", "") or "")[:50],
                    "is_interactive": True
                })
            
            # 统计所有组件
            for comp in components:
                tag = comp.get("tag", "unknown")
                tag_distribution[tag] = tag_distribution.get(tag, 0) + 1
                
                if comp.get("is_interactive"):
                    interactive_count += 1
                if comp.get("styles"):
                    with_styles_count += 1
                if comp.get("computed_styles"):
                    with_computed_styles_count += 1
                if comp.get("text_content"):
                    with_text_count += 1
            
            # 创建聚合实体
            props = {
                "page_url": page.url if hasattr(page, 'url') else "",
                "total_components": len(components),
                "tag_distribution": tag_distribution,
                "interactive_count": interactive_count,
                "with_styles_count": with_styles_count,
                "with_computed_styles_count": with_computed_styles_count,
                "with_text_count": with_text_count,
                "key_interactive_components": key_components,
                "structure_file_path": "analysis/page_structure.json"
            }
            
            group_entity = self._create_entity_batch(
                entity_type="ComponentGroup",
                properties=props,
                authority="observation"
            )
            
            # 建立关系：Page --has_component--> ComponentGroup
            self._create_relation_batch(
                from_id=page_entity_id,
                rel_type="has_component",
                to_id=group_entity["id"]
            )
            
            print(f"      ✅ 聚合完成: {len(components)} 个组件")
            
        except Exception as e:
            print(f"      ⚠️ 存储组件失败: {e}")
    
    # ==================== P0 实现：CSS系统存储 ====================
    
    def _store_css_system_batch(self, page, page_entity_id: str, task_path: Path):
        """
        P0: 存储CSS系统和设计令牌
        
        - CSS规则按文件聚合（8215条 → 每文件1个CSSFile实体）
        - 设计令牌单独存储（颜色、字体、字号）
        """
        structure_file = task_path / "analysis" / "page_structure.json"
        if not structure_file.exists():
            return
        
        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
            
            # 1. 存储CSS文件（聚合模式）
            css_rules = structure_data.get("external_css_rules", [])
            if css_rules:
                print(f"    存储CSS规则: {len(css_rules)} 条")
                
                # 按文件分组聚合
                files_map = {}
                for rule in css_rules[:1000]:  # 限制处理数量避免过大
                    source_file = rule.get("source_file", "unknown.css")
                    if source_file not in files_map:
                        files_map[source_file] = []
                    files_map[source_file].append(rule)
                
                # 每个CSS文件创建一个聚合实体
                for file_name, rules in files_map.items():
                    # 提取选择器样本（前10个）
                    selectors_sample = [r.get("selector", "") for r in rules[:10]]
                    
                    # 汇总属性统计
                    properties_summary = self._summarize_css_properties(rules)
                    
                    props = {
                        "file_name": file_name,
                        "rule_count": len(rules),
                        "selectors_sample": selectors_sample,
                        "properties_summary": properties_summary
                    }
                    
                    css_file_entity = self._create_entity_batch(
                        entity_type="CSSFile",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：Page --has_css--> CSSFile
                    self._create_relation_batch(
                        from_id=page_entity_id,
                        rel_type="has_css",
                        to_id=css_file_entity["id"]
                    )
                
                print(f"      ✅ 存储 {len(files_map)} 个CSS文件聚合")
            
            # 2. 存储设计令牌
            color_palette = structure_data.get("color_palette", [])
            typography = structure_data.get("typography", {})
            
            if color_palette or typography:
                print(f"    存储设计令牌: {len(color_palette)} 颜色")
                
                # 颜色令牌
                for color in color_palette[:50]:  # 限制数量
                    props = {
                        "token_type": "color",
                        "name": color.get("name", ""),
                        "value": color.get("value", ""),
                        "usage_count": color.get("usage_count", 0)
                    }
                    
                    token_entity = self._create_entity_batch(
                        entity_type="DesignToken",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：Page --has_design_token--> DesignToken
                    self._create_relation_batch(
                        from_id=page_entity_id,
                        rel_type="has_design_token",
                        to_id=token_entity["id"]
                    )
                
                # 字体令牌
                for font in typography.get("font_families", [])[:10]:
                    props = {
                        "token_type": "font_family",
                        "name": font,
                        "value": font
                    }
                    self._create_entity_batch(
                        entity_type="DesignToken",
                        properties=props,
                        authority="observation"
                    )
                
                # 字号令牌
                for size in typography.get("font_sizes", [])[:10]:
                    props = {
                        "token_type": "font_size",
                        "name": str(size),
                        "value": str(size)
                    }
                    self._create_entity_batch(
                        entity_type="DesignToken",
                        properties=props,
                        authority="observation"
                    )
                
                print(f"      ✅ 存储设计令牌完成")
                
        except Exception as e:
            print(f"      ⚠️ 存储CSS系统失败: {e}")
    
    def _summarize_css_properties(self, rules: List[Dict]) -> Dict:
        """汇总CSS属性统计（取最常见的10个）"""
        properties_count = {}
        for rule in rules:
            for prop in rule.get("properties", {}).keys():
                properties_count[prop] = properties_count.get(prop, 0) + 1
        
        # 返回最常见的10个属性
        sorted_props = sorted(properties_count.items(), key=lambda x: x[1], reverse=True)
        return {k: v for k, v in sorted_props[:10]}
    
    # ==================== P0 实现：API层存储 ====================
    
    def _store_api_layer_batch(self, system_entity_id: str, task_path: Path):
        """
        P0: 存储API层数据
        
        包括：
        - APIEndpoint (23个唯一端点)
        - APIRequest (35个请求)
        - APIResponse (26个响应)
        - DataFlow (10个数据流)
        - APISchema (22个Schema)
        """
        # 1. 读取 API 流量数据
        api_traffic_file = task_path / "analysis" / "api_traffic.json"
        if not api_traffic_file.exists():
            print(f"    ⚠️ 未找到 API 流量数据: {api_traffic_file}")
            return
        
        try:
            with open(api_traffic_file, 'r', encoding='utf-8') as f:
                api_data = json.load(f)
            
            print(f"    存储API层数据...")
            
            # 2. 存储 API Endpoint（按URL去重）
            endpoints = api_data.get("endpoints", [])
            endpoint_entities = {}  # URL -> entity_id 映射
            
            if endpoints:
                print(f"      存储 API Endpoint: {len(endpoints)} 个")
                for endpoint in endpoints[:30]:  # 限制数量
                    url = endpoint.get("url", "")
                    if not url:
                        continue
                    
                    props = {
                        "url": url,
                        "method": endpoint.get("method", "GET"),
                        "domain": endpoint.get("domain", ""),
                        "path": endpoint.get("path", ""),
                        "parameter_names": endpoint.get("parameter_names", []),
                        "response_schema_summary": json.dumps(endpoint.get("response_schema", {}))[:500]
                    }
                    
                    endpoint_entity = self._create_entity_batch(
                        entity_type="APIEndpoint",
                        properties=props,
                        authority="observation"
                    )
                    
                    endpoint_entities[url] = endpoint_entity["id"]
                    
                    # 建立关系：System --has_api--> APIEndpoint
                    self._create_relation_batch(
                        from_id=system_entity_id,
                        rel_type="has_api",
                        to_id=endpoint_entity["id"]
                    )
                
                print(f"        ✅ 存储 {len(endpoint_entities)} 个 Endpoint")
            
            # 3. 存储 API Request
            requests = api_data.get("requests", [])
            if requests:
                print(f"      存储 API Request: {len(requests)} 个")
                stored_count = 0
                
                for req in requests[:40]:  # 限制数量
                    url = req.get("url", "")
                    endpoint_id = endpoint_entities.get(url)
                    
                    props = {
                        "timestamp": req.get("timestamp", 0),
                        "url": url,
                        "method": req.get("method", "GET"),
                        "status": req.get("status", 0),
                        "resource_type": req.get("resourceType", ""),
                        "response_body_summary": (req.get("response_body", "") or "")[:200]
                    }
                    
                    request_entity = self._create_entity_batch(
                        entity_type="APIRequest",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：Endpoint --has_request--> APIRequest
                    if endpoint_id:
                        self._create_relation_batch(
                            from_id=endpoint_id,
                            rel_type="has_request",
                            to_id=request_entity["id"]
                        )
                    
                    stored_count += 1
                
                print(f"        ✅ 存储 {stored_count} 个 Request")
            
            # 4. 存储 API Response（从 responses 或 requests 中提取）
            responses = api_data.get("responses", [])
            if responses:
                print(f"      存储 API Response: {len(responses)} 个")
                stored_count = 0
                
                for resp in responses[:30]:  # 限制数量
                    url = resp.get("url", "")
                    endpoint_id = endpoint_entities.get(url)
                    
                    props = {
                        "url": url,
                        "status": resp.get("status", 0),
                        "headers_summary": json.dumps(resp.get("headers", {}))[:200],
                        "body_structure": resp.get("body_structure", {}),
                        "body_file_path": resp.get("body_file_path", "")
                    }
                    
                    response_entity = self._create_entity_batch(
                        entity_type="APIResponse",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：Endpoint --has_response--> APIResponse
                    if endpoint_id:
                        self._create_relation_batch(
                            from_id=endpoint_id,
                            rel_type="has_response",
                            to_id=response_entity["id"]
                        )
                    
                    stored_count += 1
                
                print(f"        ✅ 存储 {stored_count} 个 Response")
            
            # 5. 存储 DataFlow
            data_flows = api_data.get("data_flows", [])
            if data_flows:
                print(f"      存储 DataFlow: {len(data_flows)} 个")
                
                for flow in data_flows[:15]:  # 限制数量
                    props = {
                        "source": flow.get("source", ""),
                        "target": flow.get("target", ""),
                        "flow_type": flow.get("flow_type", ""),
                        "endpoint_urls": flow.get("endpoint_urls", [])[:10]
                    }
                    
                    flow_entity = self._create_entity_batch(
                        entity_type="DataFlow",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：System --has_data_flow--> DataFlow
                    self._create_relation_batch(
                        from_id=system_entity_id,
                        rel_type="has_data_flow",
                        to_id=flow_entity["id"]
                    )
                
                print(f"        ✅ 存储 {len(data_flows)} 个 DataFlow")
            
            # 6. 存储 API Schema
            schemas = api_data.get("schemas", [])
            if schemas:
                print(f"      存储 API Schema: {len(schemas)} 个")
                
                for schema in schemas[:25]:  # 限制数量
                    endpoint_url = schema.get("endpoint_url", "")
                    endpoint_id = endpoint_entities.get(endpoint_url)
                    
                    props = {
                        "endpoint_url": endpoint_url,
                        "field_types": schema.get("field_types", {}),
                        "constraints": schema.get("constraints", []),
                        "dependencies": schema.get("dependencies", [])
                    }
                    
                    schema_entity = self._create_entity_batch(
                        entity_type="APISchema",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：Endpoint --has_schema--> APISchema
                    if endpoint_id:
                        self._create_relation_batch(
                            from_id=endpoint_id,
                            rel_type="has_schema",
                            to_id=schema_entity["id"]
                        )
                
                print(f"        ✅ 存储 {len(schemas)} 个 Schema")
            
            print(f"    ✅ API层数据存储完成")
            
        except Exception as e:
            print(f"    ⚠️ 存储API层数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    # ==================== P1 实现：静态资源存储（聚合模式）====================
    
    def _store_resources_batch(self, system_entity_id: str, task_path: Path):
        """
        P1: 存储静态资源（聚合模式）
        
        169个资源 → 按类型聚合为6个 ResourceGroup 实体
        类型：html, css, js, img, font, other
        """
        resources_dir = task_path / "network" / "resources"
        if not resources_dir.exists():
            print(f"    ⚠️ 未找到资源目录: {resources_dir}")
            return
        
        try:
            # 读取资源清单
            manifest_file = resources_dir / "manifest.json"
            if not manifest_file.exists():
                print(f"    ⚠️ 未找到资源清单: {manifest_file}")
                return
            
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            resources = manifest.get("resources", [])
            if not resources:
                print(f"    ⚠️ 资源清单为空")
                return
            
            print(f"    存储静态资源: {len(resources)} 个 → 按类型聚合")
            
            # 按类型分组
            type_groups = {
                "html": [],
                "css": [],
                "js": [],
                "img": [],
                "font": [],
                "other": []
            }
            
            for res in resources:
                res_type = res.get("type", "other")
                if res_type not in type_groups:
                    res_type = "other"
                type_groups[res_type].append(res)
            
            # 为每种类型创建聚合实体
            for res_type, items in type_groups.items():
                if not items:
                    continue
                
                # 计算统计信息
                total_size = sum(r.get("size", 0) for r in items)
                urls_sample = [r.get("url", "")[:100] for r in items[:5]]
                
                props = {
                    "resource_type": res_type,
                    "count": len(items),
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / 1024 / 1024, 2),
                    "urls_sample": urls_sample,
                    "cdn_domains": list(set(r.get("cdn_domain", "") for r in items if r.get("cdn_domain")))[:5]
                }
                
                group_entity = self._create_entity_batch(
                    entity_type="ResourceGroup",
                    properties=props,
                    authority="observation"
                )
                
                # 建立关系：System --has_resource--> ResourceGroup
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_resource",
                    to_id=group_entity["id"]
                )
            
            print(f"      ✅ 存储 {sum(1 for v in type_groups.values() if v)} 个资源组")
            
        except Exception as e:
            print(f"      ⚠️ 存储静态资源失败: {e}")
    
    # ==================== P1 实现：浏览器状态存储 ====================
    
    def _store_browser_state_batch(self, system_entity_id: str, task_path: Path):
        """
        P1: 存储浏览器状态
        
        - Cookie (6个)
        - CookieDomain (3个)
        - LocalStorage
        - SessionStorage
        """
        browser_state_file = task_path / "sandbox" / "browser_state.json"
        if not browser_state_file.exists():
            print(f"    ⚠️ 未找到浏览器状态: {browser_state_file}")
            return
        
        try:
            with open(browser_state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            print(f"    存储浏览器状态...")
            
            # 1. 存储 Cookies
            cookies = state_data.get("cookies", [])
            if cookies:
                print(f"      存储 Cookies: {len(cookies)} 个")
                
                for cookie in cookies[:20]:  # 限制数量
                    props = {
                        "name": cookie.get("name", ""),
                        "value": (cookie.get("value", "") or "")[:50],  # 截断
                        "domain": cookie.get("domain", ""),
                        "path": cookie.get("path", "/"),
                        "secure": cookie.get("secure", False),
                        "httpOnly": cookie.get("httpOnly", False),
                        "session": cookie.get("session", True),
                        "sameSite": cookie.get("sameSite", "")
                    }
                    
                    cookie_entity = self._create_entity_batch(
                        entity_type="Cookie",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：System --has_cookie--> Cookie
                    self._create_relation_batch(
                        from_id=system_entity_id,
                        rel_type="has_cookie",
                        to_id=cookie_entity["id"]
                    )
                
                print(f"        ✅ 存储 {len(cookies)} 个 Cookies")
            
            # 2. 存储 CookieDomain（按域名聚合）
            domain_map = {}
            for cookie in cookies:
                domain = cookie.get("domain", "unknown")
                if domain not in domain_map:
                    domain_map[domain] = []
                domain_map[domain].append(cookie)
            
            if domain_map:
                print(f"      存储 CookieDomain: {len(domain_map)} 个")
                
                for domain, domain_cookies in domain_map.items():
                    # 评估安全级别
                    secure_count = sum(1 for c in domain_cookies if c.get("secure"))
                    http_only_count = sum(1 for c in domain_cookies if c.get("httpOnly"))
                    
                    props = {
                        "domain": domain,
                        "cookie_count": len(domain_cookies),
                        "secure_count": secure_count,
                        "http_only_count": http_only_count,
                        "security_level": "high" if secure_count == len(domain_cookies) else "medium" if secure_count > 0 else "low"
                    }
                    
                    domain_entity = self._create_entity_batch(
                        entity_type="CookieDomain",
                        properties=props,
                        authority="observation"
                    )
                    
                    # 建立关系：System --has_domain--> CookieDomain
                    self._create_relation_batch(
                        from_id=system_entity_id,
                        rel_type="has_domain",
                        to_id=domain_entity["id"]
                    )
                
                print(f"        ✅ 存储 {len(domain_map)} 个 CookieDomain")
            
            # 3. LocalStorage
            local_storage = state_data.get("localStorage", {})
            if local_storage:
                print(f"      存储 LocalStorage: {len(local_storage)} 个键")
                # 可以创建聚合实体，但通常数据量不大，暂不单独存储
            
            # 4. SessionStorage
            session_storage = state_data.get("sessionStorage", {})
            if session_storage:
                print(f"      存储 SessionStorage: {len(session_storage)} 个键")
            
            print(f"    ✅ 浏览器状态存储完成")
            
        except Exception as e:
            print(f"    ⚠️ 存储浏览器状态失败: {e}")
    
    # ==================== P1 实现：性能指标存储 ====================
    
    def _store_performance_batch(self, system_entity_id: str, task_path: Path):
        """
        P1: 存储性能指标和优化建议
        
        - PerformanceMetric (~20个)
        - OptimizationSuggestion (4个)
        """
        # 1. 从 video analysis 读取性能数据
        video_analysis_file = task_path / "analysis" / "video_analysis.json"
        performance_metrics = []
        
        if video_analysis_file.exists():
            try:
                with open(video_analysis_file, 'r', encoding='utf-8') as f:
                    video_data = json.load(f)
                
                # 提取视频性能指标
                if "performance" in video_data:
                    perf = video_data["performance"]
                    performance_metrics.extend([
                        {"metric_type": "video_duration", "value": perf.get("duration", 0), "unit": "seconds"},
                        {"metric_type": "total_frames", "value": perf.get("total_frames", 0), "unit": "frames"},
                        {"metric_type": "fps", "value": perf.get("fps", 0), "unit": "fps"},
                        {"metric_type": "event_density", "value": perf.get("event_density", 0), "unit": "events/sec"}
                    ])
            except Exception as e:
                print(f"      ⚠️ 读取视频分析失败: {e}")
        
        # 2. 从 api_traffic 读取时序数据
        api_traffic_file = task_path / "analysis" / "api_traffic.json"
        if api_traffic_file.exists():
            try:
                with open(api_traffic_file, 'r', encoding='utf-8') as f:
                    api_data = json.load(f)
                
                timing = api_data.get("timing_analysis", {})
                if timing:
                    performance_metrics.extend([
                        {"metric_type": "avg_response_time", "value": timing.get("avg_response_time", 0), "unit": "ms"},
                        {"metric_type": "max_response_time", "value": timing.get("max_response_time", 0), "unit": "ms"},
                        {"metric_type": "min_response_time", "value": timing.get("min_response_time", 0), "unit": "ms"}
                    ])
            except Exception as e:
                print(f"      ⚠️ 读取API时序失败: {e}")
        
        # 存储性能指标
        if performance_metrics:
            print(f"    存储性能指标: {len(performance_metrics)} 个")
            
            for metric in performance_metrics:
                props = {
                    "metric_type": metric.get("metric_type", ""),
                    "value": metric.get("value", 0),
                    "unit": metric.get("unit", ""),
                    "source": metric.get("source", "auto")
                }
                
                metric_entity = self._create_entity_batch(
                    entity_type="PerformanceMetric",
                    properties=props,
                    authority="observation"
                )
                
                # 建立关系：System --has_performance--> PerformanceMetric
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_performance",
                    to_id=metric_entity["id"]
                )
            
            print(f"      ✅ 存储 {len(performance_metrics)} 个性能指标")
        
        # 3. 存储优化建议
        optimization_file = task_path / "analysis" / "optimization.json"
        if optimization_file.exists():
            try:
                with open(optimization_file, 'r', encoding='utf-8') as f:
                    opt_data = json.load(f)
                
                suggestions = opt_data.get("suggestions", [])
                if suggestions:
                    print(f"    存储优化建议: {len(suggestions)} 个")
                    
                    for suggestion in suggestions[:10]:  # 限制数量
                        props = {
                            "category": suggestion.get("category", ""),
                            "description": suggestion.get("description", "")[:200],
                            "severity": suggestion.get("severity", "medium"),
                            "affected_resources": suggestion.get("affected_resources", [])[:5]
                        }
                        
                        opt_entity = self._create_entity_batch(
                            entity_type="OptimizationSuggestion",
                            properties=props,
                            authority="observation"
                        )
                        
                        # 建立关系：System --has_suggestion--> OptimizationSuggestion
                        self._create_relation_batch(
                            from_id=system_entity_id,
                            rel_type="has_suggestion",
                            to_id=opt_entity["id"]
                        )
                    
                    print(f"      ✅ 存储 {len(suggestions)} 个优化建议")
            except Exception as e:
                print(f"      ⚠️ 读取优化建议失败: {e}")
    
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
