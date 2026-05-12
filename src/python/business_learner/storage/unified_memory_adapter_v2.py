"""
统一Memory适配器 - V2 扩展版
支持本地模式和服务器模式
与OpenClaw Memory Skill集成

V2 更新：
- 添加 P0/P1/P2 完整实体类型支持
- 实现数据聚合策略避免图谱爆炸
- 覆盖率目标：3.8% → 80%+
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
    统一内存适配器 V2
    
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
    
    # ==================== V2 新增：完整实体类型映射 ====================
    
    def _map_entity_type(self, entity_type: str) -> str:
        """
        映射实体类型到skill类型
        
        V2 扩展：支持 P0/P1/P2 所有实体类型
        """
        type_mapping = {
            # P0 - 核心实体
            "announcement": "Document",
            "recruitment": "Task",
            "product": "Product",
            "service": "Service",
            "generic": "Entity",
            
            # P0 - DOM结构
            "dom_snapshot": "DOMSnapshot",
            "component": "Component",
            "component_group": "ComponentGroup",
            
            # P0 - CSS系统
            "css_rule": "CSSRule",
            "css_file": "CSSFile",
            "design_token": "DesignToken",
            
            # P0 - API层
            "api_endpoint": "APIEndpoint",
            "api_request": "APIRequest",
            "api_response": "APIResponse",
            "data_flow": "DataFlow",
            "api_schema": "APISchema",
            
            # P0 - 业务逻辑
            "user_intent": "UserIntent",
            "business_flow": "BusinessFlow",
            "flow_step": "FlowStep",
            
            # P1 - 静态资源
            "resource": "Resource",
            "resource_group": "ResourceGroup",
            
            # P1 - 浏览器状态
            "cookie": "Cookie",
            "cookie_domain": "CookieDomain",
            
            # P1 - 性能与错误
            "performance_metric": "PerformanceMetric",
            "optimization_suggestion": "OptimizationSuggestion",
            "js_error": "JSError",
            "anchor_event": "AnchorEvent",
            
            # P1 - 事件
            "rrweb_event": "RrwebEvent",
            "rrweb_event_group": "RrwebEventGroup",
            
            # P2 - 视觉资产
            "keyframe": "Keyframe",
            "keyframe_collection": "KeyframeCollection",
            "long_screenshot": "LongScreenshot",
            "prototype_demo": "PrototypeDemo",
        }
        return type_mapping.get(entity_type, "Entity")
    
    # ==================== V2 新增：DOM快照存储 ====================
    
    def _store_dom_snapshots_batch(self, page, page_entity_id: str, task_path: Path):
        """
        存储DOM快照（P0）
        
        从 dom/snapshot_*.json 文件读取
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
                snapshot_type = "full" if snapshot_data.get("rrwebEvent") else "incremental"
                
                props = {
                    "timestamp": snapshot_data.get("timestamp", 0),
                    "url": snapshot_data.get("url", ""),
                    "type": snapshot_type,
                    "element_count": len(snapshot_data.get("components", [])),
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
                    properties={"captured_at": props["timestamp"]}
                )
                
                stored_count += 1
            except Exception as e:
                print(f"      ⚠️ 存储快照失败 {snapshot_file.name}: {e}")
        
        print(f"      ✅ 成功存储 {stored_count} 个DOM快照")
    
    # ==================== V2 新增：组件存储（聚合模式）====================
    
    def _store_components_batch(self, page, page_entity_id: str, task_path: Path):
        """
        存储组件（P0）- 聚合模式
        
        621个组件 → 每页1个ComponentGroup聚合实体
        """
        # 从 page_structure.json 读取
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
            with_text_count = 0
            
            # 提取关键交互组件（限制数量）
            key_components = []
            
            for comp in components[:100]:  # 最多处理100个，避免过大
                tag = comp.get("tag", "unknown")
                tag_distribution[tag] = tag_distribution.get(tag, 0) + 1
                
                if comp.get("is_interactive"):
                    interactive_count += 1
                if comp.get("styles"):
                    with_styles_count += 1
                if comp.get("text_content"):
                    with_text_count += 1
                
                # 保存关键交互组件详情
                if comp.get("is_interactive") and len(key_components) < 20:
                    key_components.append({
                        "id": comp.get("id", ""),
                        "tag": tag,
                        "class_names": comp.get("class_names", [])[:5],  # 限制数量
                        "text_content": comp.get("text_content", "")[:100],  # 限制长度
                        "is_interactive": True
                    })
            
            # 创建聚合实体
            props = {
                "page_url": page.url if hasattr(page, 'url') else "",
                "total_components": len(components),
                "tag_distribution": tag_distribution,
                "interactive_count": interactive_count,
                "with_styles_count": with_styles_count,
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
    
    # ==================== V2 新增：CSS系统存储 ====================
    
    def _store_css_system_batch(self, page, page_entity_id: str, task_path: Path):
        """
        存储CSS系统和设计令牌（P0）
        
        - CSS规则按文件聚合
        - 设计令牌单独存储
        """
        structure_file = task_path / "analysis" / "page_structure.json"
        if not structure_file.exists():
            return
        
        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                structure_data = json.load(f)
            
            # 1. 存储CSS文件（聚合）
            css_rules = structure_data.get("external_css_rules", [])
            if css_rules:
                print(f"    存储CSS规则: {len(css_rules)} 条")
                
                # 按文件分组
                files_map = {}
                for rule in css_rules[:500]:  # 限制处理数量
                    source_file = rule.get("source_file", "unknown.css")
                    if source_file not in files_map:
                        files_map[source_file] = []
                    files_map[source_file].append(rule)
                
                # 每个CSS文件创建一个聚合实体
                for file_name, rules in files_map.items():
                    selectors_sample = [r.get("selector", "") for r in rules[:10]]
                    
                    props = {
                        "file_name": file_name,
                        "rule_count": len(rules),
                        "selectors_sample": selectors_sample,
                        "properties_summary": self._summarize_css_properties(rules)
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
                        "type": "color",
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
                        "type": "font_family",
                        "name": font,
                        "value": font
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
        """汇总CSS属性统计"""
        properties_count = {}
        for rule in rules:
            for prop in rule.get("properties", {}).keys():
                properties_count[prop] = properties_count.get(prop, 0) + 1
        
        # 返回最常见的10个属性
        sorted_props = sorted(properties_count.items(), key=lambda x: x[1], reverse=True)
        return {k: v for k, v in sorted_props[:10]}
