#!/usr/bin/env python3
"""
Sentinel Learner 增强系统演示
展示知识问答和产品原型两个模块的使用
"""

import os
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from enhanced_memory import EnhancedMemorySystem, QueryResult
from prototype_builder import PrototypeBuilder


def demo_qa_system():
    """演示知识问答系统"""
    print("="*70)
    print("演示 1: 知识问答系统")
    print("="*70)
    
    # 初始化系统
    api_key = os.getenv("OPENAI_API_KEY")
    memory = EnhancedMemorySystem(
        collection_name="demo_qa",
        api_key=api_key
    )
    
    # 示例 task 路径（请替换为实际的 task 路径）
    task_path = "/path/to/task_55_www.chinastock.com.cn_1778664098999"
    
    if not Path(task_path).exists():
        print(f"⚠️ Task 路径不存在: {task_path}")
        print("请修改脚本中的 task_path 为实际路径")
        return
    
    # 索引 task
    print("\n1. 索引 task 数据...")
    success = memory.index_task(task_path)
    if not success:
        print("❌ 索引失败")
        return
    
    # 查询示例
    questions = [
        "这个网站有哪些主要功能？",
        "用户可以进行哪些操作？",
        "页面布局是什么样的？",
        "有哪些导航菜单？",
    ]
    
    print("\n2. 执行查询...")
    for question in questions:
        print(f"\n  Q: {question}")
        result = memory.query(question)
        
        print(f"  A: {result.answer[:200]}...")
        print(f"  置信度: {result.confidence:.3f} ({result.confidence_level.value})")
        print(f"  证据数: {result.total_found}")
        print(f"  查询时间: {result.query_time_ms:.1f}ms")
        
        if result.confidence >= 0.95:
            print("  ✅ 高置信度回答")
        elif result.confidence >= 0.85:
            print("  ⚠️ 中等置信度回答")
        else:
            print("  ❌ 低置信度回答，建议核实")


def demo_prototype_builder():
    """演示产品原型构建"""
    print("\n" + "="*70)
    print("演示 2: 产品原型构建")
    print("="*70)
    
    # 初始化构建器
    builder = PrototypeBuilder(target_score=0.95)
    
    # 示例 task 路径
    task_path = "/path/to/task_55_www.chinastock.com.cn_1778664098999"
    output_dir = "/tmp/prototype_output"
    
    if not Path(task_path).exists():
        print(f"⚠️ Task 路径不存在: {task_path}")
        print("请修改脚本中的 task_path 为实际路径")
        return
    
    # 构建原型
    print(f"\n1. 构建原型...")
    print(f"   Task: {task_path}")
    print(f"   输出: {output_dir}")
    
    result = builder.build(task_path, output_dir)
    
    print(f"\n2. 构建结果:")
    print(f"   状态: {'✅ 成功' if result.is_success() else '❌ 失败'}")
    print(f"   数据源: {result.source.value}")
    
    if result.is_success():
        print(f"   输出文件: {result.output_path}")
        print(f"   构建时间: {result.build_time_ms:.1f}ms")
        
        if result.quality.overall_score > 0:
            print(f"\n3. 质量评估:")
            print(f"   综合评分: {result.quality.overall_score:.3f}")
            print(f"   SSIM: {result.quality.ssim_score:.3f}")
            print(f"   布局: {result.quality.layout_score:.3f}")
            print(f"   元素: {result.quality.element_score:.3f}")
            print(f"   样式: {result.quality.style_score:.3f}")
            print(f"   质量等级: {result.quality.evaluate_quality().value}")
            
            if result.meets_target():
                print(f"   ✅ 达到目标 (≥0.95)")
            else:
                print(f"   ⚠️ 未达到目标")
        
        if result.downgrade_from:
            print(f"\n   降级信息:")
            print(f"     从: {result.downgrade_from.value}")
            print(f"     原因: {result.downgrade_reason}")
    else:
        print(f"   错误: {result.error_message}")


def demo_batch_build():
    """演示批量构建"""
    print("\n" + "="*70)
    print("演示 3: 批量原型构建")
    print("="*70)
    
    # 示例 task 列表
    task_paths = [
        "/path/to/task_1",
        "/path/to/task_2",
        "/path/to/task_3",
    ]
    
    # 过滤存在的路径
    existing_tasks = [p for p in task_paths if Path(p).exists()]
    
    if not existing_tasks:
        print("⚠️ 没有有效的 task 路径")
        print("请修改脚本中的 task_paths")
        return
    
    builder = PrototypeBuilder(target_score=0.95)
    output_base = "/tmp/prototype_batch"
    
    print(f"\n批量构建 {len(existing_tasks)} 个 task...")
    results = builder.batch_build(existing_tasks, output_base)
    
    # 生成报告
    report = builder.get_build_report(results)
    
    print(f"\n构建报告:")
    print(f"  总数: {report['summary']['total']}")
    print(f"  成功: {report['summary']['successful']}")
    print(f"  达到目标: {report['summary']['target_met']} ({report['summary']['target_rate']:.1%})")
    print(f"  降级: {report['summary']['downgraded']}")
    print(f"  平均质量: {report['summary']['average_quality']:.3f}")
    
    print(f"\n数据源分布:")
    for source, count in report['by_source'].items():
        print(f"  - {source}: {count}")
    
    print(f"\n质量分布:")
    for quality, count in report['quality_distribution'].items():
        print(f"  - {quality}: {count}")


if __name__ == "__main__":
    print("Sentinel Learner 增强系统演示")
    print("="*70)
    print("\n请先设置环境变量:")
    print("  export OPENAI_API_KEY='your-api-key'")
    print("\n请修改脚本中的 task_path 为实际路径")
    print("="*70)
    
    # 检查 API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️ 未设置 OPENAI_API_KEY，部分功能可能无法使用")
    
    # 运行演示
    try:
        demo_qa_system()
    except Exception as e:
        print(f"\n知识问答演示出错: {e}")
    
    try:
        demo_prototype_builder()
    except Exception as e:
        print(f"\n原型构建演示出错: {e}")
    
    try:
        demo_batch_build()
    except Exception as e:
        print(f"\n批量构建演示出错: {e}")
    
    print("\n" + "="*70)
    print("演示完成")
    print("="*70)
