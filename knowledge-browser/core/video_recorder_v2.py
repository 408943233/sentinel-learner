#!/usr/bin/env python3
"""
视频录制模块 V2 - 事件驱动，无干扰录制
只在用户操作时截图，不采用定时截图
"""
import os
import cv2
import threading
import queue
import tempfile
from typing import Optional, Callable, Dict
from datetime import datetime


class VideoRecorderV2:
    """视频录制器 V2 - 事件驱动"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.is_recording = False
        
        # 视频写入器
        self.video_writer: Optional[cv2.VideoWriter] = None
        self.video_path: Optional[str] = None
        
        # 录制参数
        self.fps = 2  # 降低帧率到2fps
        self.frame_size = (1280, 800)
        
        # 帧队列
        self.frame_queue: queue.Queue = queue.Queue(maxsize=10)
        
        # 录制线程
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调函数
        self.on_frame_captured: Optional[Callable] = None
        self.on_recording_started: Optional[Callable] = None
        self.on_recording_stopped: Optional[Callable] = None
        
        # 统计
        self.frame_count = 0
        self.start_time: Optional[datetime] = None
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
    def start_recording(self, custom_name: Optional[str] = None) -> str:
        """开始录制视频"""
        if self.is_recording:
            print("⚠️ 视频录制已在进行中")
            return self.video_path
            
        # 生成视频文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{custom_name or 'recording'}_{timestamp}.mp4"
        self.video_path = os.path.join(self.output_dir, filename)
        
        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            self.video_path,
            fourcc,
            self.fps,
            self.frame_size
        )
        
        if not self.video_writer.isOpened():
            raise RuntimeError("无法创建视频文件")
            
        self.is_recording = True
        self.frame_count = 0
        self.start_time = datetime.now()
        self._stop_event.clear()
        
        # 启动录制线程
        self._recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._recording_thread.start()
        
        print(f"🎥 视频录制开始: {self.video_path}")
        print(f"   模式: 事件驱动（只在操作时截图）")
        
        if self.on_recording_started:
            self.on_recording_started(self.video_path)
            
        return self.video_path
        
    def _recording_loop(self):
        """录制循环 - 处理帧队列"""
        while not self._stop_event.is_set():
            try:
                # 从队列获取帧（阻塞等待）
                frame = self.frame_queue.get(timeout=0.5)
                
                if frame is None:  # 结束信号
                    break
                    
                if self.video_writer:
                    self.video_writer.write(frame)
                    self.frame_count += 1
                    
                    if self.on_frame_captured:
                        self.on_frame_captured(self.frame_count)
                        
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ 录制错误: {e}")
                
    def capture_frame(self, screenshot_path: str):
        """
        捕获一帧（由外部调用，如操作事件触发）
        这是主要的截图入口，只在用户操作时调用
        """
        if not self.is_recording or not self.video_writer:
            return
            
        try:
            # 读取截图
            frame = cv2.imread(screenshot_path)
            if frame is None:
                return
                
            # 调整大小
            if (frame.shape[1], frame.shape[0]) != self.frame_size:
                frame = cv2.resize(frame, self.frame_size)
                
            # 添加时间戳
            frame = self._add_timestamp(frame)
            
            # 添加到队列（非阻塞）
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                # 队列满，丢弃最旧的帧
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ 添加帧失败: {e}")
            
    def _add_timestamp(self, frame):
        """添加时间戳水印"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            timestamp,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )
        return frame
        
    def stop_recording(self) -> Dict:
        """停止录制视频"""
        if not self.is_recording:
            return {"error": "没有正在进行的录制"}
            
        self.is_recording = False
        self._stop_event.set()
        
        # 发送结束信号
        try:
            self.frame_queue.put_nowait(None)
        except:
            pass
            
        # 等待录制线程结束
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=5)
            
        # 释放视频写入器
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            
        # 计算录制信息
        duration = 0
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            
        result = {
            "video_path": self.video_path,
            "frame_count": self.frame_count,
            "duration": duration,
            "fps": self.fps,
            "resolution": self.frame_size
        }
        
        print(f"✅ 视频录制完成: {self.video_path}")
        print(f"   帧数: {self.frame_count}, 时长: {duration:.1f}秒")
        
        if self.on_recording_stopped:
            self.on_recording_stopped(result)
            
        return result
        
    def get_recording_info(self) -> Dict:
        """获取当前录制信息"""
        if not self.is_recording:
            return {"is_recording": False}
            
        duration = 0
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            
        return {
            "is_recording": True,
            "video_path": self.video_path,
            "frame_count": self.frame_count,
            "duration": duration,
            "fps": self.fps
        }
