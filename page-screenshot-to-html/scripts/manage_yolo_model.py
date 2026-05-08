#!/usr/bin/env python3
"""
YOLO模型管理工具
用于检查、下载和修复YOLOv5模型文件
"""

import os
import sys
import urllib.request
import argparse
from pathlib import Path

# 模型配置 - 使用YOLOv8（与ultralytics库兼容）
MODEL_CONFIG = {
    'yolov8n': {
        'filename': 'yolov8n.pt',
        'size_mb': 6,
        'min_size_bytes': 5000000,  # 5MB
        'urls': [
            'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt',
            'https://ghproxy.com/https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt',
        ]
    },
    'yolov8s': {
        'filename': 'yolov8s.pt',
        'size_mb': 22,
        'min_size_bytes': 15000000,  # 15MB
        'urls': [
            'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt',
            'https://ghproxy.com/https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt',
            'https://hub.fastgit.xyz/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt',
        ]
    },
    'yolov8m': {
        'filename': 'yolov8m.pt',
        'size_mb': 52,
        'min_size_bytes': 45000000,  # 45MB
        'urls': [
            'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt',
            'https://ghproxy.com/https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt',
        ]
    }
}


def get_possible_model_paths(model_name='yolov5s'):
    """获取所有可能的模型文件路径"""
    config = MODEL_CONFIG.get(model_name, MODEL_CONFIG['yolov5s'])
    filename = config['filename']
    
    paths = [
        # 当前目录
        os.path.join(os.getcwd(), filename),
        # 脚本所在目录
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
        # ultralytics 默认目录
        os.path.join(os.path.expanduser('~'), '.ultralytics', filename),
        # 系统临时目录
        os.path.join('/tmp', filename),
        # /usr/local/share
        os.path.join('/usr/local/share', filename),
    ]
    
    return paths


def check_model_file(filepath, min_size):
    """检查模型文件是否有效"""
    if not os.path.exists(filepath):
        return False, "文件不存在"
    
    file_size = os.path.getsize(filepath)
    if file_size < min_size:
        return False, f"文件太小 ({file_size} bytes), 可能已损坏"
    
    return True, f"文件正常 ({file_size / 1024 / 1024:.1f} MB)"


def find_model(model_name='yolov5s'):
    """查找模型文件"""
    config = MODEL_CONFIG.get(model_name, MODEL_CONFIG['yolov5s'])
    paths = get_possible_model_paths(model_name)
    
    print(f"🔍 查找 {config['filename']} 模型文件...")
    print(f"   期望大小: ~{config['size_mb']} MB")
    print()
    
    found_paths = []
    for path in paths:
        exists = os.path.exists(path)
        status = "✅ 存在" if exists else "❌ 不存在"
        
        if exists:
            is_valid, msg = check_model_file(path, config['min_size_bytes'])
            status_icon = "✅" if is_valid else "⚠️"
            print(f"   {status_icon} {path}")
            print(f"      {msg}")
            if is_valid:
                found_paths.append(path)
        else:
            print(f"   {status} {path}")
    
    print()
    if found_paths:
        print(f"✅ 找到 {len(found_paths)} 个有效的模型文件")
        return found_paths[0]  # 返回第一个有效的
    else:
        print("❌ 未找到有效的模型文件")
        return None


def download_model(model_name='yolov5s', target_dir=None):
    """下载模型文件"""
    config = MODEL_CONFIG.get(model_name, MODEL_CONFIG['yolov5s'])
    filename = config['filename']
    
    # 确定下载目录
    if target_dir is None:
        # 默认下载到脚本所在目录
        target_dir = os.path.dirname(os.path.abspath(__file__))
    
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)
    
    print(f"📥 开始下载 {filename}...")
    print(f"   目标路径: {target_path}")
    print(f"   期望大小: ~{config['size_mb']} MB")
    print()
    
    # 尝试多个下载源
    for i, url in enumerate(config['urls'], 1):
        try:
            print(f"   尝试源 {i}/{len(config['urls'])}: {url[:60]}...")
            
            # 显示下载进度
            def report_progress(block_num, block_size, total_size):
                downloaded = block_num * block_size
                percent = min(downloaded * 100 / total_size, 100)
                sys.stdout.write(f"\r   进度: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)")
                sys.stdout.flush()
            
            urllib.request.urlretrieve(url, target_path, reporthook=report_progress)
            print()  # 换行
            
            # 验证下载的文件
            is_valid, msg = check_model_file(target_path, config['min_size_bytes'])
            if is_valid:
                print(f"✅ 下载成功: {target_path}")
                print(f"   {msg}")
                return target_path
            else:
                print(f"⚠️ 下载的文件验证失败: {msg}")
                os.remove(target_path)
                
        except Exception as e:
            print(f"\n   ❌ 下载失败: {e}")
            if os.path.exists(target_path):
                os.remove(target_path)
            continue
    
    print("\n❌ 所有下载源都失败")
    return None


