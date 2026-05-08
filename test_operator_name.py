#!/usr/bin/env python3
"""
测试 operator_name 是否正确读取和传递
"""

import sys
import json
from pathlib import Path

# 添加路径
sys.path.insert(0, '/Users/gaoyiwei/Documents/trae_projects/openclaw/sentinel-learner/src/python')

from business_learner.utils.task_metadata import TaskMetadataManager, RecorderInfo

def test_operator_name():
    """测试 operator_name 是否正确读取"""
    task_path = "/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778202281796"
    
    # 创建管理器
    manager = TaskMetadataManager(task_path)
    
    # 加载元数据
    metadata = manager.load_metadata()
    
    print("="*70)
    print("Operator Name 测试")
    print("="*70)
    
    print(f"\n📋 Task ID: {metadata.task_id}")
    print(f"📋 Task Name: {metadata.task_name}")
    
    print(f"\n👤 Recorder Info:")
    print(f"   - user_id: {metadata.recorder.user_id}")
    print(f"   - user_name: {metadata.recorder.user_name}")
    print(f"   - operator_name: {metadata.recorder.operator_name}")
    print(f"   - recorded_at: {metadata.recorder.recorded_at}")
    
    # 验证
    if metadata.recorder.operator_name == "高一为":
        print("\n✅ SUCCESS: operator_name 正确读取为 '高一为'")
        return True
    else:
        print(f"\n❌ FAILED: operator_name 是 '{metadata.recorder.operator_name}'，期望 '高一为'")
        return False

if __name__ == "__main__":
    success = test_operator_name()
    sys.exit(0 if success else 1)
