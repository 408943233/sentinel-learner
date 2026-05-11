#!/usr/bin/env python3
"""
批量图片转HTML工具
"""

import os
import sys
import argparse
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screenshot_to_html import ScreenshotToHTML


def batch_convert(input_dir, output_dir=None, use_kimi=True):
    """批量转换目录中的所有图片"""
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    # 获取所有图片文件
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return
    
    image_files = [f for f in input_path.iterdir() 
                   if f.is_file() and f.suffix.lower() in image_extensions]
    
    if not image_files:
        print(f"❌ 未找到图片文件: {input_dir}")
        return
    
    print(f"📁 找到 {len(image_files)} 个图片文件")
    print(f"📂 输入目录: {input_dir}")
    
    # 设置输出目录
    if output_dir is None:
        # 默认输出到项目目录下的output文件夹
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(script_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)
    print(f"📂 输出目录: {output_dir}")
    print()
    
    # 批量转换
    success_count = 0
    failed_files = []
    
    for i, image_file in enumerate(image_files, 1):
        print(f"\n{'='*60}")
        print(f"处理 {i}/{len(image_files)}: {image_file.name}")
        print(f"{'='*60}")
        
        # 生成输出文件名（保持原名，只改扩展名）
        output_name = image_file.stem + '.html'
        output_path = os.path.join(output_dir, output_name)
        
        try:
            # 为每个图片创建转换器实例
            converter = ScreenshotToHTML(
                image_path=str(image_file),
                output_path=output_path,
                use_kimi=use_kimi
            )
            
            # 转换图片
            converter.run()
            
            # 检查输出文件是否生成
            if os.path.exists(output_path):
                print(f"✅ 成功: {output_name}")
                success_count += 1
            else:
                print(f"❌ 失败: 未生成HTML文件")
                failed_files.append(image_file.name)
                
        except Exception as e:
            print(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            failed_files.append(image_file.name)
    
    # 总结
    print(f"\n{'='*60}")
    print("批量转换完成")
    print(f"{'='*60}")
    print(f"✅ 成功: {success_count}/{len(image_files)}")
    print(f"❌ 失败: {len(failed_files)}/{len(image_files)}")
    
    if failed_files:
        print(f"\n失败的文件:")
        for f in failed_files:
            print(f"  - {f}")
    
    print(f"\n输出目录: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description='批量将图片转换为HTML',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 转换指定目录中的所有图片
  python3 batch_convert.py /path/to/images
  
  # 指定输出目录
  python3 batch_convert.py /path/to/images --output /path/to/output
  
  # 不使用Kimi API（仅使用本地处理）
  python3 batch_convert.py /path/to/images --no-kimi
        '''
    )
    
    parser.add_argument(
        'input_dir',
        help='输入图片目录'
    )
    
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='输出HTML目录 (默认与输入目录相同)'
    )
    
    parser.add_argument(
        '--no-kimi',
        action='store_true',
        help='不使用Kimi API，仅使用本地处理'
    )
    
    args = parser.parse_args()
    
    # 批量转换
    batch_convert(
        input_dir=args.input_dir,
        output_dir=args.output,
        use_kimi=not args.no_kimi
    )


if __name__ == '__main__':
    main()
