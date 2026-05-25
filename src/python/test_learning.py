#!/usr/bin/env python3
"""
Sentinel Learner 测试脚本
使用 task_55 进行学习和测试
"""

import os
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from enhanced_memory import EnhancedMemorySystem
from prototype_builder import PrototypeBuilder


def test_qa_learning():
    """测试知识问答学习"""
    print("="*70)
    print("测试知识问答学习")
    print("="*70)
    
    # Task 路径
    task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/.trae/skills/sentinel-browser/collections/task_55_www.chinastock.com.cn_1778664098999"
    
    if not Path(task_path).exists():
        print(f"❌ Task 路径不存在: {task_path}")
        return False
    
    print(f"\n📁 Task 路径: {task_path}")
    print(f"   Task ID: task_55_www.chinastock.com.cn_1778664098999")
    
    # 检查 API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️ 未设置 OPENAI_API_KEY")
        print("请设置: export OPENAI_API_KEY='your-api-key'")
        print("\n跳过向量嵌入，仅测试数据提取...")
        test_extraction_only(task_path)
        return False
    
    # 初始化系统
    print("\n🚀 初始化 EnhancedMemorySystem...")
    memory = EnhancedMemorySystem(
        collection_name="test_task_55",
        api_key=api_key
    )
    
    # 索引 task
    print("\n📚 开始索引 task 数据...")
    print("   - 提取文本块（manifest, api, dom）")
    print("   - 提取图像块（video keyframes）")
    print("   - 生成嵌入向量")
    print("   - 存储到 ChromaDB 和知识图谱")
    
    try:
        success = memory.index_task(task_path)
        if success:
            print("✅ 索引成功！")
        else:
            print("❌ 索引失败")
            return False
    except Exception as e:
        print(f"❌ 索引出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 查看存储统计
    print("\n📊 存储统计:")
    stats = memory.get_stats()
    print(f"   向量集合: {stats['vector_store']['collection_name']}")
    print(f"   文档数量: {stats['vector_store']['total_documents']}")
    print(f"   存储路径: {stats['vector_store']['persist_directory']}")
    
    # 测试查询
    print("\n🔍 测试查询...")
    test_questions = [
        "这个网站是什么？",
        "网站有哪些功能？",
        "页面上有什么内容？",
    ]
    
    for question in test_questions:
        print(f"\n   Q: {question}")
        try:
            result = memory.query(question)
            print(f"   A: {result.answer[:150]}...")
            print(f"   置信度: {result.confidence:.3f}")
            print(f"   证据数: {result.total_found}")
            
            if result.confidence >= 0.95:
                print("   ✅ 高置信度")
            elif result.confidence >= 0.85:
                print("   ⚠️ 中等置信度")
            else:
                print("   ❌ 低置信度")
                
        except Exception as e:
            print(f"   ❌ 查询失败: {e}")
    
    return True


def test_extraction_only(task_path: str):
    """仅测试数据提取（无需 API key）"""
    print("\n" + "="*70)
    print("仅测试数据提取（无需 API）")
    print("="*70)
    
    from enhanced_memory.extractors.task_extractor import TaskExtractor
    
    extractor = TaskExtractor()
    
    print("\n📄 提取文本块...")
    text_chunks = extractor.extract_text_chunks(task_path)
    print(f"   找到 {len(text_chunks)} 个文本块")
    
    if text_chunks:
        print("\n   前3个文本块示例:")
        for i, chunk in enumerate(text_chunks[:3]):
            print(f"\n   [{i+1}] 来源: {chunk['source']}")
            print(f"       内容: {chunk['text'][:100]}...")
    
    print("\n🖼️  提取图像块...")
    image_chunks = extractor.extract_image_chunks(task_path)
    print(f"   找到 {len(image_chunks)} 个图像块")
    
    if image_chunks:
        print("\n   前3个图像示例:")
        for i, chunk in enumerate(image_chunks[:3]):
            print(f"\n   [{i+1}] 来源: {chunk['source']}")
            print(f"       路径: {chunk['path']}")


def test_prototype_building():
    """测试产品原型构建"""
    print("\n" + "="*70)
    print("测试产品原型构建")
    print("="*70)
    
    # Task 路径
    task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/.trae/skills/sentinel-browser/collections/task_55_www.chinastock.com.cn_1778664098999"
    output_dir = "/tmp/sentinel_prototype_test"
    
    print(f"\n📁 Task 路径: {task_path}")
    print(f"📁 输出目录: {output_dir}")
    
    # 初始化构建器
    print("\n🚀 初始化 PrototypeBuilder...")
    builder = PrototypeBuilder(target_score=0.95)
    
    # 构建原型
    print("\n🔨 开始构建原型...")
    print("   策略1: DOM 快照重建")
    print("   策略2: 资源文件重建（降级）")
    
    try:
        result = builder.build(task_path, output_dir)
        
        print(f"\n📊 构建结果:")
        print(f"   状态: {'✅ 成功' if result.is_success() else '❌ 失败'}")
        print(f"   数据源: {result.source.value}")
        
        if result.is_success():
            print(f"   输出文件: {result.output_path}")
            print(f"   构建时间: {result.build_time_ms:.1f}ms")
            
            if result.quality.overall_score > 0:
                print(f"\n   质量评估:")
                print(f"      综合评分: {result.quality.overall_score:.3f}")
                print(f"      SSIM: {result.quality.ssim_score:.3f}")
                print(f"      布局: {result.quality.layout_score:.3f}")
                print(f"      元素: {result.quality.element_score:.3f}")
                print(f"      样式: {result.quality.style_score:.3f}")
                
                if result.meets_target():
                    print(f"      ✅ 达到目标 (≥0.95)")
                else:
                    print(f"      ⚠️ 未达到目标")
            
            if result.downgrade_from:
                print(f"\n   降级信息:")
                print(f"      从: {result.downgrade_from.value}")
                print(f"      原因: {result.downgrade_reason}")
        else:
            print(f"   错误: {result.error_message}")
            
    except Exception as e:
        print(f"❌ 构建出错: {e}")
        import traceback
        traceback.print_exc()


def show_task_info():
    """显示 task 信息"""
    print("="*70)
    print("Task 信息")
    print("="*70)
    
    task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/.trae/skills/sentinel-browser/collections/task_55_www.chinastock.com.cn_1778664098999"
    
    print(f"\n📁 路径: {task_path}")
    
    # 检查文件
    path = Path(task_path)
    if not path.exists():
        print("❌ 路径不存在")
        return
    
    print("\n📂 目录结构:")
    
    # 主要文件
    files_to_check = [
        ("metadata.json", "任务元数据"),
        ("training_manifest.jsonl", "核心事件日志"),
        ("video/raw_record.mp4", "录制视频"),
        ("dom/snapshot_*.json", "DOM 快照"),
        ("network/api_responses.json", "API 响应"),
        ("network/resources/", "静态资源"),
        ("sandbox/browser_state.json", "浏览器状态"),
    ]
    
    for file_path, description in files_to_check:
        full_path = path / file_path
        if '*' in file_path:
            # 通配符检查
            import glob
            matches = glob.glob(str(full_path))
            if matches:
                print(f"   ✅ {description}: {len(matches)} 个文件")
            else:
                print(f"   ❌ {description}: 未找到")
        else:
            if full_path.exists():
                if full_path.is_file():
                    size = full_path.stat().st_size
                    print(f"   ✅ {description}: {size:,} bytes")
                else:
                    print(f"   ✅ {description}: 目录")
            else:
                print(f"   ❌ {description}: 不存在")
    
    # 读取 metadata
    metadata_path = path / "metadata.json"
    if metadata_path.exists():
        import json
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        print(f"\n📋 元数据:")
        print(f"   任务ID: {metadata.get('task_id')}")
        print(f"   目标网站: {metadata.get('start_url')}")
        print(f"   录制时间: {metadata.get('created_at')}")
        print(f"   操作员: {metadata.get('user_id')}")


if __name__ == "__main__":
    print("Sentinel Learner 测试")
    print("="*70)
    
    # 显示 task 信息
    show_task_info()
    
    # 测试知识问答
    print("\n")
    test_qa_learning()
    
    # 测试产品原型
    print("\n")
    test_prototype_building()
    
    print("\n" + "="*70)
    print("测试完成")
    print("="*70)
