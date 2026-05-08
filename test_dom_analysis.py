#!/usr/bin/env python3
"""
测试 DOM 分析流程
"""

import sys
sys.path.insert(0, '/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner/src/python')

from pathlib import Path
from business_learner.core.final_engine import FinalBusinessLearningEngine

# 测试任务路径
task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778202281796"

print("="*70)
print("DOM 分析测试")
print("="*70)

if not Path(task_path).exists():
    print(f"\n❌ 任务路径不存在: {task_path}")
    sys.exit(1)

print(f"\n📁 任务路径: {task_path}")

# 创建引擎
engine = FinalBusinessLearningEngine(task_path)

# 只运行 DOM 分析
print("\n🔍 运行 DOM 分析...")
dom_result = engine._analyze_dom()

print("\n" + "="*70)
print("分析结果:")
print("="*70)

if not dom_result:
    print("\n❌ DOM 分析返回空结果")
    sys.exit(1)

print(f"\n✅ 返回的键: {list(dom_result.keys())}")
print(f"   - total_snapshots: {dom_result.get('total_snapshots', 0)}")
print(f"   - snapshots 数量: {len(dom_result.get('snapshots', []))}")
print(f"   - page_structures 数量: {len(dom_result.get('page_structures', []))}")

# 检查 page_structures 内容
page_structures = dom_result.get('page_structures', [])
if page_structures:
    print("\n📊 第一个 page_structure 的键:")
    first_ps = page_structures[0]
    for key in first_ps.keys():
        value = first_ps[key]
        if isinstance(value, list):
            print(f"   - {key}: {len(value)} 项")
        elif isinstance(value, dict):
            print(f"   - {key}: {len(value)} 个键")
        else:
            print(f"   - {key}: {value}")
else:
    print("\n⚠️ 警告: page_structures 为空数组!")
    
    # 检查 snapshots
    snapshots = dom_result.get('snapshots', [])
    if snapshots:
        print("\n📋 snapshots 内容:")
        for i, snap in enumerate(snapshots[:3]):  # 只显示前3个
            print(f"   [{i}] {snap.get('file', 'N/A')}")
            print(f"       has_structure: {snap.get('has_structure', False)}")
            print(f"       element_count: {snap.get('element_count', 0)}")

print("\n" + "="*70)
print("测试完成!")
print("="*70)
