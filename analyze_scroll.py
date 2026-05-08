#!/usr/bin/env python3
"""分析视频中的滚动行为"""
import cv2
import numpy as np
from pathlib import Path
from skimage.metrics import structural_similarity as ssim

video_path = '/Users/gaoyiwei/Documents/trae_projects/openclaw/output/collections/task_11_www.chinastock.com.cn_1778034751731/video/raw_record.mp4'

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps

print(f'视频信息: FPS={fps:.1f}, 总帧数={total_frames}, 时长={duration:.2f}秒')
print()

# 分析13-17秒之间的帧变化
start_sec = 13
end_sec = 17
start_frame = int(start_sec * fps)
end_frame = int(end_sec * fps)

print(f'分析 {start_sec}-{end_sec} 秒之间的帧变化...')
print()

# 读取第一帧作为参考
cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
ret, prev_frame = cap.read()
if not ret:
    print("无法读取视频")
    exit()

prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# 每10帧采样一次
sample_interval = 10
frame_idx = start_frame + sample_interval

significant_changes = []

while frame_idx <= end_frame:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        break
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # 计算相似度
    similarity = ssim(prev_gray, gray)
    change = 1.0 - similarity
    
    time_sec = frame_idx / fps
    
    # 如果变化超过30%，记录为可能的滚动
    if change > 0.30:
        significant_changes.append({
            'time': time_sec,
            'frame': frame_idx,
            'change': change
        })
        print(f"  时间 {time_sec:.2f}s (帧{frame_idx}): 变化 {change:.1%} - 可能是滚动")
        
        # 保存这个关键帧
        output_path = f'/tmp/scroll_frame_{time_sec:.2f}.jpg'
        cv2.imwrite(output_path, frame)
        
        # 更新参考帧
        prev_gray = gray
    
    frame_idx += sample_interval

cap.release()

print()
print(f"共检测到 {len(significant_changes)} 次显著变化")
if significant_changes:
    print("可能用户在13-17秒之间进行了多次滚动操作")
    print("但 training_manifest.jsonl 只记录了一次 scroll 事件")
    print("这是 sentinel-browser 采集的遗漏！")
