#!/usr/bin/env python3
"""
测试 unified_memory_adapter 的数据提取逻辑
验证所有属性是否正确提取
"""

import sys
sys.path.insert(0, '/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner/src/python')

import json
from pathlib import Path

# 测试任务路径
task_path = Path("/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778202281796")

print("="*70)
print("UnifiedMemoryAdapter 数据提取验证 v2")
print("="*70)

# 1. 检查 page_structure.json
structure_file = task_path / "analysis" / "page_structure.json"
print(f"\n1. Page Structure 分析:")
print(f"   文件存在: {structure_file.exists()}")

if structure_file.exists():
    with open(structure_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    components = data.get('components', [])
    sections = data.get('layout_sections', [])
    css_rules = data.get('external_css_rules', {})

    print(f"   - Components: {len(components)}")
    print(f"   - Layout Sections: {len(sections)}")
    print(f"   - CSS Rules: {len(css_rules)}")
    print(f"   - Color Palette: {len(data.get('color_palette', []))}")
    print(f"   - Breakpoints: {len(data.get('breakpoints', []))}")

    # 验证 Component 属性完整性
    print(f"\n2. Component 属性验证:")
    if components:
        comp = components[10]  # 取第11个组件（跳过html/head等）
        expected_props = ['id', 'tag', 'type', 'name', 'class_names', 'attributes',
                         'styles', 'computed_styles', 'bounding_box', 'children_ids',
                         'parent_id', 'depth', 'text_content', 'is_interactive', 'event_handlers']
        actual_props = list(comp.keys())

        print(f"   期望属性数: {len(expected_props)}")
        print(f"   实际属性数: {len(actual_props)}")

        missing = [p for p in expected_props if p not in actual_props]
        if missing:
            print(f"   ❌ 缺失属性: {missing}")
        else:
            print(f"   ✅ 所有关键属性都存在")

        # 显示组件示例
        print(f"\n   组件示例 (id={comp.get('id')}):")
        for prop in ['tag', 'type', 'depth', 'parent_id']:
            print(f"     {prop}: {comp.get(prop)}")
        print(f"     class_names: {comp.get('class_names', [])[:3]}...")
        print(f"     bounding_box: {comp.get('bounding_box', {})}")
        print(f"     children_ids: {len(comp.get('children_ids', []))} 个子组件")

    # 验证 LayoutSection 属性完整性
    print(f"\n3. LayoutSection 属性验证:")
    if sections:
        sec = sections[0]
        expected_props = ['id', 'type', 'name', 'component_ids', 'child_sections',
                         'parent_section_id', 'styles', 'bounding_box']
        actual_props = list(sec.keys())

        print(f"   期望属性数: {len(expected_props)}")
        print(f"   实际属性数: {len(actual_props)}")

        missing = [p for p in expected_props if p not in actual_props]
        if missing:
            print(f"   ❌ 缺失属性: {missing}")
        else:
            print(f"   ✅ 所有关键属性都存在")

        # 显示 section 示例
        print(f"\n   Section 示例 (id={sec.get('id')}):")
        for prop in ['type', 'name']:
            print(f"     {prop}: {sec.get(prop)}")
        print(f"     component_ids: {len(sec.get('component_ids', []))} 个组件")
        print(f"     child_sections: {len(sec.get('child_sections', []))} 个子区块")
        print(f"     bounding_box: {sec.get('bounding_box', {})}")

    # 验证 CSS Rules
    print(f"\n4. CSS Rules 验证:")
    if css_rules:
        selectors = list(css_rules.keys())[:3]
        print(f"   样本选择器: {selectors}")

        # 检查 declarations 格式
        sample_selector = selectors[0]
        sample_decl = css_rules[sample_selector]
        print(f"   样本 declarations 类型: {type(sample_decl)}")
        if isinstance(sample_decl, dict):
            print(f"   样本 declarations 内容: {dict(list(sample_decl.items())[:3])}")
        elif isinstance(sample_decl, list):
            print(f"   样本 declarations 数量: {len(sample_decl)}")

# 5. 验证资源文件
print(f"\n5. 资源文件验证:")
resources_dir = task_path / "network" / "resources"
if resources_dir.exists():
    resource_files = list(resources_dir.iterdir())
    print(f"   资源文件数量: {len(resource_files)}")

    # 按类型统计
    type_count = {}
    for f in resource_files[:50]:  # 取样前50个
        ext = f.suffix.lower()
        type_count[ext] = type_count.get(ext, 0) + 1

    print(f"   类型分布 (前50个):")
    for ext, count in sorted(type_count.items(), key=lambda x: -x[1])[:5]:
        print(f"     {ext}: {count}")

# 6. 验证 DOM 快照
print(f"\n6. DOM 快照验证:")
dom_dir = task_path / "dom"
if dom_dir.exists():
    snapshot_files = list(dom_dir.glob("snapshot_*.json"))
    print(f"   Snapshot 文件数量: {len(snapshot_files)}")

    if snapshot_files:
        # 读取第一个 snapshot
        with open(snapshot_files[0], 'r', encoding='utf-8') as f:
            snapshot = json.load(f)

        rrweb_event = snapshot.get('rrwebEvent', {})
        print(f"   事件类型: {rrweb_event.get('type')}")
        print(f"   时间戳: {rrweb_event.get('timestamp')}")

        data = rrweb_event.get('data', {})
        nodes = data.get('nodes', [])
        print(f"   节点数量: {len(nodes)}")

# 7. 验证关键帧
print(f"\n7. 视频关键帧验证:")
keyframes_dirs = [
    task_path / "video" / "enhanced_final",
    task_path / "analysis" / "enhanced_final"
]

for keyframes_dir in keyframes_dirs:
    if keyframes_dir.exists():
        screenshot_files = list(keyframes_dir.glob("*.png")) + list(keyframes_dir.glob("*.jpg"))
        print(f"   关键帧目录: {keyframes_dir}")
        print(f"   关键帧数量: {len(screenshot_files)}")
        break
else:
    print(f"   未找到关键帧目录")

print("\n" + "="*70)
print("验证完成!")
print("="*70)
