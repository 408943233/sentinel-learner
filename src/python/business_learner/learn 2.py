#!/usr/bin/env python3
"""
Business Learner - 业务学习入口

使用方法:
    python learn.py <task_path>
    
示例:
    python learn.py /path/to/task_folder
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core_fusion_engine import CoreFusionEngine
from storage.memory_adapter import MemorySkillAdapter


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)


def print_summary(summary: dict):
    """打印业务理解摘要"""
    print_section("业务理解摘要")
    
    print(f"\n📌 业务系统: {summary.get('业务系统', 'Unknown')}")
    
    print(f"\n🏢 业务领域:")
    for domain in summary.get('业务领域', []):
        print(f"   • {domain}")
    
    print(f"\n📄 页面类型:")
    for page_type, pages in summary.get('页面类型', {}).items():
        print(f"   • {page_type}: {len(pages)} 个页面")
        for page in pages[:3]:  # 只显示前3个
            print(f"     - {page.get('title', '')[:40]}")
            print(f"       {page.get('url', '')[:60]}...")
    
    print(f"\n🔄 业务流程:")
    for process in summary.get('业务流程', []):
        print(f"   • {process.get('name', '')}")
        print(f"     步骤数: {process.get('steps_count', 0)}")
        print(f"     从: {process.get('start', '')[:50]}...")
        print(f"     到: {process.get('end', '')[:50]}...")


def main():
    """主函数"""
    # 检查参数
    if len(sys.argv) < 2:
        # 使用默认路径
        task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778034751731"
        print(f"未指定task路径，使用默认路径: {task_path}")
    else:
        task_path = sys.argv[1]
    
    task_path = Path(task_path)
    
    if not task_path.exists():
        print(f"错误: 路径不存在: {task_path}")
        sys.exit(1)
    
    print_section("Business Learner 启动")
    print(f"Task路径: {task_path}")
    
    # 步骤1: 运行核心融合引擎
    print_section("步骤1: 多源数据融合分析")
    engine = CoreFusionEngine(str(task_path))
    summary = engine.run()
    
    # 步骤2: 打印理解结果
    print_summary(summary)
    
    # 步骤3: 存储到知识图谱（可选）
    print_section("步骤2: 存储到知识图谱")
    
    try:
        adapter = MemorySkillAdapter()
        adapter.store_learning_result(summary)
    except Exception as e:
        print(f"存储到知识图谱时出错: {e}")
        print("（这不影响业务理解结果）")
    
    # 步骤4: 保存结果到文件
    print_section("步骤3: 保存结果")
    
    output_dir = task_path / "analysis"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "business_understanding.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"结果已保存到: {output_file}")
    
    print_section("学习完成")
    print(f"""
✅ 完成!
   - 分析了 {len(summary.get('页面类型', {}))} 种页面类型
   - 提取了 {len(summary.get('业务流程', []))} 个业务流程
   - 识别了 {len(summary.get('业务领域', []))} 个业务领域
   
📁 输出文件:
   - {output_file}
""")


if __name__ == "__main__":
    main()
