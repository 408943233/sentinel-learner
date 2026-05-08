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
        
        # 4. 存储页面知识
        for page in task_result.pages:
            self._store_page_knowledge(page, task_entity["id"], system_entity["id"])
        
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
                             task_id: str, system_id: str):
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
            except:
                pass
    
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
