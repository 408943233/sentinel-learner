#!/usr/bin/env python3
"""
视频录制模块 - 录制浏览器操作过程为视频文件
"""
import os
import cv2
import numpy as np
import threading
import queue
from typing import Optional, Callable, Dict
from datetime import datetime
import tempfile
import time


class VideoRecorder:
    """视频录制器"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.is_recording = False
        
        # 视频写入器
        self.video_writer: Optional[cv2.VideoWriter] = None
        self.video_path: Optional[str] = None
        
        # 录制参数
        self.fps = 10  # 帧率
        self.frame_size = (1280, 800)  # 默认分辨率
        
        # 帧队列
        self.frame_queue: queue.Queue = queue.Queue(maxsize=30)
        
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
        
        if self.on_recording_started:
            self.on_recording_started(self.video_path)
            
        return self.video_path
        
    def _recording_loop(self):
        """录制循环（在独立线程中运行）"""
        while not self._stop_event.is_set() or not self.frame_queue.empty():
            try:
                # 获取帧（阻塞等待，最多1秒）
                frame_data = self.frame_queue.get(timeout=1.0)
                
                if frame_data is None:  # 结束信号
                    break
                    
                # 写入视频
                if self.video_writer:
                    self.video_writer.write(frame_data)
                    self.frame_count += 1
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ 录制帧失败: {e}")
                
    def add_frame(self, screenshot_path: str):
        """添加一帧到视频"""
        print(f"🎥 add_frame 被调用: {screenshot_path}")
        
        if not self.is_recording or not self.video_writer:
            print(f"🎥 跳过: is_recording={self.is_recording}, video_writer={self.video_writer}")
            return
            
        try:
            # 读取截图
            frame = cv2.imread(screenshot_path)
            print(f"🎥 读取截图: shape={frame.shape if frame is not None else None}")
            
            if frame is None:
                print(f"⚠️ 无法读取截图: {screenshot_path}")
                return
                
            # 调整大小以匹配视频尺寸
            if (frame.shape[1], frame.shape[0]) != self.frame_size:
                frame = cv2.resize(frame, self.frame_size)
                
            # 添加时间戳水印
            frame = self._add_timestamp(frame)
            
            # 添加到队列（非阻塞）
            try:
                self.frame_queue.put_nowait(frame)
                print(f"🎥 帧已添加到队列, 队列大小: {self.frame_queue.qsize()}")
            except queue.Full:
                print(f"🎥 队列满，丢弃旧帧")
                # 队列满，丢弃最旧的帧
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except:
                    pass
                    
            if self.on_frame_captured:
                self.on_frame_captured(self.frame_count)
                
        except Exception as e:
            print(f"⚠️ 添加帧失败: {e}")
            import traceback
            traceback.print_exc()
            
    def add_frame_from_bytes(self, frame_bytes: bytes, width: int, height: int):
        """从字节数据添加一帧"""
        if not self.is_recording or not self.video_writer:
            return
            
        try:
            # 将字节转换为numpy数组
            nparr = np.frombuffer(frame_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return
                
            # 调整大小
            if (frame.shape[1], frame.shape[0]) != self.frame_size:
                frame = cv2.resize(frame, self.frame_size)
                
            # 添加时间戳
            frame = self._add_timestamp(frame)
            
            # 添加到队列
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except:
                    pass
                    
        except Exception as e:
            print(f"⚠️ 添加帧失败: {e}")
            
    def _add_timestamp(self, frame: np.ndarray) -> np.ndarray:
        """在帧上添加时间戳"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 添加半透明背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (250, 40), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        
        # 添加文字
        cv2.putText(
            frame,
            timestamp,
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )
        
        # 添加录制指示器
        cv2.circle(frame, (frame.shape[1] - 30, 30), 10, (0, 0, 255), -1)
        
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
        
    def set_frame_size(self, width: int, height: int):
        """设置视频分辨率"""
        self.frame_size = (width, height)
        
    def set_fps(self, fps: int):
        """设置帧率"""
        self.fps = fps
        
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


class ScreenshotCapture:
    """截图捕获器 - 事件驱动，只在用户操作时截图"""
    
    def __init__(self, video_recorder: VideoRecorder):
        self.video_recorder = video_recorder
        self.is_capturing = False
        self.get_screenshot_func: Optional[Callable] = None
        
        # 防抖控制 - 避免短时间内重复截图
        self._last_capture_time = 0
        self._min_interval = 3.0  # 最少3秒才截一次
        
    def start_capture(self, screenshot_func: Callable):
        """开始捕获（初始化，不启动定时器）"""
        self.get_screenshot_func = screenshot_func
        self.is_capturing = True
        print("📸 事件驱动截图已启动（只在操作时截图，无定时截图）")
        
    def capture_on_action(self):
        """
        在操作发生时截图 - 由外部调用
        这是主要的截图入口，只在用户操作时调用
        """
        print(f"📸 capture_on_action 被调用, is_capturing={self.is_capturing}, is_recording={self.video_recorder.is_recording}")
        
        if not self.is_capturing or not self.video_recorder.is_recording:
            print(f"📸 跳过截图: is_capturing={self.is_capturing}, is_recording={self.video_recorder.is_recording}")
            return
            
        import time
        current_time = time.time()
        
        # 防抖检查
        if current_time - self._last_capture_time < self._min_interval:
            print(f"📸 跳过截图: 防抖间隔未过")
            return
            
        self._last_capture_time = current_time
        print(f"📸 开始截图...")
        
        # 在后台线程执行截图，不阻塞主流程
        import threading
        def do_capture():
            try:
                if self.get_screenshot_func:
                    print(f"📸 调用截图函数...")
                    screenshot_path = self.get_screenshot_func()
                    print(f"📸 截图路径: {screenshot_path}")
                    if screenshot_path and os.path.exists(screenshot_path):
                        print(f"📸 添加帧到视频...")
                        self.video_recorder.add_frame(screenshot_path)
                        print(f"📸 帧已添加")
                    else:
                        print(f"⚠️ 截图文件不存在: {screenshot_path}")
                else:
                    print(f"⚠️ 截图函数未设置")
            except Exception as e:
                print(f"⚠️ 截图失败: {e}")
                import traceback
                traceback.print_exc()
        
        threading.Thread(target=do_capture, daemon=True).start()
        
    def stop_capture(self):
        """停止捕获"""
        self.is_capturing = False
        print("📸 截图已停止")
