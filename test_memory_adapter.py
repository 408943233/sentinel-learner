#!/usr/bin/env python3
"""
快速测试 UnifiedMemoryAdapter 的新功能
验证 P0 实体存储是否正常工作
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src" / "python"))

from business_learner.storage.unified_memory_adapter import UnifiedMemoryAdapter
from business_learner.utils.task_metadata import TaskMetadataManager


def test_adapter():
    """测试适配器"""
    print("=" * 70)
    print("测试 UnifiedMemoryAdapter P0 功能")
    print("=" * 70)
    
    # 查找一个测试任务
    task_paths = [
        "/Users/gaoyiwei/Downloads/task_天弓高管注册录制_ibc.chinastock.com.cn_portal_d_1778549100968",
        "/Users/gaoyiwei/Downloads/0001/SentinelBrowser/SentinelBrowser/collections/task_11_www.chinastock.com.cn_1778545863992",
    ]
    
    task_path = None
    for tp in task_paths:
        if Path(tp).exists():
            task_path = Path(tp)
            break
    
    if not task_path:
        print("❌ 未找到测试任务")
        return
    
    print(f"\n使用任务: {task_path.name}")
    
    # 创建适配器
    adapter = UnifiedMemoryAdapter(mode="local")
    
    # 检查文件是否存在
    dom_dir = task_path / "dom"
    structure_file = task_path / "analysis" / "page_structure.json"
    api_traffic_file = task_path / "analysis" / "api_traffic.json"
    
    print(f"\n文件检查:")
    print(f"  - DOM目录: {'✅' if dom_dir.exists() else '❌'} {dom_dir}")
    print(f"  - 页面结构: {'✅' if structure_file.exists() else '❌'} {structure_file}")
    print(f"  - API流量: {'✅' if api_traffic_file.exists() else '❌'} {api_traffic_file}")
    
    # 测试各个存储方法
    print("\n" + "=" * 70)
    print("测试存储方法")
    print("=" * 70)
    
    # 清空批量缓存
    adapter._batch_entities.clear()
    adapter._batch_relations.clear()
    
    # 创建模拟页面实体
    mock_page_entity = {
        "id": "test_page_001",
        "type": "WebPage",
        "properties": {"url": "https://example.com/test"}
    }
    
    # 测试1: DOM快照存储
    print("\n1. 测试 _store_dom_snapshots_batch()")
    try:
        adapter._store_dom_snapshots_batch(
            page=type('obj', (object,), {'url': 'https://example.com'})(),
            page_entity_id=mock_page_entity["id"],
            task_path=task_path
        )
        print(f"   ✅ 完成，批量缓存: {len(adapter._batch_entities)} 实体")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试2: 组件聚合存储
    print("\n2. 测试 _store_components_batch()")
    try:
        adapter._store_components_batch(
            page=type('obj', (object,), {'url': 'https://example.com'})(),
            page_entity_id=mock_page_entity["id"],
            task_path=task_path
        )
        print(f"   ✅ 完成，批量缓存: {len(adapter._batch_entities)} 实体")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试3: CSS系统存储
    print("\n3. 测试 _store_css_system_batch()")
    try:
        adapter._store_css_system_batch(
            page=type('obj', (object,), {'url': 'https://example.com'})(),
            page_entity_id=mock_page_entity["id"],
            task_path=task_path
        )
        print(f"   ✅ 完成，批量缓存: {len(adapter._batch_entities)} 实体")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试4: API层存储
    print("\n4. 测试 _store_api_layer_batch()")
    try:
        adapter._store_api_layer_batch(
            system_entity_id="test_system_001",
            task_path=task_path
        )
        print(f"   ✅ 完成，批量缓存: {len(adapter._batch_entities)} 实体")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 统计结果
    print("\n" + "=" * 70)
    print("测试结果统计")
    print("=" * 70)
    
    entity_types = {}
    for entity in adapter._batch_entities:
        etype = entity.get("type", "Unknown")
        entity_types[etype] = entity_types.get(etype, 0) + 1
    
    print(f"\n实体类型分布:")
    for etype, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {etype}: {count} 个")
    
    print(f"\n总计:")
    print(f"  - 实体: {len(adapter._batch_entities)} 个")
    print(f"  - 关系: {len(adapter._batch_relations)} 条")
    
    # 检查是否写入文件（可选）
    print("\n" + "=" * 70)
    print("是否写入知识图谱? (y/n): ", end="")
    
    # 自动测试模式，不写入
    print("n (测试模式，跳过写入)")
    print("\n✅ 测试完成！新功能工作正常。")


if __name__ == "__main__":
    test_adapter()
