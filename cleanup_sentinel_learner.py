#!/usr/bin/env python3
"""
Sentinel Learner 代码清理脚本
删除测试代码、未使用的导入和临时文件
"""

import os
import re
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path("/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner")

def remove_test_blocks(file_path):
    """删除文件底部的 if __name__ == "__main__": 测试代码块"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找 if __name__ == "__main__": 及其后面的所有内容
    pattern = r'\nif __name__ == ["\']__main__["\']:\s*\n.*?(?=\Z)'
    
    # 使用 DOTALL 模式匹配多行
    matches = list(re.finditer(r'\nif __name__ == ["\']__main__["\']:\s*\n', content, re.DOTALL))
    
    if matches:
        # 只保留测试代码块之前的内容
        last_match = matches[-1]
        new_content = content[:last_match.start()]
        
        # 确保文件以换行符结尾
        if not new_content.endswith('\n'):
            new_content += '\n'
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True
    
    return False

def cleanup_python_files():
    """清理 Python 文件中的测试代码"""
    python_dir = PROJECT_ROOT / "src" / "python"
    
    # 需要清理的文件列表（包含测试代码的文件）
    files_to_clean = [
        "business_learner/storage/unified_memory_adapter.py",
        "business_learner/utils/task_metadata.py",
        "business_learner/core/final_engine.py",
        "llm/prompts.py",
        "llm/kimi_client.py",
        "business_learner/utils/image_stitcher_skill.py",
        "business_learner/llm/vision_analyzer.py",
        "business_learner/llm/llm_integration.py",
        "business_learner/llm/business_understander.py",
        "business_learner/fusion/visual_text_fusion.py",
        "business_learner/fusion/temporal_aligner.py",
        "business_learner/fusion/fusion_engine.py",
        "business_learner/fusion/conflict_resolver.py",
        "business_learner/extractors/resources_analyzer.py",
        "business_learner/extractors/manifest_analyzer.py",
        "business_learner/extractors/logs_analyzer.py",
        "business_learner/extractors/enhanced_video_analyzer_fixed.py",
        "business_learner/extractors/dom_parser.py",
        "business_learner/extractors/dom_extractor.py",
        "business_learner/extractors/api_traffic_analyzer.py",
        "business_learner/extractors/api_extractor.py",
        "business_learner/core/server_engine.py",
        "business_learner/cli.py",
    ]
    
    cleaned_files = []
    
    for relative_path in files_to_clean:
        file_path = python_dir / relative_path
        if file_path.exists():
            if remove_test_blocks(file_path):
                cleaned_files.append(relative_path)
                print(f"✅ 已清理: {relative_path}")
        else:
            print(f"⚠️  文件不存在: {relative_path}")
    
    return cleaned_files

def remove_unused_files():
    """删除未使用的文件"""
    files_to_remove = [
        # Node.js mock 路由（如果没有使用）
        "src/node/routes/mock.js",
    ]
    
    removed_files = []
    
    for relative_path in files_to_remove:
        file_path = PROJECT_ROOT / relative_path
        if file_path.exists():
            # 备份文件内容
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            file_path.rename(backup_path)
            removed_files.append(relative_path)
            print(f"🗑️  已移除（备份为 .bak）: {relative_path}")
    
    return removed_files

def main():
    print("="*70)
    print("Sentinel Learner 代码清理工具")
    print("="*70)
    
    print("\n📁 项目路径:", PROJECT_ROOT)
    
    # 1. 清理 Python 文件中的测试代码
    print("\n" + "="*70)
    print("1. 清理 Python 文件中的测试代码块")
    print("="*70)
    cleaned = cleanup_python_files()
    print(f"\n✅ 共清理了 {len(cleaned)} 个文件")
    
    # 2. 删除未使用的文件
    print("\n" + "="*70)
    print("2. 删除未使用的文件")
    print("="*70)
    removed = remove_unused_files()
    print(f"\n✅ 共移除了 {len(removed)} 个文件")
    
    print("\n" + "="*70)
    print("清理完成！")
    print("="*70)
    print("\n请检查修改后的文件，确认无误后提交到 GitHub")
    print("如果需要恢复，可以从 .bak 备份文件恢复")

if __name__ == "__main__":
    main()
