"""
长图拼接脚本 - 修正版
正确逻辑：
1. result = img[0]
2. for i from 1 to n-1:
3.   result = merge(result, img[i])
"""
import os
import sys
import json
import cv2
import numpy as np


def find_overlap_smart(img_a, img_b):
    """
    检测两张图片的最佳重叠位置
    在img_a的底部和img_b的顶部之间搜索
    返回: (img_a中的行, img_b中的行, 重叠像素数)
    """
    h_a, w_a = img_a.shape[:2]
    h_b, w_b = img_b.shape[:2]
    
    if w_a != w_b:
        return None, None, 0
    
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
    
    # 搜索范围
    search_start_a = int(h_a * 0.5)  # 从img_a的中间偏下开始
    search_end_a = h_a
    search_start_b = 0
    search_end_b = int(h_b * 0.5)  # 搜索到img_b的中间偏上
    
    best_ncc = -1.0
    best_line_a = 0
    best_line_b = 0
    window_h = 80  # 比较窗口高度
    
    # 粗略搜索（步长10）
    for line_a in range(search_start_a, h_a - window_h, 10):
        win_a = gray_a[line_a:line_a+window_h, :].astype(np.float64)
        
        for line_b in range(search_start_b, min(search_end_b - window_h, line_a), 10):
            win_b = gray_b[line_b:line_b+window_h, :].astype(np.float64)
            
            # 计算NCC
            m_a, m_b = np.mean(win_a), np.mean(win_b)
            s_a, s_b = np.std(win_a), np.std(win_b)
            
            if s_a < 1e-6 or s_b < 1e-6:
                continue
            
            ncc = np.mean((win_a - m_a) * (win_b - m_b)) / (s_a * s_b)
            
            if ncc > best_ncc:
                best_ncc = ncc
                best_line_a = line_a
                best_line_b = line_b
    
    # 精细化搜索（步长1）
    if best_ncc > 0:
        refine_best = best_ncc
        refine_a = best_line_a
        refine_b = best_line_b
        
        for da in range(-5, 6):
            for db in range(-5, 6):
                la = best_line_a + da
                lb = best_line_b + db
                
                if la < 0 or la >= h_a - window_h or lb < 0 or lb >= h_b - window_h:
                    continue
                
                wa = gray_a[la:la+window_h, :].astype(np.float64)
                wb = gray_b[lb:lb+window_h, :].astype(np.float64)
                
                ma, mb = np.mean(wa), np.mean(wb)
                sa, sb = np.std(wa), np.std(wb)
                
                if sa < 1e-6 or sb < 1e-6:
                    continue
                
                ncc = np.mean((wa - ma) * (wb - mb)) / (sa * sb)
                
                if ncc > refine_best:
                    refine_best = ncc
                    refine_a = la
                    refine_b = lb
        
        best_ncc = refine_best
        best_line_a = refine_a
        best_line_b = refine_b
    
    overlap = h_a - best_line_a + best_line_b
    
    return best_line_a, best_line_b, overlap


def merge_images(result_img, next_img, line_result, line_next, overlap):
    """
    合并两张图片（硬切，无渐变）
    - result_img: 当前结果图
    - next_img: 下一张图
    - line_result: result_img中的重叠线
    - line_next: next_img中的重叠线
    - overlap: 重叠像素数
    """
    h_result, w = result_img.shape[:2]
    h_next = next_img.shape[0]
    
    # result保留：从头到 line_result
    result_keep = line_result
    
    # next保留：从 line_next 开始到尾
    next_keep = h_next - line_next
    
    # 新高度
    new_height = result_keep + next_keep
    
    # 创建新图
    new_img = np.zeros((new_height, w, 3), dtype=np.uint8)
    
    # 1. 复制result的非重叠部分
    new_img[0:result_keep, :] = result_img[0:result_keep, :]
    
    # 2. 复制next的非重叠部分
    new_img[result_keep:result_keep + next_keep, :] = next_img[line_next:, :]
    
    return new_img


