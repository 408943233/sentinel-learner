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

from business_learner.core.final_engine import FinalBusinessLearningEngine
from business_learner.storage.unified_memory_adapter import UnifiedMemoryAdapter


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)


def main():
    """主函数"""
    # 检查参数
    if len(sys.argv) < 2:
        print("用法: python learn.py <task_path>")
        print("示例: python learn.py /path/to/task_folder")
        sys.exit(1)

    task_path = sys.argv[1]
    task_path = Path(task_path)

    if not task_path.exists():
        print(f"错误: 路径不存在: {task_path}")
        sys.exit(1)

    print_section("Business Learner 启动")
    print(f"Task路径: {task_path}")

    # 运行最终版引擎
    print_section("运行最终版业务学习引擎")

    # LLM API密钥
    llm_api_key = "sk-kimi-zhML5ZaA3RUhBw6TWawtWNQdod4Qf02Mokm4QzbXdSbden99YI4nyk5DE9GUJHJA"

    engine = FinalBusinessLearningEngine(
        task_path=str(task_path),
        mode='local',
        llm_api_key=llm_api_key
    )

    result = engine.run(
        use_llm_vision=True,
        create_long_screenshots=True
    )

    print_section("学习完成")
    print(f"""
✅ 完成!
   - Task ID: {result.task_id if hasattr(result, 'task_id') else 'N/A'}
   - 页面数: {len(result.pages) if hasattr(result, 'pages') else 0}
   - 业务流程: {len(result.processes) if hasattr(result, 'processes') else 0}

📁 输出目录:
   - {task_path / 'analysis'}
""")


if __name__ == "__main__":
    main()
