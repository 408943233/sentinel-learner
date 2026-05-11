#!/usr/bin/env python3
"""
屏幕录制模块 - 使用MSS进行系统级屏幕录制
提供类似QuickTime Player的流畅录制体验
"""
import os
import cv2
import numpy as np
import threading
import queue
from typing import Optional, Callable, Dict, Tuple
from datetime import datetime
import time


class ScreenRecorder:
    """
    屏幕录制器 - 使用MSS库进行高性能屏幕捕获
    优点：
    - 30+ fps 流畅录制
    - 不影响被录制应用
    - 硬件加速
    """
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.is_recording = False
        
        # 视频写入器
        self.video_writer: Optional[cv2.VideoWriter] = None
        self.video_path: Optional[str] = None
        
        # 录制参数
        self.fps = 30  # 高帧率
        self.quality = 80  # 编码质量
        
        # 录制区域（默认全屏）
        self.capture_region: Optional[Tuple[int, int, int, int]] = None
        
        # 窗口标题（用于自动跟踪窗口位置）
        self.window_title: Optional[str] = None
        
        # 帧队列
        self.frame_queue: queue.Queue = queue.Queue(maxsize=60)
        
        # 录制线程
        self._recording_thread: Optional[threading.Thread] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调函数
        self.on_frame_captured: Optional[Callable] = None
        self.on_recording_started: Optional[Callable] = None
        self.on_recording_stopped: Optional[Callable] = None
        
        # 统计
        self.frame_count = 0
        self.start_time: Optional[datetime] = None
        self.dropped_frames = 0
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
    def start_recording(self, custom_name: Optional[str] = None, 
                       region: Optional[Tuple[int, int, int, int]] = None,
                       window_title: Optional[str] = None) -> str:
        """
        开始录制屏幕
        
        Args:
            custom_name: 自定义文件名
            region: 录制区域 (left, top, width, height)，None表示全屏或自动跟踪窗口
            window_title: 窗口标题关键字，用于自动跟踪窗口位置
        """
        if self.is_recording:
            print("⚠️ 屏幕录制已在进行中")
            return self.video_path
            
        try:
            import mss
        except ImportError:
            print("⚠️ 未安装mss库，正在安装...")
            import subprocess
            subprocess.run(["pip", "install", "mss"], check=True)
            import mss
            
        self.capture_region = region
        self.window_title = window_title
        
        # 生成视频文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{custom_name or 'screen_recording'}_{timestamp}.mp4"
        self.video_path = os.path.join(self.output_dir, filename)
        
        # 获取录制区域尺寸
        if window_title:
            # 如果指定了窗口标题，获取窗口大小
            window_region = self._get_window_region()
            if window_region:
                width, height = window_region[2], window_region[3]
                print(f"   窗口大小: {width}x{height}")
            else:
                # 如果获取失败，使用屏幕尺寸
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    width, height = monitor["width"], monitor["height"]
        elif region:
            width, height = region[2], region[3]
        else:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                width, height = monitor["width"], monitor["height"]
            
        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            self.video_path,
            fourcc,
            self.fps,
            (width, height)
        )
        
        if not self.video_writer.isOpened():
            raise RuntimeError("无法创建视频文件")
            
        self.is_recording = True
        self.frame_count = 0
        self.dropped_frames = 0
        self.start_time = datetime.now()
        self._stop_event.clear()
        
        # 启动捕获线程
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        # 启动编码线程
        self._recording_thread = threading.Thread(target=self._encoding_loop, daemon=True)
        self._recording_thread.start()
        
        print(f"🎥 屏幕录制开始: {self.video_path}")
        print(f"   分辨率: {width}x{height}, 帧率: {self.fps}fps")
        if region:
            print(f"   区域: {region}")
        if window_title:
            print(f"   跟踪窗口: {window_title}")
        
        if self.on_recording_started:
            self.on_recording_started(self.video_path)
            
        return self.video_path
        
    def _get_window_region(self) -> Optional[Tuple[int, int, int, int]]:
        """获取窗口位置（macOS）"""
        if not self.window_title:
            print(f"   没有窗口标题，使用固定区域: {self.capture_region}")
            return self.capture_region

        try:
            # 使用 AppleScript 获取窗口位置
            import subprocess
            script = '''
            tell application "System Events"
                try
                    tell process "Chromium"
                        if exists window 1 then
                            set winPos to position of window 1
                            set winSize to size of window 1
                            return (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winSize) & "," & (item 2 of winSize)
                        else
                            return "no_window"
                        end if
                    end tell
                on error errMsg
                    return "error:" & errMsg
                end try
            end tell
            '''
            print(f"   执行 AppleScript 获取窗口位置...")
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=2
            )
            output = result.stdout.strip()
            stderr = result.stderr.strip()
            print(f"   AppleScript 结果: returncode={result.returncode}, stdout={output}, stderr={stderr}")

            if result.returncode == 0 and output != "no_window" and not output.startswith("error:"):
                parts = output.split(',')
                if len(parts) == 4:
                    try:
                        region = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
                        print(f"   获取到窗口区域: {region}")
                        return region
                    except Exception as e:
                        print(f"   解析窗口区域失败: {e}")
                else:
                    print(f"   窗口区域格式错误: {parts}")
            else:
                print(f"   获取窗口失败: {output}")
        except Exception as e:
            print(f"⚠️ 获取窗口位置失败: {e}")

        print(f"   回退到固定区域: {self.capture_region}")
        return self.capture_region
        
    def _capture_loop(self):
        """屏幕捕获循环 - 高频率捕获屏幕"""
        import mss
        
        with mss.mss() as sct:
            target_interval = 1.0 / self.fps
            
            while not self._stop_event.is_set():
                start_time = time.time()
                
                try:
                    # 获取录制区域
                    if self.window_title:
                        region = self._get_window_region()
                        if region:
                            monitor = {"left": region[0], "top": region[1],
                                      "width": region[2], "height": region[3]}
                        else:
                            # 如果获取不到窗口位置，使用全屏
                            monitor = sct.monitors[0]
                    elif self.capture_region:
                        monitor = {"left": self.capture_region[0], "top": self.capture_region[1],
                                  "width": self.capture_region[2], "height": self.capture_region[3]}
                    else:
                        monitor = sct.monitors[0]
                        
                    # 捕获屏幕
                    screenshot = sct.grab(monitor)
                    
                    # 转换为numpy数组
                    frame = np.array(screenshot)
                    # BGRA -> BGR
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # 添加到队列（非阻塞，队列满则丢弃）
                    try:
                        self.frame_queue.put_nowait(frame)
                    except queue.Full:
                        self.dropped_frames += 1
                        
                except Exception as e:
                    print(f"⚠️ 屏幕捕获错误: {e}")
                    
                # 控制帧率
                elapsed = time.time() - start_time
                sleep_time = target_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
    def _encoding_loop(self):
        """视频编码循环"""
        while not self._stop_event.is_set() or not self.frame_queue.empty():
            try:
                # 获取帧（阻塞等待，最多1秒）
                frame = self.frame_queue.get(timeout=1.0)
                
                # 写入视频
                if self.video_writer:
                    self.video_writer.write(frame)
                    self.frame_count += 1
                    
                    if self.on_frame_captured:
                        self.on_frame_captured(self.frame_count)
                        
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ 编码错误: {e}")
                
    def stop_recording(self) -> Dict:
        """停止录制"""
        if not self.is_recording:
            return {"error": "没有正在进行的录制"}
            
        self.is_recording = False
        self._stop_event.set()
        
        # 等待线程结束
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=5)
            
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
            "dropped_frames": self.dropped_frames,
            "duration": duration,
            "fps": self.fps,
            "actual_fps": self.frame_count / duration if duration > 0 else 0
        }
        
        print(f"✅ 屏幕录制完成: {self.video_path}")
        print(f"   帧数: {self.frame_count}, 丢弃: {self.dropped_frames}")
        print(f"   时长: {duration:.1f}秒, 实际帧率: {result['actual_fps']:.1f}fps")
        
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
            "dropped_frames": self.dropped_frames,
            "duration": duration,
            "fps": self.fps,
            "queue_size": self.frame_queue.qsize()
        }


# 使用示例
if __name__ == "__main__":
    import time
    
    recorder = ScreenRecorder()
    
    print("开始录制屏幕（5秒）...")
    recorder.start_recording("test")
    
    time.sleep(5)
    
    result = recorder.stop_recording()
    print(f"录制完成: {result}")