def stitch_images(directory, min_overlap_threshold=100, min_ncc_threshold=0.5):
    """
    拼接指定目录下的所有图片
    
    Args:
        directory: 图片目录
        min_overlap_threshold: 最小重叠像素数阈值，低于此值认为无重叠
        min_ncc_threshold: 最小NCC相似度阈值，低于此值认为匹配失败
    """
    files = sorted([f for f in os.listdir(directory) if f.lower().endswith('.png')])
    
    if len(files) < 2:
        print(f"需要至少2张图片，只有{len(files)}张")
        return None, "INSUFFICIENT_IMAGES"
    
    print(f"加载了 {len(files)} 张截图，开始拼接...\n")
    print(f"重叠检测阈值: 最小重叠={min_overlap_threshold}px, 最小NCC={min_ncc_threshold}\n")
    
    # 加载所有图片
    images = []
    for f in files:
        img = cv2.imread(os.path.join(directory, f))
        if img is not None:
            images.append(img)
    
    # 正确的拼接逻辑：
    # result = images[0]
    # for i from 1 to n-1:
    #   result = merge(result, images[i])
    
    result = images[0]
    print(f"初始: {result.shape[1]}x{result.shape[0]}")
    
    # 记录最佳NCC值用于判断是否有效匹配
    best_ncc_overall = 1.0  # 第一张图与自己完全匹配
    
    for i in range(1, len(images)):
        print(f"\n[{i+1}/{len(images)}] 与第{i+1}张图拼接...")
        
        # 检测当前结果与下一张图的重叠
        line_result, line_next, overlap = find_overlap_smart(result, images[i])
        
        # 检查1: 是否检测到有效重叠区域
        if overlap <= 0:
            print(f"  ✗ 错误: 未检测到任何重叠区域")
            print(f"     图片{i}和图片{i+1}可能是完全不同的页面内容")
            return None, "NO_OVERLAP_DETECTED"
        
        # 检查2: 重叠区域是否足够大
        if overlap < min_overlap_threshold:
            print(f"  ✗ 错误: 重叠区域过小 ({overlap}px < {min_overlap_threshold}px)")
            print(f"     图片{i}和图片{i+1}可能不是连续的滚动截图")
            return None, "INSUFFICIENT_OVERLAP"
        
        # 检查3: 通过NCC值判断是否真正匹配
        # 重新计算最佳NCC值
        gray_result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        gray_next = cv2.cvtColor(images[i], cv2.COLOR_BGR2GRAY)
        window_h = 80
        
        if line_result + window_h <= gray_result.shape[0] and line_next + window_h <= gray_next.shape[0]:
            win_result = gray_result[line_result:line_result+window_h, :].astype(np.float64)
            win_next = gray_next[line_next:line_next+window_h, :].astype(np.float64)
            
            m_r, m_n = np.mean(win_result), np.mean(win_next)
            s_r, s_n = np.std(win_result), np.std(win_next)
            
            if s_r > 1e-6 and s_n > 1e-6:
                ncc = np.mean((win_result - m_r) * (win_next - m_n)) / (s_r * s_n)
                best_ncc_overall = ncc
                
                if ncc < min_ncc_threshold:
                    print(f"  ✗ 错误: 图片相似度过低 (NCC={ncc:.3f} < {min_ncc_threshold})")
                    print(f"     图片{i}和图片{i+1}可能不是同一页面的滚动截图")
                    return None, "LOW_SIMILARITY"
                
                print(f"  ✓ 检测到重叠: {overlap}px, NCC相似度: {ncc:.3f}")
            else:
                print(f"  ⚠ 警告: 无法计算相似度，继续拼接")
                print(f"  ✓ 检测到重叠: {overlap}px")
        else:
            print(f"  ✓ 检测到重叠: {overlap}px")
        
        # 合并（使用硬切，无渐变）
        result = merge_images(result, images[i], line_result, line_next, overlap)
        
        print(f"  ✓ 当前尺寸: {result.shape[1]}x{result.shape[0]}")
    
    return result, "SUCCESS"


def main():
    if len(sys.argv) < 2:
        directory = "screenshots"
    else:
        directory = sys.argv[1]
    
    if not os.path.isabs(directory):
        directory = os.path.join(os.path.dirname(__file__), directory)
    
    if not os.path.exists(directory):
        print(f"错误: 目录 '{directory}' 不存在")
        sys.exit(1)
    
    result, status = stitch_images(directory)
    
    if result is not None:
        # 保存结果
        output_dir = os.path.join(directory, 'stitched')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'result_stitched.png')
        cv2.imwrite(output_path, result)
        
        print(f"\n{'='*60}")
        print("✓ 拼接完成!")
        print(f"{'='*60}")
        print(f"  输出尺寸: {result.shape[1]} x {result.shape[0]}")
        print(f"  保存路径: {output_path}")
        print(f"{'='*60}")
        
        # 输出JSON结果
        print(json.dumps({
            'success': True,
            'width': int(result.shape[1]),
            'height': int(result.shape[0]),
            'output_path': output_path,
            'status': status
        }))
    else:
        # 拼接失败，返回具体错误原因
        error_messages = {
            'INSUFFICIENT_IMAGES': '图片数量不足（至少需要2张）',
            'NO_OVERLAP_DETECTED': '未检测到重叠区域，图片可能来自不同页面',
            'INSUFFICIENT_OVERLAP': '重叠区域过小，可能不是连续的滚动截图',
            'LOW_SIMILARITY': '图片相似度过低，可能不是同一页面的滚动截图'
        }
        error_msg = error_messages.get(status, f'拼接失败: {status}')
        
        print(f"\n{'='*60}")
        print("✗ 拼接失败!")
        print(f"{'='*60}")
        print(f"  原因: {error_msg}")
        print(f"{'='*60}")
        
        print(json.dumps({
            'success': False, 
            'error': error_msg,
            'status': status
        }))


if __name__ == "__main__":
    main()
