#!/usr/bin/env python3
import sys
sys.path.insert(0, 'sentinel-learner/src/python')

from business_learner.extractors.page_structure_extractor import PageStructureExtractor
from business_learner.generators.prototype_generator import PrototypeGenerator
from pathlib import Path

# 路径
task_path = '/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_44_www.chinastock.com.cn_1778124008942'
snapshot_path = f'{task_path}/dom/snapshot_initial.json'
output_dir = f'{task_path}/output'

# 创建输出目录
Path(output_dir).mkdir(exist_ok=True)

print('🔍 提取页面结构...')
extractor = PageStructureExtractor(snapshot_path)
structure = extractor.extract()

if structure:
    print(f'✅ 提取成功!')
    print(f'   标题: {structure.title}')
    print(f'   组件: {len(structure.components)}')
    print(f'   布局: {len(structure.layout_sections)}')
    
    # 保存页面结构
    extractor.save(output_dir)
    print(f'   已保存到: {output_dir}/page_structure.json')
    
    # 生成原型
    print('\n🎨 生成原型Demo...')
    generator = PrototypeGenerator(f'{output_dir}/page_structure.json')
    prototype_path = generator.generate(output_dir, title=structure.title)
    
    if prototype_path:
        print(f'✅ 原型已生成: {prototype_path}')
    else:
        print('❌ 原型生成失败')
else:
    print('❌ 页面结构提取失败')
