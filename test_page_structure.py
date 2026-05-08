#!/usr/bin/env python3
"""
测试 page_structure_extractor 是否正常工作
"""

import sys
sys.path.insert(0, '/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner/src/python')

from business_learner.extractors.page_structure_extractor import PageStructureExtractor, PageStructure

# 检查关键类和函数是否存在
print("="*70)
print("Page Structure Extractor 测试")
print("="*70)

# 1. 检查 PageStructure 类
print("\n1. 检查 PageStructure 类...")
ps = PageStructure(
    url="https://example.com",
    title="Test",
    timestamp=1234567890
)
print(f"   ✓ PageStructure 类可实例化")

# 2. 检查 to_dict 方法
print("\n2. 检查 to_dict 方法...")
data = ps.to_dict()
expected_fields = ['url', 'title', 'timestamp', 'viewport', 'layout_sections', 
                   'components', 'color_palette', 'typography', 'spacing_system',
                   'css_files', 'inline_styles', 'external_css_rules', 
                   'css_class_definitions', 'component_css_mapping', 'breakpoints']
missing = [f for f in expected_fields if f not in data]
if missing:
    print(f"   ✗ 缺少字段: {missing}")
else:
    print(f"   ✓ 所有字段都存在: {len(expected_fields)} 个")

# 3. 检查 PageStructureExtractor 类
print("\n3. 检查 PageStructureExtractor 类...")
try:
    extractor = PageStructureExtractor("/nonexistent/path.json")
    print(f"   ✓ PageStructureExtractor 类可实例化")
    
    # 检查关键方法
    methods = ['extract', '_identify_layout_sections', '_extract_components', 
               '_extract_responsive_breakpoints', '_extract_typography']
    for method in methods:
        if hasattr(extractor, method):
            print(f"   ✓ 方法存在: {method}")
        else:
            print(f"   ✗ 方法缺失: {method}")
except Exception as e:
    print(f"   ✗ 实例化失败: {e}")

print("\n" + "="*70)
print("测试完成!")
print("="*70)
