"""
统一Memory适配器
支持本地模式和服务器模式
与OpenClaw Memory Skill集成
"""

import json
import time
import os
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from datetime import datetime

logger = logging.getLogger(__name__)

def _get_commit_hash() -> str:
    """获取当前代码仓库的 commit 版本号"""
    try:
        script_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(script_dir), timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

_APP_VERSION = _get_commit_hash()

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
        self._skill_entity_manager = None
        self._skill_relation_manager = None
        self._skill_conflict_manager = None
        self._skill_file_manager = None
        self._init_skill_classes()
        self._fail_counts: Dict[str, int] = {}
        logger.info(f"UnifiedMemoryAdapter v{_APP_VERSION} init: mode={self.mode}")
    
    def _init_skill_classes(self):
        if self._skill_entity_manager is not None:
            return
        import importlib.util
        if not self.script_path.exists():
            raise SystemExit(
                f"❌ openclaw-memory-skill 脚本未找到: {self.script_path}\n"
                f"   请确认 OPENCLAW_SKILL_PATH 或 OPENCLAW_MEMORY_PATH 环境变量指向正确路径"
            )

        spec = importlib.util.spec_from_file_location(
            "ontology_optimized_adapter", self.script_path
        )
        ontology_module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(ontology_module)
        except Exception as e:
            raise SystemExit(
                f"❌ openclaw-memory-skill 加载失败: {e}\n"
                f"   脚本路径: {self.script_path}"
            ) from e

        self._skill_entity_manager = ontology_module.EntityManager
        self._skill_relation_manager = ontology_module.RelationManager
        self._skill_conflict_manager = ontology_module.ConflictManager
        self._skill_file_manager = ontology_module.FileManager

        print(f"[UnifiedMemoryAdapter] Skill 类导入成功: {self.script_path}")
    
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
    
    def _load_entity_map_indexed(self) -> Dict[str, Dict]:
        entity_map = {}
        if not self.graph_path.exists():
            return entity_map

        with open(self.graph_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                op = record.get("op")
                if op == "create":
                    e = record.get("entity", record)
                    eid = e.get("id")
                    if eid and e.get("type") != "Relation":
                        entity_map[eid] = e
                elif op == "update":
                    eid = record.get("id")
                    if eid and eid in entity_map:
                        entity_map[eid]["properties"].update(record.get("properties", {}))
                elif op == "delete":
                    eid = record.get("id")
                    entity_map.pop(eid, None)

        return entity_map

    def _find_matching_entity(self, new_entity: Dict, existing: Dict[str, Dict]) -> Optional[str]:
        etype = new_entity.get("type", "")
        props = new_entity.get("properties", {})
        new_name = props.get("name", "")
        new_url = props.get("url", "")

        for eid, e in existing.items():
            if e.get("type") != etype:
                continue
            ep = e.get("properties", {})
            if new_name and ep.get("name") == new_name:
                return eid
            if new_url and ep.get("url") == new_url:
                return eid

        return None

    def _flush_via_skill(self):
        graph_path_str = str(self.graph_path)
        existing_entities = self._load_entity_map_indexed()
        logger.debug(f"_flush_via_skill: {len(self._batch_entities)} entities + {len(self._batch_relations)} relations")
        print(f"\n  ┌─ _flush_via_skill: {len(self._batch_entities)} 实体 + {len(self._batch_relations)} 关系")

        updated_entity_ids = {}
        created_count = 0
        updated_count = 0

        for entity in self._batch_entities:
            entity_type = entity["type"]
            entity_props = entity["properties"]
            entity_id = entity["id"]
            source = entity.get("source", "sentinel-learner")
            authority = entity.get("authority", "observation")

            matching_id = self._find_matching_entity(entity, existing_entities)
            if matching_id:
                updated_entity_ids[entity_id] = matching_id
                url_info = entity_props.get('url', entity_props.get('name', ''))
                print(f"  │ Adapter 去重命中: {entity_type}:{entity_id[:16]} → 更新已有实体 {matching_id[:16]} ({url_info[:40]})")
                result = self._skill_entity_manager.update_entity(
                    entity_id=matching_id,
                    properties=entity_props,
                    graph_path=graph_path_str,
                    confidence=0.8,
                    source=source,
                    authority_level=authority
                )
                if result:
                    updated_count += 1
                else:
                    print(f"  │ ⚠️ update_entity 返回 None: {matching_id[:16]}")
            else:
                created = self._skill_entity_manager.create_entity(
                    type_name=entity_type,
                    properties=entity_props,
                    graph_path=graph_path_str,
                    entity_id=entity_id,
                    confidence=0.8,
                    source=source,
                    authority_level=authority
                )
                existing_entities[entity_id] = created
                created_count += 1

        print(f"  │ 结果: {created_count} 新建, {updated_count} 更新 (Skill治理)")

        relation_count = 0
        for relation in self._batch_relations:
            from_id = updated_entity_ids.get(relation["from"], relation["from"])
            to_id = updated_entity_ids.get(relation["to"], relation["to"])
            if relation.get("from") != from_id:
                print(f"  │ Relation from_id 重映射: {relation['from'][:16]} → {from_id[:16]}")
            self._skill_relation_manager.create_relation(
                from_id=from_id,
                rel_type=relation["type"],
                to_id=to_id,
                properties=relation.get("properties", {}),
                graph_path=graph_path_str,
                confidence=0.8,
                source="sentinel-learner",
                authority_level="observation"
            )
            relation_count += 1

        if relation_count:
            logger.debug(f"_flush_via_skill: {relation_count} relations written (idempotent)")
            print(f"  │ 关系写入: {relation_count} 条 (幂等)")
        logger.info(f"_flush_via_skill: done — {created_count} created, {updated_count} updated, {relation_count} relations")
        print(f"  └─ _flush_via_skill 完成")

    def _flush_batch(self) -> bool:
        if not self._batch_entities and not self._batch_relations:
            return True

        self.graph_path.parent.mkdir(parents=True, exist_ok=True)

        self._flush_via_skill()

        print(f"  ✅ 批量写入完成: {len(self._batch_entities)} 实体, {len(self._batch_relations)} 关系")

        self._batch_entities.clear()
        self._batch_relations.clear()

        return True
    
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
            
            # 4.1 存储页面详细结构（组件、布局、样式等）
            if page_entity:
                self._store_page_structure_detailed_batch(
                    page, 
                    page_entity["id"], 
                    metadata_manager.task_path
                )
                
                # 4.2 存储DOM快照
                self._store_dom_snapshots_batch(
                    page_entity["id"],
                    metadata_manager.task_path
                )
                
                # 4.3 存储CSS系统和设计令牌
                self._store_css_system_batch(
                    page_entity["id"],
                    metadata_manager.task_path
                )
        
        # 5. 存储业务实体
        print(f"  准备存储 {len(task_result.entities)} 个业务实体...")
        for i, entity in enumerate(task_result.entities):
            try:
                # 类型检查
                if isinstance(entity, str):
                    self._fail_counts["unknown"] = self._fail_counts.get("unknown", 0) + 1
                    print(f"    ⚠️ 实体 #{i} 是字符串而非对象: {entity[:50]}...")
                    continue
                if not hasattr(entity, 'name'):
                    self._fail_counts["unknown"] = self._fail_counts.get("unknown", 0) + 1
                    print(f"    ⚠️ 实体 #{i} 缺少 name 属性: {type(entity)}")
                    continue
                self._store_business_entity_batch(entity, system_entity["id"])
            except Exception as e:
                self._fail_counts["business_entity"] = self._fail_counts.get("business_entity", 0) + 1
                print(f"    ⚠️ 存储业务实体 #{i} 失败: {e}")
                continue
        
        # 6. 存储API层（Endpoint + Request + Response + DataFlow）
        self._store_api_layer_batch(
            system_entity["id"],
            metadata_manager.task_path
        )
        
        # 7. 存储用户意图
        self._store_user_intents_batch(
            task_entity["id"],
            metadata_manager.task_path
        )
        
        # 8. 存储业务流程
        self._store_business_flows_batch(
            task_entity["id"],
            system_entity["id"],
            metadata_manager.task_path
        )
        
        # 9. 存储静态资源（聚合模式）
        self._store_resources_batch(
            system_entity["id"],
            metadata_manager.task_path
        )
        
        # 10. 存储浏览器状态（Cookies）
        self._store_browser_state_batch(
            system_entity["id"],
            metadata_manager.task_path
        )
        
        # 11. 存储性能指标和错误
        self._store_performance_batch(
            system_entity["id"],
            metadata_manager.task_path
        )
        self._store_errors_batch(
            system_entity["id"],
            metadata_manager.task_path
        )
        
        # 12. 存储视觉资产
        self._store_visual_assets_batch(
            task_entity["id"],
            metadata_manager.task_path
        )
        
        # 13. 解决冲突
        self._resolve_system_conflicts(system_entity["id"])
        
        # 14. 一次性批量写入所有数据
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
        """批量模式：存储页面知识（含 URL 去重 + Skill 治理更新）"""
        if hasattr(page.overall_confidence, 'value'):
            confidence_value = page.overall_confidence.value
        elif hasattr(page.overall_confidence, 'overall_confidence'):
            confidence_value = str(page.overall_confidence.overall_confidence)
        else:
            confidence_value = str(page.overall_confidence)

        page_url = page.page_info.url
        page_props = {
            "url": page_url,
            "title": page.page_info.title,
            "page_type": page.page_info.page_type,
            "domain": page.page_info.business_domain,
            "confidence": confidence_value
        }

        existing = self._query_existing_page(page_url)
        if existing:
            print(f"  📄 WebPage 已存在: {page_url} → 复用已有实体")
            self._create_relation_batch(from_id=task_id, rel_type="recorded",
                                        to_id=existing["id"])
            self._create_relation_batch(from_id=system_id, rel_type="has_page",
                                        to_id=existing["id"])
            return existing

        page_entity = self._create_entity_batch(
            entity_type="WebPage",
            properties=page_props,
            authority="observation"
        )

        self._create_relation_batch(
            from_id=task_id,
            rel_type="recorded",
            to_id=page_entity["id"]
        )
        self._create_relation_batch(
            from_id=system_id,
            rel_type="has_page",
            to_id=page_entity["id"]
        )
        return page_entity

    def _query_existing_page(self, page_url: str) -> Optional[Dict]:
        if not self.graph_path.exists():
            return None
        for entity in self._load_entity_map_indexed().values():
            if entity.get("type") == "WebPage" and \
               entity.get("properties", {}).get("url") == page_url:
                return entity
        return None

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
            except Exception as e:
                logger.warning(f"        ⚠️ 操作失败: {e}")
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
        for comp in components:  # 最多统计100个
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
                self._fail_counts["component"] = self._fail_counts.get("component", 0) + 1
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
        props['name'] = comp.get('name', '')
        props['text_content'] = comp.get('text_content', '')
        props['is_interactive'] = comp.get('is_interactive', False)
        props['depth'] = comp.get('depth', 0)

        # 类名（保留完整列表）
        class_names = comp.get('class_names', [])
        if class_names:
            props['class_names'] = json.dumps(class_names)  # 最多50个类名

        # 属性（完整保留）
        attributes = comp.get('attributes', {})
        if attributes:
            # 截断过长的属性值
            truncated_attrs = {}
            for k, v in attributes.items():
                if isinstance(v, str):
                    truncated_attrs[k] = v
                else:
                    truncated_attrs[k] = str(v)
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
            props['children_ids'] = json.dumps(children_ids)  # 最多100个子组件

        parent_id = comp.get('parent_id', '')
        if parent_id:
            props['parent_id'] = parent_id

        # 事件处理器
        event_handlers = comp.get('event_handlers', [])
        if event_handlers:
            props['event_handlers'] = json.dumps(event_handlers)

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
                self._fail_counts["layout_section"] = self._fail_counts.get("layout_section", 0) + 1
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
                self._fail_counts["layout_relation"] = self._fail_counts.get("layout_relation", 0) + 1
                print(f"        ⚠️ 建立布局区块关系失败: {e}")
                continue

    def _serialize_layout_section(self, section: Dict) -> Dict:
        """序列化布局区块，保留所有属性"""
        props = {}

        # 基础属性
        props['id'] = section.get('id', '')
        props['type'] = section.get('type', 'unknown')
        props['name'] = section.get('name', '')

        # 组件ID列表
        component_ids = section.get('component_ids', [])
        if component_ids:
            props['component_ids'] = json.dumps(component_ids)

        # 父子关系
        parent_id = section.get('parent_section_id', '')
        if parent_id:
            props['parent_section_id'] = parent_id

        child_sections = section.get('child_sections', [])
        if child_sections:
            props['child_sections'] = json.dumps(child_sections)

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
            selector_samples = list(css_rules.keys())

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
                    decl_str = json.dumps(declarations, ensure_ascii=False)
                elif isinstance(declarations, list):
                    decl_str = json.dumps(declarations, ensure_ascii=False)
                else:
                    decl_str = str(declarations)

                rule_props = {
                    "selector": selector,  # 限制选择器长度
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
                    self._fail_counts["css_rule"] = self._fail_counts.get("css_rule", 0) + 1
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
            for color in color_palette:  # 限制数量
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
            for size in font_sizes:  # 限制数量
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
            for font in font_families:  # 限制数量
                if font:
                    token_props = {
                        "token_type": "font_family",
                        "value": font,
                        "name": f"font_{font.replace(' ', '_')}"
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
                resource_props['filename'] = filename
                resource_props['file_path'] = str(resource_file.relative_to(task_path))

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
                self._fail_counts["resource"] = self._fail_counts.get("resource", 0) + 1
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
            props['original_name'] = original_name

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
                    'filename': screenshot_file.name,
                    'file_path': str(screenshot_file.relative_to(task_path)),
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
                self._fail_counts["keyframe"] = self._fail_counts.get("keyframe", 0) + 1
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
                self._fail_counts["dom_snapshot"] = self._fail_counts.get("dom_snapshot", 0) + 1
                print(f"        ⚠️ 存储DOM快照失败: {e}")
                continue

        print(f"        ✅ 成功存储 {stored_count} 个DOM快照")

    def _extract_snapshot_info(self, snapshot_file: Path) -> Dict:
        """提取 snapshot 文件的基本信息"""
        info = {
            'filename': snapshot_file.name,
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

        except Exception as e:
            logger.warning(f"        ⚠️ 提取快照元数据失败: {e}")

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
                    'name': bp.get('name', 'unknown'),
                    'min_width': bp.get('min_width', 0),
                    'max_width': bp.get('max_width', 0),
                    'media_query': bp.get('media_query', '')
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
                self._fail_counts["breakpoint"] = self._fail_counts.get("breakpoint", 0) + 1
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
            except Exception as e:
                logger.warning(f"        ⚠️ 操作失败: {e}")
    
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
    
    # ==================== 新增批量存储方法 ====================
    
    def _store_dom_snapshots_batch(self, page_entity_id: str, task_path: Path):
        """批量模式：存储DOM快照实体"""
        dom_dir = task_path / "dom"
        if not dom_dir.exists():
            return
        
        snapshot_files = list(dom_dir.glob("snapshot_*.json"))
        print(f"    📄 发现 {len(snapshot_files)} 个DOM快照")
        
        for snapshot_file in snapshot_files:
            try:
                info = self._extract_snapshot_info(snapshot_file)
                snapshot_entity = self._create_entity_batch(
                    entity_type="DOMSnapshot",
                    properties=info,
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=page_entity_id,
                    rel_type="has_dom_snapshot",
                    to_id=snapshot_entity["id"]
                )
            except Exception as e:
                print(f"      ⚠️ 存储DOM快照失败: {e}")
    
    def _store_css_system_batch(self, page_entity_id: str, task_path: Path):
        """批量模式：存储CSS系统和设计令牌"""
        structure_file = task_path / "analysis" / "page_structure.json"
        if not structure_file.exists():
            return
        
        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
        except Exception:
            return
        
        # 存储CSS规则（按文件聚合）
        css_rules = structure_data.get('external_css_rules', {})
        if css_rules:
            css_file_entity = self._create_entity_batch(
                entity_type="CSSFile",
                properties={
                    "rule_count": len(css_rules),
                    "selector_samples": json.dumps(list(css_rules.keys())[:20]),
                    "source": "external_css"
                },
                authority="observation"
            )
            self._create_relation_batch(
                from_id=page_entity_id,
                rel_type="has_css",
                to_id=css_file_entity["id"]
            )
        
        # 存储设计令牌
        color_palette = structure_data.get('color_palette', [])
        typography = structure_data.get('typography', {})
        
        # 颜色令牌 - 存储所有颜色
        color_count = 0
        for color in color_palette:
            if color:
                token_entity = self._create_entity_batch(
                    entity_type="DesignToken",
                    properties={
                        "token_type": "color",
                        "value": color,
                        "name": f"color_{color.replace('#', '')}"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=page_entity_id,
                    rel_type="has_design_token",
                    to_id=token_entity["id"]
                )
                color_count += 1
        if color_count > 0:
            print(f"      ✅ 存储 {color_count} 个颜色令牌")
        
        # 字号令牌 - 存储所有字号
        font_size_count = 0
        for size in typography.get('font_sizes', []):
            if size:
                token_entity = self._create_entity_batch(
                    entity_type="DesignToken",
                    properties={
                        "token_type": "font_size",
                        "value": str(size),
                        "name": f"font_size_{size}"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=page_entity_id,
                    rel_type="has_design_token",
                    to_id=token_entity["id"]
                )
                font_size_count += 1
        if font_size_count > 0:
            print(f"      ✅ 存储 {font_size_count} 个字号令牌")
        
        # 字体令牌 - 存储所有字体
        font_family_count = 0
        for font in typography.get('font_families', []):
            if font:
                token_entity = self._create_entity_batch(
                    entity_type="DesignToken",
                    properties={
                        "token_type": "font_family",
                        "value": font,
                        "name": f"font_{font.replace(' ', '_')}"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=page_entity_id,
                    rel_type="has_design_token",
                    to_id=token_entity["id"]
                )
                font_family_count += 1
        if font_family_count > 0:
            print(f"      ✅ 存储 {font_family_count} 个字体令牌")
    
    def _store_api_layer_batch(self, system_entity_id: str, task_path: Path):
        """批量模式：存储API层（Endpoint + Request + Response + DataFlow）"""
        # 读取API流量日志
        api_traffic_file = task_path / "network" / "api_traffic.jsonl"
        api_responses_file = task_path / "network" / "api_responses.json"
        
        if not api_traffic_file.exists() and not api_responses_file.exists():
            return
        
        print(f"    🌐 存储API层知识...")
        
        # 收集端点信息
        endpoints = {}
        requests = []
        
        if api_traffic_file.exists():
            try:
                with open(api_traffic_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            req = json.loads(line)
                            requests.append(req)
                            url = req.get('url', '')
                            if url:
                                parsed = url.split('?')[0]
                                if parsed not in endpoints:
                                    endpoints[parsed] = {
                                        "url": parsed,
                                        "method": req.get('method', 'GET'),
                                        "domain": parsed.split('/')[2] if len(parsed.split('/')) > 2 else '',
                                        "count": 0
                                    }
                                endpoints[parsed]["count"] += 1
            except Exception as e:
                print(f"      ⚠️ 读取API流量失败: {e}")
        
        # 存储端点
        endpoint_entities = {}
        for url, ep_data in endpoints.items():
            ep_entity = self._create_entity_batch(
                entity_type="APIEndpoint",
                properties=ep_data,
                authority="observation"
            )
            endpoint_entities[url] = ep_entity["id"]
            self._create_relation_batch(
                from_id=system_entity_id,
                rel_type="has_api",
                to_id=ep_entity["id"]
            )
        
        # 存储所有请求
        request_count = 0
        for req in requests:
            url = req.get('url', '').split('?')[0]
            req_entity = self._create_entity_batch(
                entity_type="APIRequest",
                properties={
                    "timestamp": req.get('timestamp', 0),
                    "endpoint_url": url,
                    "method": req.get('method', 'GET'),
                    "status": req.get('status', 0),
                    "resource_type": req.get('resourceType', 'xhr')
                },
                authority="observation"
            )
            if url in endpoint_entities:
                self._create_relation_batch(
                    from_id=endpoint_entities[url],
                    rel_type="has_request",
                    to_id=req_entity["id"]
                )
            request_count += 1
        if request_count > 0:
            print(f"      ✅ 存储 {request_count} 个API请求")
        
        # 存储响应
        if api_responses_file.exists():
            try:
                with open(api_responses_file, 'r', encoding='utf-8') as f:
                    responses = json.load(f)
                
                for url, resp in responses.items():
                    base_url = url.split('?')[0]
                    resp_entity = self._create_entity_batch(
                        entity_type="APIResponse",
                        properties={
                            "endpoint_url": base_url,
                            "status": resp.get('status', 0),
                            "headers_summary": json.dumps(list(resp.get('headers', {}).keys())[:10]),
                            "body_structure": type(resp.get('body')).__name__ if resp.get('body') else 'empty',
                            "timestamp": resp.get('timestamp', 0)
                        },
                        authority="observation"
                    )
                    if base_url in endpoint_entities:
                        self._create_relation_batch(
                            from_id=endpoint_entities[base_url],
                            rel_type="has_response",
                            to_id=resp_entity["id"]
                        )
            except Exception as e:
                print(f"      ⚠️ 读取API响应失败: {e}")
    
    def _store_user_intents_batch(self, task_entity_id: str, task_path: Path):
        """批量模式：存储用户意图"""
        manifest_file = task_path / "training_manifest.jsonl"
        if not manifest_file.exists():
            return
        
        print(f"    🎯 存储用户意图...")
        intent_count = 0
        
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        intents = event.get('_metadata', {}).get('user_intents', [])
                        action = event.get('event_details', {}).get('action', 'unknown')
                        
                        # 存储该事件的所有意图
                        for intent in intents:
                            intent_entity = self._create_entity_batch(
                                entity_type="UserIntent",
                                properties={
                                    "timestamp": event.get('timestamp', 0),
                                    "action_type": action,
                                    "intent_description": intent,
                                    "target_element": event.get('event_details', {}).get('semantic_label', ''),
                                    "confidence": 0.8
                                },
                                authority="inference"
                            )
                            self._create_relation_batch(
                                from_id=task_entity_id,
                                rel_type="has_intent",
                                to_id=intent_entity["id"]
                            )
                            intent_count += 1
        except Exception as e:
            print(f"      ⚠️ 读取用户意图失败: {e}")
    
    def _store_business_flows_batch(self, task_entity_id: str, system_entity_id: str, task_path: Path):
        """批量模式：存储业务流程"""
        # 尝试从analysis_results读取
        analysis_file = task_path / "analysis" / "analysis_results.json"
        if not analysis_file.exists():
            return
        
        print(f"    🔄 存储业务流程...")
        
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis = json.load(f)
            
            flows = analysis.get('manifest', {}).get('business_flows', [])
            
            flow_count = 0
            step_count = 0
            for flow in flows:
                flow_entity = self._create_entity_batch(
                    entity_type="BusinessFlow",
                    properties={
                        "name": flow.get('name', 'Unknown'),
                        "description": flow.get('description', ''),
                        "start_url": flow.get('start_url', ''),
                        "end_url": flow.get('end_url', ''),
                        "steps_count": len(flow.get('steps', [])),
                        "total_duration_ms": flow.get('total_duration_ms', 0)
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=task_entity_id,
                    rel_type="has_flow",
                    to_id=flow_entity["id"]
                )
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_flow",
                    to_id=flow_entity["id"]
                )
                flow_count += 1
                
                # 存储所有流程步骤
                for i, step in enumerate(flow.get('steps', [])):
                    step_entity = self._create_entity_batch(
                        entity_type="FlowStep",
                        properties={
                            "flow_id": flow_entity["id"],
                            "step_index": i,
                            "action": step.get('action', 'unknown'),
                            "timestamp": step.get('timestamp', 0),
                            "url": step.get('url', '')
                        },
                        authority="observation"
                    )
                    self._create_relation_batch(
                        from_id=flow_entity["id"],
                        rel_type="has_step",
                        to_id=step_entity["id"]
                    )
                    step_count += 1
            if flow_count > 0:
                print(f"      ✅ 存储 {flow_count} 个业务流程, {step_count} 个步骤")
        except Exception as e:
            print(f"      ⚠️ 读取业务流程失败: {e}")
    
    def _store_resources_batch(self, system_entity_id: str, task_path: Path):
        """批量模式：存储静态资源（按类型聚合）"""
        resources_dir = task_path / "network" / "resources"
        if not resources_dir.exists():
            return
        
        print(f"    📦 存储静态资源...")
        
        # 按类型统计
        type_stats = {}
        type_mapping = {
            'css': 'stylesheet', 'js': 'script', 'png': 'image', 'jpg': 'image',
            'jpeg': 'image', 'gif': 'image', 'svg': 'image', 'woff': 'font',
            'woff2': 'font', 'ttf': 'font', 'html': 'document', 'json': 'data'
        }
        
        for resource_file in resources_dir.iterdir():
            ext = resource_file.suffix.lower().lstrip('.')
            res_type = type_mapping.get(ext, 'other')
            
            if res_type not in type_stats:
                type_stats[res_type] = {"count": 0, "total_size": 0, "files": []}
            
            type_stats[res_type]["count"] += 1
            try:
                type_stats[res_type]["total_size"] += resource_file.stat().st_size
            except Exception as e:
                logger.warning(f"        ⚠️ 操作失败: {e}")
            type_stats[res_type]["files"].append(resource_file.name)
        
        # 创建聚合实体
        for res_type, stats in type_stats.items():
            resource_entity = self._create_entity_batch(
                entity_type="ResourceGroup",
                properties={
                    "resource_type": res_type,
                    "count": stats["count"],
                    "total_size": stats["total_size"],
                    "sample_files": json.dumps(stats["files"])
                },
                authority="observation"
            )
            self._create_relation_batch(
                from_id=system_entity_id,
                rel_type="has_resource",
                to_id=resource_entity["id"]
            )
    
    def _store_browser_state_batch(self, system_entity_id: str, task_path: Path):
        """批量模式：存储浏览器状态（Cookies）"""
        browser_state_file = task_path / "sandbox" / "browser_state.json"
        if not browser_state_file.exists():
            return
        
        print(f"    🍪 存储浏览器状态...")
        
        try:
            with open(browser_state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            cookies = state.get('cookies', [])
            
            # 按domain聚合
            domain_cookies = {}
            for cookie in cookies:
                domain = cookie.get('domain', 'unknown')
                if domain not in domain_cookies:
                    domain_cookies[domain] = []
                domain_cookies[domain].append(cookie)
            
            # 存储domain
            for domain, domain_cookies_list in domain_cookies.items():
                domain_entity = self._create_entity_batch(
                    entity_type="CookieDomain",
                    properties={
                        "domain": domain,
                        "cookie_count": len(domain_cookies_list),
                        "security_level": "standard"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_cookie_domain",
                    to_id=domain_entity["id"]
                )
                
                # 存储该domain的所有cookie
                cookie_count = 0
                for cookie in domain_cookies_list:
                    cookie_entity = self._create_entity_batch(
                        entity_type="Cookie",
                        properties={
                            "name": cookie.get('name', ''),
                            "value": cookie.get('value', ''),
                            "domain": domain,
                            "path": cookie.get('path', '/'),
                            "secure": cookie.get('secure', False),
                            "httpOnly": cookie.get('httpOnly', False),
                            "session": cookie.get('session', False),
                            "sameSite": cookie.get('sameSite', 'unspecified')
                        },
                        authority="observation"
                    )
                    self._create_relation_batch(
                        from_id=domain_entity["id"],
                        rel_type="has_cookie",
                        to_id=cookie_entity["id"]
                    )
                    cookie_count += 1
                if cookie_count > 0:
                    print(f"      ✅ Domain {domain}: {cookie_count} 个Cookie")
        except Exception as e:
            print(f"      ⚠️ 读取浏览器状态失败: {e}")
    
    def _store_performance_batch(self, system_entity_id: str, task_path: Path):
        """批量模式：存储性能指标"""
        analysis_file = task_path / "analysis" / "analysis_results.json"
        if not analysis_file.exists():
            return
        
        print(f"    ⚡ 存储性能指标...")
        
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis = json.load(f)
            
            # 视频性能
            video_metrics = analysis.get('video', {}).get('performance_metrics', {})
            if video_metrics:
                for metric_type, value in video_metrics.items():
                    perf_entity = self._create_entity_batch(
                        entity_type="PerformanceMetric",
                        properties={
                            "metric_type": f"video_{metric_type}",
                            "value": str(value),
                            "unit": self._get_metric_unit(metric_type),
                            "source": "video_analysis"
                        },
                        authority="observation"
                    )
                    self._create_relation_batch(
                        from_id=system_entity_id,
                        rel_type="has_performance_metric",
                        to_id=perf_entity["id"]
                    )
            
            # 资源性能
            resource_metrics = analysis.get('resources', {})
            if resource_metrics:
                perf_entity = self._create_entity_batch(
                    entity_type="PerformanceMetric",
                    properties={
                        "metric_type": "resource_total",
                        "value": str(resource_metrics.get('total_count', 0)),
                        "unit": "count",
                        "source": "resource_analysis"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_performance_metric",
                    to_id=perf_entity["id"]
                )
            
            # 优化建议 - 存储所有建议
            suggestions = resource_metrics.get('optimization_suggestions', [])
            suggestion_count = 0
            for suggestion in suggestions:
                opt_entity = self._create_entity_batch(
                    entity_type="OptimizationSuggestion",
                    properties={
                        "category": suggestion.get('category', 'general'),
                        "description": suggestion.get('description', ''),
                        "severity": suggestion.get('severity', 'info'),
                        "affected_resources": json.dumps(suggestion.get('affected_resources', []))
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_optimization",
                    to_id=opt_entity["id"]
                )
                suggestion_count += 1
            if suggestion_count > 0:
                print(f"      ✅ 存储 {suggestion_count} 个优化建议")
        except Exception as e:
            print(f"      ⚠️ 读取性能指标失败: {e}")
    
    def _get_metric_unit(self, metric_type: str) -> str:
        """获取指标单位"""
        unit_map = {
            'duration': 'seconds',
            'fps': 'fps',
            'frame_count': 'frames',
            'event_count': 'events',
            'event_density': 'events/second',
            'scroll_count': 'times',
            'avg_scroll_duration': 'ms',
            'interaction_latency_avg': 'ms',
            'interaction_latency_max': 'ms'
        }
        return unit_map.get(metric_type, 'unknown')
    
    def _store_errors_batch(self, system_entity_id: str, task_path: Path):
        """批量模式：存储JS错误"""
        errors_file = task_path / "logs" / "errors.json"
        if not errors_file.exists():
            return
        
        print(f"    ❌ 存储错误信息...")
        
        try:
            with open(errors_file, 'r', encoding='utf-8') as f:
                errors_data = json.load(f)
            
            errors = errors_data.get('errors', [])
            error_count = 0
            for error in errors:
                error_entity = self._create_entity_batch(
                    entity_type="JSError",
                    properties={
                        "type": error.get('type', 'unknown'),
                        "message": error.get('message', ''),
                        "timestamp": error.get('timestamp', 0),
                        "url": error.get('url', ''),
                        "severity": error.get('severity', 'error')
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=system_entity_id,
                    rel_type="has_error",
                    to_id=error_entity["id"]
                )
                error_count += 1
            if error_count > 0:
                print(f"      ✅ 存储 {error_count} 个错误")
        except Exception as e:
            print(f"      ⚠️ 读取错误信息失败: {e}")
    
    def _store_visual_assets_batch(self, task_entity_id: str, task_path: Path):
        """批量模式：存储视觉资产（关键帧、长截图、原型）"""
        print(f"    🖼️ 存储视觉资产...")
        
        # 关键帧 - 存储所有关键帧文件路径
        keyframes_dir = task_path / "analysis" / "enhanced_final"
        if keyframes_dir.exists():
            keyframe_files = list(keyframes_dir.glob("*.png")) + list(keyframes_dir.glob("*.jpg"))
            if keyframe_files:
                # 分批存储文件路径（避免单个实体过大）
                batch_size = 50
                for i in range(0, len(keyframe_files), batch_size):
                    batch = keyframe_files[i:i+batch_size]
                    keyframe_collection = self._create_entity_batch(
                        entity_type="KeyframeCollection",
                        properties={
                            "batch_index": i // batch_size,
                            "count": len(batch),
                            "total_count": len(keyframe_files),
                            "file_paths": json.dumps([str(f.relative_to(task_path)) for f in batch]),
                            "directory": "analysis/enhanced_final"
                        },
                        authority="observation"
                    )
                    self._create_relation_batch(
                        from_id=task_entity_id,
                        rel_type="has_keyframe_collection",
                        to_id=keyframe_collection["id"]
                    )
                print(f"      ✅ 存储 {len(keyframe_files)} 个关键帧（分 {(len(keyframe_files) + batch_size - 1) // batch_size} 批）")
        
        # 长截图 - 存储所有
        long_screenshots = list(task_path.glob("analysis/*_long_screenshot*.png"))
        if long_screenshots:
            screenshot_count = 0
            for screenshot in long_screenshots:
                ss_entity = self._create_entity_batch(
                    entity_type="LongScreenshot",
                    properties={
                        "file_path": str(screenshot.relative_to(task_path)),
                        "type": "long_screenshot"
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=task_entity_id,
                    rel_type="has_screenshot",
                    to_id=ss_entity["id"]
                )
                screenshot_count += 1
            if screenshot_count > 0:
                print(f"      ✅ 存储 {screenshot_count} 个长截图")
        
        # 原型Demo - 存储所有
        prototype_files = list(task_path.glob("analysis/prototype_*.html"))
        if prototype_files:
            proto_count = 0
            for proto in prototype_files:
                proto_entity = self._create_entity_batch(
                    entity_type="PrototypeDemo",
                    properties={
                        "file_path": str(proto.relative_to(task_path)),
                        "generated_at": proto.stat().st_mtime if proto.exists() else 0
                    },
                    authority="observation"
                )
                self._create_relation_batch(
                    from_id=task_entity_id,
                    rel_type="has_prototype",
                    to_id=proto_entity["id"]
                )
                proto_count += 1
            if proto_count > 0:
                print(f"      ✅ 存储 {proto_count} 个原型Demo")
    
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
            "pages": [p.get("properties", {}).get("url", "") for p in pages]
        }

    # ==================== Layer3 系统分析存储 ====================

    def store_layer3_analysis(self, task_id: str, system_id: str,
                              analysis_file: str):
        """将 Layer 3 LLM 分析结果写入知识图谱"""
        t0 = time.time()
        analysis_path = Path(analysis_file)
        if not analysis_path.exists():
            print(f"  ⚠️ Layer 3 分析文件不存在: {analysis_file}")
            return

        try:
            with open(analysis_path, 'r', encoding='utf-8') as f:
                analysis = json.load(f)
        except Exception as e:
            print(f"  ⚠️ 读取 Layer 3 分析失败: {e}")
            return

        system_name = analysis.get("system_name", "")
        entity_count = 0

        # 存储功能模块
        for module in analysis.get("functional_modules", []):
            module_entity = self._create_entity_batch(
                entity_type="FunctionalModule",
                properties={
                    "name": module.get("name", ""),
                    "purpose": module.get("purpose", ""),
                    "system": system_name,
                    "pages": module.get("pages", []),
                    "source_task": task_id
                },
                authority="observation"
            )
            self._create_relation_batch(from_id=system_id, rel_type="has_module",
                                        to_id=module_entity["id"])

        # 存储数据流
        for flow in analysis.get("data_flows", []):
            flow_entity = self._create_entity_batch(
                entity_type="DataFlow",
                properties={
                    "api": flow.get("api", ""),
                    "purpose": flow.get("purpose", ""),
                    "system": system_name,
                    "renders_to": flow.get("renders_to", ""),
                    "data_fields": flow.get("data_fields", []),
                    "source_task": task_id
                },
                authority="observation"
            )
            self._create_relation_batch(from_id=system_id, rel_type="has_data_flow",
                                        to_id=flow_entity["id"])

        # 存储用户路径
        for path in analysis.get("user_paths", []):
            self._create_entity_batch(
                entity_type="UserPath",
                properties={
                    "name": path.get("name", ""),
                    "steps": path.get("steps", []),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        # 存储导航关系图
        for nav in analysis.get("navigation_graph", []):
            nav_entity = self._create_entity_batch(
                entity_type="Navigation",
                properties={
                    "from_page": nav.get("from", ""),
                    "to_page": nav.get("to", ""),
                    "trigger": nav.get("trigger", ""),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )
            self._create_relation_batch(from_id=system_id, rel_type="has_navigation",
                                        to_id=nav_entity["id"])

        # 存储数据实体
        for entity_data in analysis.get("data_entities", []):
            entity = self._create_entity_batch(
                entity_type="DataEntity",
                properties={
                    "name": entity_data.get("name", ""),
                    "fields": entity_data.get("fields", []),
                    "related_apis": entity_data.get("related_apis", []),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )
            self._create_relation_batch(from_id=system_id, rel_type="has_data_entity",
                                        to_id=entity["id"])

        # 存储设计系统
        design = analysis.get("design_system", {})
        if design:
            design_entity = self._create_entity_batch(
                entity_type="DesignSystem",
                properties={
                    "colors": design.get("colors", []),
                    "fonts": design.get("fonts", []),
                    "component_framework": design.get("component_framework", ""),
                    "icon_style": design.get("icon_style", ""),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )
            self._create_relation_batch(from_id=system_id, rel_type="has_design_system",
                                        to_id=design_entity["id"])

        # 存储交互模式
        for pattern in analysis.get("interaction_patterns", []):
            self._create_entity_batch(
                entity_type="InteractionPattern",
                properties={
                    "name": pattern.get("name", ""),
                    "description": pattern.get("description", ""),
                    "occurs_in": pattern.get("occurs_in", []),
                    "states": pattern.get("states", []),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        # 存储 API contracts
        for contract in analysis.get("api_contracts", []):
            self._create_entity_batch(
                entity_type="APIContract",
                properties={
                    "endpoint": contract.get("endpoint", ""),
                    "method": contract.get("method", "GET"),
                    "auth_required": contract.get("authentication_required", False),
                    "request_schema": contract.get("request_schema", {}),
                    "response_schema": contract.get("response_schema", {}),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        # 存储 tech_stack
        tech_stack = analysis.get("tech_stack", [])
        if tech_stack:
            self._create_entity_batch(
                entity_type="TechStack",
                properties={
                    "technologies": tech_stack if isinstance(tech_stack, list) else [tech_stack],
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        # 存储 user_roles
        for role in analysis.get("user_roles", []):
            self._create_entity_batch(
                entity_type="UserRole",
                properties={
                    "name": role.get("name", ""),
                    "permissions": role.get("permissions", []),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        # 存储优化建议
        for opt in analysis.get("optimization_opportunities", []):
            self._create_entity_batch(
                entity_type="OptimizationOpportunity",
                properties={
                    "description": opt.get("description", ""),
                    "priority": opt.get("priority", "medium"),
                    "category": opt.get("category", ""),
                    "system": system_name,
                    "source_task": task_id
                },
                authority="observation"
            )

        print(f"  ✅ Layer 3 分析已存储:")
        print(f"     模块: {len(analysis.get('functional_modules', []))}")
        print(f"     数据流: {len(analysis.get('data_flows', []))}")
        print(f"     用户路径: {len(analysis.get('user_paths', []))}")
        print(f"     导航: {len(analysis.get('navigation_graph', []))}")
        print(f"     数据实体: {len(analysis.get('data_entities', []))}")

        t_total = time.time() - t0
        print(f"  ✅ Layer 3 分析已存储 (耗时:{t_total:.2f}s):")
    def generate_site_model(self, system_name: str) -> Dict:
        """从知识图谱中聚合生成 site_model.json（LLM 消费格式）"""
        model = {
            "system_name": system_name,
            "generated_at": datetime.now().isoformat(),
            "pages": 0,
            "functional_modules": [],
            "data_flows": [],
            "navigation_graph": [],
            "data_entities": [],
            "design_system": {},
            "interaction_patterns": [],
            "user_paths": [],
            "api_contracts": [],
            "tech_stack": [],
            "user_roles": [],
            "optimization_opportunities": []
        }

        entities = self._load_entity_map_indexed()
        if not entities:
            return model

        modules = [e for e in entities.values() if e.get("type") == "FunctionalModule"]
        model["functional_modules"] = [
            {"name": m["properties"].get("name", ""),
             "purpose": m["properties"].get("purpose", ""),
             "pages": m["properties"].get("pages", [])} for m in modules
        ]

        data_flows = [e for e in entities.values() if e.get("type") == "DataFlow"]
        model["data_flows"] = [
            {"api": df["properties"].get("api", ""),
             "purpose": df["properties"].get("purpose", ""),
             "renders_to": df["properties"].get("renders_to", ""),
             "data_fields": df["properties"].get("data_fields", [])} for df in data_flows
        ]

        pages = [e for e in entities.values() if e.get("type") == "WebPage"]
        model["pages"] = len(pages)

        navigations = [e for e in entities.values() if e.get("type") == "Navigation"]
        model["navigation_graph"] = [
            {"from": n["properties"].get("from_page", ""),
             "to": n["properties"].get("to_page", ""),
             "trigger": n["properties"].get("trigger", "")} for n in navigations
        ]

        data_entities = [e for e in entities.values() if e.get("type") == "DataEntity"]
        model["data_entities"] = [
            {"name": de["properties"].get("name", ""),
             "fields": de["properties"].get("fields", [])} for de in data_entities
        ]

        design_systems = [e for e in entities.values() if e.get("type") == "DesignSystem"]
        if design_systems:
            model["design_system"] = design_systems[0].get("properties", {})

        interaction_patterns = [e for e in entities.values() if e.get("type") == "InteractionPattern"]
        model["interaction_patterns"] = [
            {"name": ip["properties"].get("name", ""),
             "description": ip["properties"].get("description", ""),
             "occurs_in": ip["properties"].get("occurs_in", []),
             "states": ip["properties"].get("states", [])} for ip in interaction_patterns
        ]

        user_paths = [e for e in entities.values() if e.get("type") == "UserPath"]
        model["user_paths"] = [
            {"name": up["properties"].get("name", ""),
             "steps": up["properties"].get("steps", [])} for up in user_paths
        ]

        api_contracts = [e for e in entities.values() if e.get("type") == "APIContract"]
        model["api_contracts"] = [
            {"endpoint": ac["properties"].get("endpoint", ""),
             "method": ac["properties"].get("method", "GET"),
             "auth_required": ac["properties"].get("auth_required", False),
             "request_schema": ac["properties"].get("request_schema", {}),
             "response_schema": ac["properties"].get("response_schema", {})} for ac in api_contracts
        ]

        tech_stacks = [e for e in entities.values() if e.get("type") == "TechStack"]
        model["tech_stack"] = tech_stacks[0]["properties"].get("technologies", []) if tech_stacks else []

        user_roles = [e for e in entities.values() if e.get("type") == "UserRole"]
        model["user_roles"] = [
            {"name": ur["properties"].get("name", ""),
             "permissions": ur["properties"].get("permissions", [])} for ur in user_roles
        ]

        optimization_opps = [e for e in entities.values() if e.get("type") == "OptimizationOpportunity"]
        model["optimization_opportunities"] = [
            {"description": oo["properties"].get("description", ""),
             "priority": oo["properties"].get("priority", "medium"),
             "category": oo["properties"].get("category", "")} for oo in optimization_opps
        ]

        return model

    def save_site_model(self, system_name: str):
        """保存 site_model.json 到 memory/ontology 目录"""
        t0 = time.time()
        model = self.generate_site_model(system_name)
        site_model_dir = self.memory_base_path / "memory" / "ontology"
        site_model_dir.mkdir(parents=True, exist_ok=True)
        site_model_path = site_model_dir / "site_model.json"
        with open(site_model_path, 'w', encoding='utf-8') as f:
            json.dump(model, f, ensure_ascii=False, indent=2)
        print(f"  ✅ site_model.json 已保存 ({site_model_path})")
        print(f"    ⏱  site_model 聚合耗时: {time.time() - t0:.3f}s")

    def _log_page_version(self, page_url: str, task_id: str, node_count: int,
                          title: str, system_id: str):
        """记录页面版本到 version_log.jsonl"""
        version_dir = self.memory_base_path / "memory" / "ontology"
        version_dir.mkdir(parents=True, exist_ok=True)
        version_path = version_dir / "version_log.jsonl"
        record = {
            "page_url": page_url,
            "task_id": task_id,
            "node_count": node_count,
            "title": title,
            "system_id": system_id,
            "timestamp": datetime.now().isoformat()
        }
        with open(version_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _record_contribution(self, system_id: str, task_id: str,
                             system_name: str = None):
        """记录贡献溯源到 contribution_map.jsonl"""
        contrib_dir = self.memory_base_path / "memory" / "ontology"
        contrib_dir.mkdir(parents=True, exist_ok=True)
        contrib_path = contrib_dir / "contribution_map.jsonl"
        record = {
            "system_id": system_id,
            "system_name": system_name or "unknown",
            "task_id": task_id,
            "level": "system",
            "timestamp": datetime.now().isoformat()
        }
        with open(contrib_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _record_page_contribution(self, page_url: str, page_entity_id: str,
                                   task_id: str, system_id: str):
        """记录页面级别贡献溯源"""
        contrib_dir = self.memory_base_path / "memory" / "ontology"
        contrib_dir.mkdir(parents=True, exist_ok=True)
        contrib_path = contrib_dir / "contribution_map.jsonl"
        record = {
            "page_url": page_url,
            "page_entity_id": page_entity_id,
            "task_id": task_id,
            "system_id": system_id,
            "level": "page",
            "timestamp": datetime.now().isoformat()
        }
        with open(contrib_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _query_existing_system(self, system_name: str) -> Optional[Dict]:
        """从已有 graph.jsonl 中查询 System 实体"""
        if not self.graph_path.exists():
            return None
        for entity in self._load_entity_map_indexed().values():
            if entity.get("type") == "System" and \
               entity.get("properties", {}).get("name") == system_name:
                return entity
        return None
