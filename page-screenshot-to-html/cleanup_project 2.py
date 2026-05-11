#!/usr/bin/env python3
"""
清理screenshot-to-html项目中的无用文件
保留v2版本所需的核心文件
"""
import os
import shutil
from pathlib import Path

def cleanup_project():
    """清理项目"""
    base_dir = Path("/Users/gaoyiwei/Documents/trae_projects/openclaw/page-screenshot-to-html")
    
    print("="*60)
    print("🧹 清理 screenshot-to-html 项目")
    print("="*60)
    print()
    
    # 要删除的文件和目录
    to_delete = []
    
    # 1. 旧版本的脚本文件（v2版本已整合）
    old_scripts = [
        "batch_convert.py",
        "batch_convert_parallel.py", 
        "batch_convert_dynamic.py",
        "check_missing.py",
        "retry_failed.py",
        "regenerate_single.py",
        "convert_flowchart.py",
        "test_paddleocr_standalone.py",
        "test_paddleocr_ch.py",
        "test_omniparser.py",
        "missing_files.txt",
    ]
    
    # 2. 旧版本的requirements
    old_requirements = [
        "requirements.txt",
    ]
    
    # 3. 旧版本的文档
    old_docs = [
        "INSTALL.md",
        "OMNIPARSER_SETUP.md",
        "OPENCLAW_SETUP.md",
    ]
    
    # 4. 旧版本的shell脚本
    old_shell = [
        "setup_omniparser.sh",
        "vps_install.sh",
        "setup-openclaw.sh",
    ]
    
    # 5. OmniParser中不需要的部分
    omniparser_unused = [
        "OmniParser/omnitool/omnibox",  # VM相关，不需要
        "OmniParser/omnitool/gradio/agent",  # 代理相关
        "OmniParser/omnitool/gradio/executor",
        "OmniParser/omnitool/gradio/loop.py",
        "OmniParser/omnitool/gradio/app_streamlit.py",
        "OmniParser/omnitool/gradio/app_new.py",
        "OmniParser/omnitool/omniparserserver",
        "OmniParser/eval",
        "OmniParser/demo.ipynb",
        "OmniParser/gradio_demo.py",
    ]
    
    # 6. 缓存和临时文件
    cache_files = [
        "OmniParser/weights/.cache",
    ]
    
    # 7. 测试用的旧输出文件（保留最近的几个月）
    # 这个需要手动确认，暂不自动删除
    
    # 收集所有要删除的项目
    all_to_delete = (
        old_scripts + 
        old_requirements + 
        old_docs + 
        old_shell + 
        omniparser_unused + 
        cache_files
    )
    
    deleted_count = 0
    skipped_count = 0
    error_count = 0
    
    print("📋 准备清理以下项目：")
    print()
    
    for item in all_to_delete:
        full_path = base_dir / item
        if full_path.exists():
            size = get_size(full_path)
            print(f"  🗑️  {item} ({size})")
        else:
            print(f"  ⚠️  {item} (不存在)")
    
    print()
    confirm = input("确认删除以上文件? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("❌ 取消清理")
        return
    
    print()
    print("开始清理...")
    print()
    
    for item in all_to_delete:
        full_path = base_dir / item
        try:
            if full_path.exists():
                if full_path.is_dir():
                    shutil.rmtree(full_path)
                else:
                    full_path.unlink()
                print(f"  ✅ 已删除: {item}")
                deleted_count += 1
            else:
                print(f"  ⏭️  跳过: {item} (不存在)")
                skipped_count += 1
        except Exception as e:
            print(f"  ❌ 错误: {item} - {e}")
            error_count += 1
    
    print()
    print("="*60)
    print("🎉 清理完成!")
    print("="*60)
    print(f"  ✅ 已删除: {deleted_count} 项")
    print(f"  ⏭️  跳过: {skipped_count} 项")
    print(f"  ❌ 错误: {error_count} 项")
    print()
    print("💡 保留的核心文件：")
    print("  - screenshot_to_html_v2.py (主程序)")
    print("  - core/ (核心模块)")
    print("  - OmniParser/util/ (OmniParser核心)")
    print("  - OmniParser/weights/ (模型权重)")
    print("  - requirements_v2.txt (依赖)")
    print("  - SKILL.md (技能文档)")
    print()

def get_size(path):
    """获取文件或目录大小"""
    try:
        if path.is_file():
            size = path.stat().st_size
            return format_size(size)
        elif path.is_dir():
            total = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            return format_size(total)
    except:
        return "未知大小"

def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

if __name__ == '__main__':
    cleanup_project()
