#!/usr/bin/env python3
"""
YOLO模型诊断工具
用于排查YOLO模型加载问题
"""

import sys
import os

def check_ultralytics():
    """检查ultralytics库"""
    print("="*60)
    print("1. 检查 ultralytics 库")
    print("="*60)
    
    try:
        import ultralytics
        print(f"✅ ultralytics 已安装")
        print(f"   版本: {ultralytics.__version__}")
        print(f"   路径: {ultralytics.__file__}")
        return True
    except ImportError as e:
        print(f"❌ ultralytics 未安装: {e}")
        print(f"   请运行: pip install ultralytics")
        return False

def check_torch():
    """检查PyTorch"""
    print("\n" + "="*60)
    print("2. 检查 PyTorch")
    print("="*60)
    
    try:
        import torch
        print(f"✅ PyTorch 已安装")
        print(f"   版本: {torch.__version__}")
        print(f"   CUDA可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   CUDA版本: {torch.version.cuda}")
        return True
    except ImportError as e:
        print(f"❌ PyTorch 未安装: {e}")
        print(f"   请运行: pip install torch")
        return False

def check_model_file():
    """检查模型文件"""
    print("\n" + "="*60)
    print("3. 检查模型文件")
    print("="*60)
    
    # 尝试多个可能的路径
    possible_paths = [
        '/root/.openclaw/extensions/page-screenshot-to-html/yolov5s.pt',
        os.path.expanduser('~/.openclaw/extensions/page-screenshot-to-html/yolov5s.pt'),
        'yolov5s.pt',
        os.path.join(os.path.dirname(__file__), 'yolov5s.pt'),
    ]
    
    for model_path in possible_paths:
        if os.path.exists(model_path):
            file_size = os.path.getsize(model_path)
            print(f"✅ 模型文件存在")
            print(f"   路径: {model_path}")
            print(f"   大小: {file_size / 1024 / 1024:.1f} MB")
            
            if os.access(model_path, os.R_OK):
                print(f"   可读: ✅")
                return model_path
            else:
                print(f"   可读: ❌ (权限问题)")
    
    print("❌ 未找到模型文件")
    return None

def try_load_model(model_path):
    """尝试加载模型"""
    print("\n" + "="*60)
    print("4. 尝试加载模型")
    print("="*60)
    
    try:
        from ultralytics import YOLO
        
        print(f"正在加载: {model_path}")
        model = YOLO(model_path)
        
        print(f"✅ 模型加载成功!")
        print(f"   模型类型: {model.type if hasattr(model, 'type') else 'unknown'}")
        print(f"   模型任务: {model.task if hasattr(model, 'task') else 'unknown'}")
        
        # 尝试进行一次推理
        print(f"\n   测试推理...")
        import torch
        dummy_input = torch.randn(1, 3, 640, 640)
        with torch.no_grad():
            result = model.predict(dummy_input, verbose=False)
        print(f"   ✅ 推理测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_numpy():
    """检查numpy版本"""
    print("\n" + "="*60)
    print("5. 检查 NumPy")
    print("="*60)
    
    try:
        import numpy as np
        print(f"✅ NumPy 已安装")
        print(f"   版本: {np.__version__}")
        
        # 检查版本兼容性
        version_parts = np.__version__.split('.')
        major = int(version_parts[0])
        if major >= 2:
            print(f"   ⚠️ 警告: NumPy 2.x 可能与YOLOv5不兼容")
            print(f"   建议: pip install numpy==1.26.4")
        
        return True
    except ImportError as e:
        print(f"❌ NumPy 未安装: {e}")
        return False

def suggest_fixes():
    """提供修复建议"""
    print("\n" + "="*60)
    print("修复建议")
    print("="*60)
    
    print("""
如果模型加载失败，请尝试以下步骤:

1. 重新安装 ultralytics:
   pip uninstall ultralytics -y
   pip install ultralytics

2. 降级 NumPy 到 1.x 版本:
   pip install numpy==1.26.4

3. 升级 PyTorch:
   pip install torch --upgrade

4. 清除缓存:
   rm -rf ~/.cache/ultralytics
   rm -rf ~/.cache/torch

5. 检查Python版本 (推荐 3.8-3.11):
   python3 --version

6. 完整重装:
   pip uninstall ultralytics torch torchvision -y
   pip install torch torchvision ultralytics
""")

def main():
    print("YOLO模型诊断工具")
    print("="*60)
    
    # 运行所有检查
    results = []
    
    results.append(("ultralytics", check_ultralytics()))
    results.append(("PyTorch", check_torch()))
    results.append(("NumPy", check_numpy()))
    
    model_path = check_model_file()
    if model_path:
        results.append(("模型加载", try_load_model(model_path)))
    
    # 总结
    print("\n" + "="*60)
    print("诊断总结")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {status}: {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ 所有检查通过，模型应该可以正常工作")
    else:
        print("\n❌ 部分检查失败")
        suggest_fixes()

if __name__ == '__main__':
    main()
