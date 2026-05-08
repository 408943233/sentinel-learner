#!/usr/bin/env python3
"""
测试 unified_memory_adapter 的内容级存储功能
"""

import sys
sys.path.insert(0, '/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner/src/python')

import json
from pathlib import Path
from business_learner.storage.unified_memory_adapter import UnifiedMemoryAdapter
from business_learner.utils.task_metadata import TaskMetadataManager

# 测试任务路径
task_path = Path("/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778202281796")

print("="*70)
print("UnifiedMemoryAdapter 内容级存储测试")
print("="*70)

# 1. 检查 page_structure.json 是否存在
structure_file = task_path / "analysis" / "page_structure.json"
print(f"\n1. 检查 page_structure.json:")
print(f"   路径: {structure_file}")
print(f"   存在: {structure_file.exists()}")

if structure_file.exists():
    with open(structure_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\n2. Page Structure 数据概览:")
    print(f"   - URL: {data.get('url', 'N/A')}")
    print(f"   - Title: {data.get('title', 'N/A')}")
    print(f"   - Components: {len(data.get('components', []))}")
    print(f"   - Layout Sections: {len(data.get('layout_sections', []))}")
    print(f"   - CSS Rules: {len(data.get('external_css_rules', {}))}")
    print(f"   - Color Palette: {len(data.get('color_palette', []))}")
    
    # 检查组件结构
    components = data.get('components', [])
    if components:
        print(f"\n3. 第一个组件示例:")
        comp = components[0]
        print(f"   - tag: {comp.get('tag')}")
        print(f"   - type: {comp.get('type')}")
        print(f"   - class_names: {comp.get('class_names', [])}")
        print(f"   - bounding_box: {comp.get('bounding_box', {})}")
        print(f"   - styles keys: {list(comp.get('styles', {}).keys())}")
    
    # 检查布局区块
    sections = data.get('layout_sections', [])
    if sections:
        print(f"\n4. 第一个 Layout Section 示例:")
        sec = sections[0]
        print(f"   - type: {sec.get('type')}")
        print(f"   - name: {sec.get('name', '')[:50]}...")
        print(f"   - bounding_box: {sec.get('bounding_box', {})}")

# 5. 测试存储方法是否能正确解析数据
print(f"\n5. 测试 _store_page_structure_detailed 方法:")

# 创建 adapter 实例
adapter = UnifiedMemoryAdapter(mode="local")

# 创建模拟的 page_entity_id
page_entity_id = "test_page_123"

# 测试 _store_components 方法
print(f"\n   测试 _store_components:")
if components:
    # 只测试前3个组件
    test_components = components[:3]
    for i, comp in enumerate(test_components):
        comp_props = {
            "tag": comp.get('tag', ''),
            "type": comp.get('type', 'unknown'),
            "text_content": comp.get('text_content', '')[:200],
            "is_interactive": comp.get('is_interactive', False),
        }
        
        class_names = comp.get('class_names', [])
        if class_names:
            comp_props["classes"] = ' '.join(class_names[:10])
        
        bbox = comp.get('bounding_box', {})
        if bbox:
            comp_props["x"] = bbox.get('x', 0)
            comp_props["y"] = bbox.get('y', 0)
            comp_props["width"] = bbox.get('width', 0)
            comp_props["height"] = bbox.get('height', 0)
        
        print(f"      组件 {i+1}: {comp_props}")

# 测试 DesignToken
print(f"\n   测试 _store_design_tokens:")
color_palette = data.get('color_palette', [])
if color_palette:
    print(f"      颜色样本 (前5个): {color_palette[:5]}")

typography = data.get('typography', {})
if typography:
    print(f"      font_sizes: {typography.get('font_sizes', [])[:5]}")
    print(f"      font_families: {typography.get('font_families', [])[:3]}")

print("\n" + "="*70)
print("测试完成!")
print("="*70)
print("\n注意: 实际存储需要 openclaw-memory-skill 运行环境")
print("此测试仅验证数据结构和属性提取逻辑")
