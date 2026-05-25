"""
OpenClaw Memory Skill 适配器
桥接 openclaw-memory-skill 和增强记忆系统
"""

import os
import sys
from typing import List, Dict, Optional, Any
from pathlib import Path

def _find_skill_path() -> Path:
    """按优先级查找 openclaw-memory-skill 目录"""
    candidates = []

    env_path = os.environ.get("OPENCLAW_SKILL_PATH") or os.environ.get("OPENCLAW_MEMORY_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(Path.home() / ".openclaw" / "extensions" / "openclaw-memory-skill")

    candidates.append(Path.home() / ".openclaw" / "workspace" / "openclaw-memory-skill")

    try:
        cwd = Path.cwd()
        candidates.append(cwd / "openclaw-memory-skill")
        if cwd.name == "sentinel-learner":
            candidates.append(cwd.parent / "openclaw-memory-skill")
        candidates.append(cwd.parent / "openclaw-memory-skill")
    except Exception:
        pass

    for p in candidates:
        script = p / "scripts" / "ontology_optimized.py"
        if script.exists():
            return p

    return candidates[0] if candidates else Path(".")

OPENCLAW_MEMORY_PATH = _find_skill_path()
sys.path.insert(0, str(OPENCLAW_MEMORY_PATH))


class OntologyAdapter:
    """知识图谱适配器"""

    AUTHORITY_LEVELS = {
        "truth": 1,
        "reference": 2,
        "observation": 3,
        "manual": 4
    }

    def __init__(self, graph_path: Optional[str] = None):
        self.graph_path = graph_path or os.path.expanduser(
            "~/.openclaw/workspace/memory/ontology/graph.jsonl"
        )
        self._entity_manager = None
        self._relation_manager = None
        self._graph_query = None
        self._init_attempted = False
        
    def _init_managers(self):
        """初始化管理器"""
        if self._entity_manager is None and not self._init_attempted:
            self._init_attempted = True
            try:
                import importlib.util
                skill_script = OPENCLAW_MEMORY_PATH / "scripts" / "ontology_optimized.py"
                if not skill_script.exists():
                    print(f"[OntologyAdapter] Skill 脚本未找到: {skill_script}，使用降级模式")
                    return

                spec = importlib.util.spec_from_file_location(
                    "ontology_optimized", skill_script
                )
                ontology_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ontology_module)

                self._entity_manager = ontology_module.EntityManager
                self._relation_manager = ontology_module.RelationManager
                self._graph_query = ontology_module.GraphQuery

                Path(self.graph_path).parent.mkdir(parents=True, exist_ok=True)

            except Exception as e:
                print(f"[OntologyAdapter] 初始化失败: {e}")
    
    def create_knowledge_entity(self,
                               content: str,
                               source: str,
                               task_id: str,
                               entity_type: str = "KnowledgeChunk",
                               confidence: float = 0.9,
                               authority_level: str = "observation",
                               metadata: Optional[Dict] = None) -> Optional[str]:
        """
        创建知识实体
        
        Args:
            content: 知识内容
            source: 来源（dom/api/video/etc）
            task_id: 任务ID
            entity_type: 实体类型
            confidence: 置信度
            authority_level: 权威等级
            metadata: 额外元数据
            
        Returns:
            实体ID
        """
        self._init_managers()
        
        if self._entity_manager is None:
            # 降级模式：返回模拟ID
            return f"mock_{hash(content) % 1000000}"
        
        try:
            properties = {
                "content": content[:1000],  # 限制长度
                "source": source,
                "task_id": task_id,
                "content_hash": hash(content) & 0xFFFFFFFF
            }
            
            if metadata:
                properties.update(metadata)
            
            entity = self._entity_manager.create_entity(
                type_name=entity_type,
                properties=properties,
                graph_path=self.graph_path,
                confidence=confidence,
                source=source,
                authority_level=authority_level
            )
            
            return entity.get("id")
        except Exception as e:
            print(f"[OntologyAdapter] 创建实体失败: {e}")
            return None
    
    def query_entities(self,
                      entity_type: Optional[str] = None,
                      filters: Optional[Dict] = None,
                      min_confidence: float = 0.0,
                      include_stale: bool = False) -> List[Dict]:
        """
        查询实体
        
        Args:
            entity_type: 实体类型过滤
            filters: 属性过滤条件
            min_confidence: 最小置信度
            include_stale: 是否包含过期实体
            
        Returns:
            实体列表
        """
        self._init_managers()
        
        if self._graph_query is None:
            return []
        
        try:
            entities = self._graph_query.query_entities(
                type_name=entity_type,
                where=filters or {},
                graph_path=self.graph_path,
                include_stale=include_stale
            )
            
            # 过滤置信度
            if min_confidence > 0:
                entities = [
                    e for e in entities
                    if e.get("metadata", {}).get("confidence", 0) >= min_confidence
                ]
            
            return entities
        except Exception as e:
            print(f"[OntologyAdapter] 查询实体失败: {e}")
            return []
    
    def get_entity_by_content(self, content: str) -> Optional[Dict]:
        """
        根据内容查找实体
        
        Args:
            content: 内容文本
            
        Returns:
            实体字典
        """
        self._init_managers()
        
        if self._graph_query is None:
            return None
        
        try:
            entities = self._graph_query.query_entities(
                type_name="KnowledgeChunk",
                where={"content_hash": hash(content) & 0xFFFFFFFF},
                graph_path=self.graph_path
            )
            
            # 精确匹配内容
            for entity in entities:
                if entity.get("properties", {}).get("content") == content:
                    return entity
            
            return None
        except Exception as e:
            print(f"[OntologyAdapter] 查找实体失败: {e}")
            return None
    
    def create_relationship(self,
                           from_id: str,
                           to_id: str,
                           relation_type: str,
                           properties: Optional[Dict] = None,
                           confidence: float = 0.9) -> bool:
        """
        创建实体关系
        
        Args:
            from_id: 源实体ID
            to_id: 目标实体ID
            relation_type: 关系类型
            properties: 关系属性
            confidence: 置信度
            
        Returns:
            是否成功
        """
        self._init_managers()
        
        if self._relation_manager is None:
            return False
        
        try:
            self._relation_manager.create_relation(
                from_id=from_id,
                rel_type=relation_type,
                to_id=to_id,
                properties=properties or {},
                graph_path=self.graph_path,
                confidence=confidence
            )
            return True
        except Exception as e:
            print(f"[OntologyAdapter] 创建关系失败: {e}")
            return False
    
    def get_related_entities(self,
                            entity_id: str,
                            relation_type: Optional[str] = None,
                            direction: str = "both") -> List[Dict]:
        """
        获取相关实体
        
        Args:
            entity_id: 实体ID
            relation_type: 关系类型过滤
            direction: 方向（outgoing/incoming/both）
            
        Returns:
            相关实体列表
        """
        self._init_managers()
        
        if self._graph_query is None:
            return []
        
        try:
            return self._graph_query.get_related(
                entity_id=entity_id,
                rel_type=relation_type,
                graph_path=self.graph_path,
                direction=direction
            )
        except Exception as e:
            print(f"[OntologyAdapter] 获取相关实体失败: {e}")
            return []
    
    def validate_entity(self, entity: Dict) -> Dict[str, Any]:
        """
        验证实体的权威性和置信度
        
        Args:
            entity: 实体字典
            
        Returns:
            验证结果
        """
        metadata = entity.get("metadata", {})
        confidence = metadata.get("confidence", 0.5)
        authority = metadata.get("authority_level", "manual")
        
        authority_score = 1.0 / self.AUTHORITY_LEVELS.get(authority, 4)
        
        # 综合评分
        overall_score = confidence * 0.6 + authority_score * 0.4
        
        return {
            "confidence": confidence,
            "authority_level": authority,
            "authority_score": authority_score,
            "overall_score": overall_score,
            "is_trustworthy": overall_score >= 0.8 and confidence >= 0.9,
            "recommendation": "accept" if overall_score >= 0.9 else (
                "review" if overall_score >= 0.7 else "reject"
            )
        }
    
    def get_authority_priority(self, authority_level: str) -> int:
        """获取权威等级优先级（数字越小优先级越高）"""
        return self.AUTHORITY_LEVELS.get(authority_level, 4)