def remove_corrupted_models(model_name='yolov5s'):
    """删除损坏的模型文件"""
    config = MODEL_CONFIG.get(model_name, MODEL_CONFIG['yolov5s'])
    paths = get_possible_model_paths(model_name)
    
    print(f"🧹 清理损坏的 {config['filename']} 模型文件...")
    removed = 0
    
    for path in paths:
        if os.path.exists(path):
            is_valid, msg = check_model_file(path, config['min_size_bytes'])
            if not is_valid:
                try:
                    os.remove(path)
                    print(f"   🗑️  已删除: {path}")
                    removed += 1
                except Exception as e:
                    print(f"   ❌ 删除失败 {path}: {e}")
    
    if removed == 0:
        print("   没有需要清理的文件")
    else:
        print(f"   共清理 {removed} 个文件")
    
    return removed


def install_model(model_name='yolov5s', target_dir=None):
    """安装模型（检查+下载）"""
    print(f"{'='*60}")
    print(f"安装YOLO模型: {model_name}")
    print(f"{'='*60}\n")
    
    # 1. 先查找现有模型
    existing = find_model(model_name)
    if existing:
        print(f"\n✅ 模型已安装: {existing}")
        return existing
    
    # 2. 清理可能损坏的文件
    remove_corrupted_models(model_name)
    
    # 3. 下载新模型
    print()
    downloaded = download_model(model_name, target_dir)
    
    if downloaded:
        print(f"\n✅ 模型安装成功!")
        print(f"   路径: {downloaded}")
        return downloaded
    else:
        print(f"\n❌ 模型安装失败")
        return None


def verify_model(model_name='yolov5s'):
    """验证模型是否可以正常加载"""
    print(f"{'='*60}")
    print(f"验证YOLO模型: {model_name}")
    print(f"{'='*60}\n")
    
    model_path = find_model(model_name)
    if not model_path:
        print("❌ 未找到模型文件")
        return False
    
    print(f"\n🧪 尝试加载模型...")
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        print(f"✅ 模型加载成功!")
        print(f"   模型类型: {model.type}")
        print(f"   模型任务: {model.task}")
        return True
    except ImportError:
        print("❌ 未安装 ultralytics 库")
        print("   请运行: pip install ultralytics")
        return False
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='YOLO模型管理工具 - 检查、下载和修复YOLOv5模型',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 检查模型状态
  python3 manage_yolo_model.py check
  
  # 安装模型（自动检查+下载）
  python3 manage_yolo_model.py install
  
  # 验证模型是否可以加载
  python3 manage_yolo_model.py verify
  
  # 清理损坏的模型文件
  python3 manage_yolo_model.py clean
  
  # 强制重新下载
  python3 manage_yolo_model.py reinstall
  
  # 指定模型类型（默认yolov5s）
  python3 manage_yolo_model.py install --model yolov5m
  
  # 指定下载目录
  python3 manage_yolo_model.py install --dir /path/to/models
        '''
    )
    
    parser.add_argument(
        'action',
        choices=['check', 'install', 'verify', 'clean', 'reinstall', 'download'],
        help='要执行的操作'
    )
    
    parser.add_argument(
        '--model', '-m',
        choices=['yolov8n', 'yolov8s', 'yolov8m'],
        default='yolov8s',
        help='模型类型 (默认: yolov8s)'
    )
    
    parser.add_argument(
        '--dir', '-d',
        default=None,
        help='模型下载目录 (默认: 脚本所在目录)'
    )
    
    args = parser.parse_args()
    
    # 执行操作
    if args.action == 'check':
        find_model(args.model)
        
    elif args.action == 'install':
        install_model(args.model, args.dir)
        
    elif args.action == 'verify':
        verify_model(args.model)
        
    elif args.action == 'clean':
        remove_corrupted_models(args.model)
        
    elif args.action == 'reinstall':
        remove_corrupted_models(args.model)
        print()
        install_model(args.model, args.dir)
        
    elif args.action == 'download':
        download_model(args.model, args.dir)
    
    print()


if __name__ == '__main__':
    main()
