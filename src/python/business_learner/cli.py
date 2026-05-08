#!/usr/bin/env python3
"""
Business Learner CLI

Usage:
    python -m business_learner.cli <task_path>
    python -m business_learner.cli --task-path /path/to/task
    
Options:
    --task-path     Task数据目录路径
    --output-dir    输出目录（可选）
    --verbose       详细输出
"""

import sys
import argparse
from pathlib import Path

from business_learner.core.engine import BusinessLearningEngine


def create_parser():
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        prog='business_learner',
        description='从task数据中学习业务功能',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python cli.py /path/to/task
    python cli.py --task-path /path/to/task --verbose
        """
    )
    
    parser.add_argument(
        'task_path',
        nargs='?',
        help='Task数据目录路径'
    )
    
    parser.add_argument(
        '--task-path',
        dest='task_path_opt',
        help='Task数据目录路径（可选参数形式）'
    )
    
    parser.add_argument(
        '--output-dir',
        help='输出目录（默认: task_path/analysis）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 确定task路径
    task_path = args.task_path or args.task_path_opt
    
    if not task_path:
        # 使用默认路径
        task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778034751731"
        print(f"未指定task路径，使用默认路径: {task_path}")
    
    task_path = Path(task_path)
    
    if not task_path.exists():
        print(f"错误: 路径不存在: {task_path}")
        sys.exit(1)
    
    if not task_path.is_dir():
        print(f"错误: 路径不是目录: {task_path}")
        sys.exit(1)
    
    # 检查必要文件
    required_files = ['training_manifest.jsonl']
    missing = [f for f in required_files if not (task_path / f).exists()]
    if missing:
        print(f"警告: 缺少文件: {', '.join(missing)}")
    
    # 运行学习引擎
    try:
        engine = BusinessLearningEngine(str(task_path))
        result = engine.run()
        
        # 打印摘要
        print("\n" + "="*70)
        print(" 学习结果摘要")
        print("="*70)
        print(f"\n业务系统: {result.business_system}")
        print(f"业务领域: {result.business_domain}")
        print(f"分析页面: {len(result.pages)} 个")
        print(f"业务流程: {len(result.processes)} 个")
        print(f"业务实体: {len(result.entities)} 个")
        
        if result.key_findings:
            print(f"\n关键发现:")
            for finding in result.key_findings:
                print(f"  • {finding}")
        
        print(f"\n详细报告: {task_path / 'analysis' / 'business_report.md'}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"\n错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

