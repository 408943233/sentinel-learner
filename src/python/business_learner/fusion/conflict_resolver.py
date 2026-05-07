"""
冲突检测与解决引擎
处理多源数据冲突
"""

import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from difflib import SequenceMatcher


class ConflictType(Enum):
    """冲突类型"""
    VALUE_MISMATCH = "value_mismatch"  # 值不匹配
    MISSING_IN_SOURCE = "missing_in_source"  # 某源缺失
    TYPE_MISMATCH = "type_mismatch"  # 类型不匹配
    TEMPORAL_MISMATCH = "temporal_mismatch"  # 时间不匹配
    SEMANTIC_MISMATCH = "semantic_mismatch"  # 语义不匹配


class DataSource(Enum):
    """数据源优先级（从高到低）"""
    VIDEO = 1      # 视觉真实 - 最高优先级
    API = 2        # API数据 - 次高优先级
    MANIFEST = 3   # 操作流程 - 中等优先级
    DOM = 4        # DOM结构 - 较低优先级
    RESOURCES = 5  # 静态资源 - 最低优先级


@dataclass
class Conflict:
    """冲突定义"""
    conflict_id: str
    conflict_type: ConflictType
    field_path: str  # 冲突字段路径
    sources_involved: List[DataSource]
    values: Dict[DataSource, Any]  # 各源的值
    confidence: Dict[DataSource, float]  # 各源的可信度
    severity: str  # high, medium, low
    description: str
    resolution: Optional[str] = None
    resolved_value: Any = None


@dataclass
class ConflictResolutionResult:
    """冲突解决结果"""
    total_conflicts: int
    resolved_conflicts: int
    unresolved_conflicts: List[Conflict]
    resolution_log: List[Dict]
    final_data: Dict


class ConflictResolver:
    """冲突解决器"""
    
    def __init__(self, source_priorities: Optional[Dict[DataSource, int]] = None):
        """
        初始化冲突解决器
        
        Args:
            source_priorities: 自定义数据源优先级
        """
        self.priorities = source_priorities or {
            DataSource.VIDEO: 1,
            DataSource.API: 2,
            DataSource.MANIFEST: 3,
            DataSource.DOM: 4,
            DataSource.RESOURCES: 5
        }
        
        self.conflicts: List[Conflict] = []
        self.resolution_log: List[Dict] = []
    
    def detect_and_resolve(self, 
                          data_sources: Dict[DataSource, Dict],
                          alignment_map: Optional[Dict] = None) -> ConflictResolutionResult:
        """
        检测并解决冲突
        
        Args:
            data_sources: 各数据源的数据
            alignment_map: 时间对齐映射
            
        Returns:
            解决结果
        """
        print("  [冲突解决] 检测冲突...")
        self.conflicts = self._detect_conflicts(data_sources, alignment_map)
        print(f"    发现 {len(self.conflicts)} 个冲突")
        
        print("  [冲突解决] 解决冲突...")
        resolved = 0
        for conflict in self.conflicts:
            if self._resolve_conflict(conflict):
                resolved += 1
        
        print(f"    已解决 {resolved}/{len(self.conflicts)} 个冲突")
        
        # 合并最终数据
        final_data = self._merge_final_data(data_sources)
        
        return ConflictResolutionResult(
            total_conflicts=len(self.conflicts),
            resolved_conflicts=resolved,
            unresolved_conflicts=[c for c in self.conflicts if not c.resolution],
            resolution_log=self.resolution_log,
            final_data=final_data
        )
    
    def _detect_conflicts(self, 
                         data_sources: Dict[DataSource, Dict],
                         alignment_map: Optional[Dict]) -> List[Conflict]:
        """检测冲突"""
        conflicts = []
        
        # 获取所有可能的字段路径
        all_paths = self._extract_all_paths(data_sources)
        
        for path in all_paths:
            # 获取各源在该路径的值
            values = {}
            confidences = {}
            
            for source, data in data_sources.items():
                value, confidence = self._get_value_at_path(data, path)
                if value is not None:
                    values[source] = value
                    confidences[source] = confidence
            
            # 如果多个源都有值，检查是否冲突
            if len(values) > 1:
                conflict = self._check_conflict(path, values, confidences)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _extract_all_paths(self, data_sources: Dict[DataSource, Dict]) -> List[str]:
        """提取所有字段路径"""
        paths = set()
        
        for source, data in data_sources.items():
            source_paths = self._extract_paths_recursive(data, "")
            paths.update(source_paths)
        
        return sorted(list(paths))
    
    def _extract_paths_recursive(self, data: Any, prefix: str) -> List[str]:
        """递归提取路径"""
        paths = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{prefix}.{key}" if prefix else key
                paths.append(current_path)
                paths.extend(self._extract_paths_recursive(value, current_path))
        elif isinstance(data, list) and data:
            # 只处理列表的第一项作为模板
            paths.extend(self._extract_paths_recursive(data[0], f"{prefix}[]"))
        
        return paths
    
    def _get_value_at_path(self, data: Dict, path: str) -> Tuple[Any, float]:
        """获取指定路径的值和可信度"""
        parts = path.split(".")
        current = data
        
        try:
            for part in parts:
                if part.endswith("[]"):
                    part = part[:-2]
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                        if isinstance(current, list) and current:
                            current = current[0]
                    else:
                        return None, 0.0
                else:
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        return None, 0.0
            
            # 返回值的默认可信度
            return current, 0.8
        except:
            return None, 0.0
    
    def _check_conflict(self, 
                       path: str, 
                       values: Dict[DataSource, Any],
                       confidences: Dict[DataSource, float]) -> Optional[Conflict]:
        """检查是否存在冲突"""
        # 获取所有值
        value_list = list(values.values())
        
        # 检查值是否相同
        if self._values_equal(value_list):
            return None
        
        # 确定冲突类型
        conflict_type = self._determine_conflict_type(value_list)
        
        # 确定严重程度
        severity = self._determine_severity(path, conflict_type)
        
        # 生成描述
        description = self._generate_conflict_description(path, values)
        
        return Conflict(
            conflict_id=f"conflict_{len(self.conflicts)}",
            conflict_type=conflict_type,
            field_path=path,
            sources_involved=list(values.keys()),
            values=values,
            confidence=confidences,
            severity=severity,
            description=description
        )
    
    def _values_equal(self, values: List[Any]) -> bool:
        """检查值是否相等"""
        if len(values) < 2:
            return True
        
        first = values[0]
        for v in values[1:]:
            if not self._value_equal(first, v):
                return False
        
        return True
    
    def _value_equal(self, v1: Any, v2: Any) -> bool:
        """比较两个值是否相等"""
        if type(v1) != type(v2):
            return False
        
        if isinstance(v1, str):
            # 字符串相似度比较
            similarity = SequenceMatcher(None, v1, v2).ratio()
            return similarity > 0.9
        
        return v1 == v2
    
    def _determine_conflict_type(self, values: List[Any]) -> ConflictType:
        """确定冲突类型"""
        types = [type(v) for v in values]
        
        # 检查类型是否一致
        if len(set(types)) > 1:
            return ConflictType.TYPE_MISMATCH
        
        # 检查时间相关
        if any(isinstance(v, (int, float)) for v in values):
            return ConflictType.TEMPORAL_MISMATCH
        
        # 检查语义（字符串）
        if all(isinstance(v, str) for v in values):
            return ConflictType.SEMANTIC_MISMATCH
        
        return ConflictType.VALUE_MISMATCH
    
    def _determine_severity(self, path: str, conflict_type: ConflictType) -> str:
        """确定冲突严重程度"""
        # 关键字段
        critical_fields = ['page_type', 'business_domain', 'url', 'title']
        
        if any(cf in path for cf in critical_fields):
            return 'high'
        
        if conflict_type in [ConflictType.TYPE_MISMATCH, ConflictType.TEMPORAL_MISMATCH]:
            return 'high'
        
        if conflict_type == ConflictType.SEMANTIC_MISMATCH:
            return 'medium'
        
        return 'low'
    
    def _generate_conflict_description(self, 
                                      path: str, 
                                      values: Dict[DataSource, Any]) -> str:
        """生成冲突描述"""
        parts = [f"字段 '{path}' 存在冲突:"]
        for source, value in values.items():
            parts.append(f"  {source.value}={value}")
        return "\n".join(parts)
    
    def _resolve_conflict(self, conflict: Conflict) -> bool:
        """解决单个冲突"""
        resolution_strategy = self._select_resolution_strategy(conflict)
        
        if resolution_strategy == "priority":
            return self._resolve_by_priority(conflict)
        elif resolution_strategy == "confidence":
            return self._resolve_by_confidence(conflict)
        elif resolution_strategy == "merge":
            return self._resolve_by_merge(conflict)
        else:
            return self._resolve_by_priority(conflict)  # 默认使用优先级
    
    def _select_resolution_strategy(self, conflict: Conflict) -> str:
        """选择解决策略"""
        if conflict.conflict_type == ConflictType.SEMANTIC_MISMATCH:
            return "merge"
        elif conflict.conflict_type == ConflictType.TEMPORAL_MISMATCH:
            return "confidence"
        else:
            return "priority"
    
    def _resolve_by_priority(self, conflict: Conflict) -> bool:
        """基于优先级解决"""
        # 按优先级排序源
        sorted_sources = sorted(
            conflict.sources_involved,
            key=lambda s: self.priorities.get(s, 999)
        )
        
        # 选择最高优先级的值
        best_source = sorted_sources[0]
        conflict.resolved_value = conflict.values[best_source]
        conflict.resolution = f"基于优先级选择 {best_source.value} 的值"
        
        self.resolution_log.append({
            "conflict_id": conflict.conflict_id,
            "strategy": "priority",
            "selected_source": best_source.value,
            "value": conflict.resolved_value
        })
        
        return True
    
    def _resolve_by_confidence(self, conflict: Conflict) -> bool:
        """基于可信度解决"""
        # 选择可信度最高的值
        best_source = max(
            conflict.sources_involved,
            key=lambda s: conflict.confidence.get(s, 0)
        )
        
        conflict.resolved_value = conflict.values[best_source]
        conflict.resolution = f"基于可信度选择 {best_source.value} 的值"
        
        self.resolution_log.append({
            "conflict_id": conflict.conflict_id,
            "strategy": "confidence",
            "selected_source": best_source.value,
            "value": conflict.resolved_value
        })
        
        return True
    
    def _resolve_by_merge(self, conflict: Conflict) -> bool:
        """通过合并解决"""
        values = list(conflict.values.values())
        
        if all(isinstance(v, str) for v in values):
            # 字符串合并：取最长或最详细的
            merged = max(values, key=len)
            conflict.resolved_value = merged
            conflict.resolution = "合并字符串值（选择最详细的）"
        elif all(isinstance(v, list) for v in values):
            # 列表合并：去重合并
            merged = []
            seen = set()
            for v in values:
                for item in v:
                    item_str = json.dumps(item, sort_keys=True)
                    if item_str not in seen:
                        seen.add(item_str)
                        merged.append(item)
            conflict.resolved_value = merged
            conflict.resolution = "合并列表值（去重）"
        else:
            # 其他类型：使用优先级
            return self._resolve_by_priority(conflict)
        
        self.resolution_log.append({
            "conflict_id": conflict.conflict_id,
            "strategy": "merge",
            "value": conflict.resolved_value
        })
        
        return True
    
    def _merge_final_data(self, data_sources: Dict[DataSource, Dict]) -> Dict:
        """合并最终数据"""
        # 按优先级排序源
        sorted_sources = sorted(
            data_sources.keys(),
            key=lambda s: self.priorities.get(s, 999)
        )
        
        # 从最高优先级开始合并
        final_data = {}
        for source in sorted_sources:
            self._deep_merge(final_data, data_sources[source])
        
        # 应用冲突解决结果
        for conflict in self.conflicts:
            if conflict.resolved_value is not None:
                self._set_value_at_path(final_data, conflict.field_path, conflict.resolved_value)
        
        return final_data
    
    def _deep_merge(self, base: Dict, override: Dict):
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _set_value_at_path(self, data: Dict, path: str, value: Any):
        """在指定路径设置值"""
        parts = path.split(".")
        current = data
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value


if __name__ == "__main__":
    # 测试
    resolver = ConflictResolver()
    
    # 测试数据
    test_sources = {
        DataSource.VIDEO: {
            "page_type": "product_list",
            "title": "产品列表",
            "item_count": 10
        },
        DataSource.API: {
            "page_type": "product",
            "title": "产品列表页",
            "item_count": 10,
            "api_version": "v2"
        },
        DataSource.DOM: {
            "page_type": "product_list",
            "title": "产品列表",
            "dom_loaded": True
        }
    }
    
    result = resolver.detect_and_resolve(test_sources)
    
    print("\n=== 冲突解决结果 ===")
    print(f"总冲突数: {result.total_conflicts}")
    print(f"已解决: {result.resolved_conflicts}")
    print(f"\n最终数据:")
    print(json.dumps(result.final_data, ensure_ascii=False, indent=2))
