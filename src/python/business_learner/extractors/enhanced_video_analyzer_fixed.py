"""
增强版视频分析器 - 修复版
正确按页面分组并进行长图拼接
"""

import cv2
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
from collections import defaultdict
from urllib.parse import urlparse

from ..utils.models import VideoFrame
from ..config.settings import VIDEO_CONFIG
from ..utils.image_stitcher_skill import ImageStitcherSkill, StitchResult
from ..llm.vision_analyzer import VisionAnalyzer


class EnhancedVideoAnalyzerFixed:
    """增强版视频分析器 - 修复长图拼接逻辑"""
    
    def __init__(self, video_path: str, manifest_path: str, 
                 api_key: Optional[str] = None):
        """
        初始化分析器
        
        Args:
            video_path: 视频文件路径
            manifest_path: training_manifest.jsonl路径
            api_key: LLM API密钥（可选）
        """
        self.video_path = Path(video_path)
        self.manifest_path = Path(manifest_path)
        
        # 加载视频
        self.cap = cv2.VideoCapture(str(self.video_path))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps if self.fps > 0 else 0
        
        # 加载事件
        self.events = self._load_events()
        
        # 初始化工具
        self.stitcher = ImageStitcherSkill()
        self.vision_analyzer = VisionAnalyzer(api_key=api_key) if api_key else None
        
        # 分析结果
        self.keyframes: List[VideoFrame] = []
        self.long_screenshots: Dict[str, StitchResult] = {}
        self.visual_analysis: Dict[str, Dict] = {}
        
    def _load_events(self) -> List[Dict]:
        """加载manifest中的关键事件 - 支持新的scroll事件类型"""
        events = []
        scroll_sequences = {}  # 用于跟踪scroll序列
        
        if not self.manifest_path.exists():
            return events
            
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    action = event.get('event_details', {}).get('action')
                    metadata = event.get('_metadata', {})
                    
                    # 支持新的scroll事件类型
                    if action in ['page-load', 'click', 'scroll', 'scroll-start', 'scroll-end']:
                        event_data = {
                            'type': action,
                            'timestamp': event.get('timestamp', 0),
                            'data': event,
                            'url': event.get('window_context', {}).get('url', ''),
                            # 提取scroll增强字段
                            'scrollSequenceId': metadata.get('scrollSequenceId'),
                            'direction': metadata.get('direction'),
                            'scrollStartX': metadata.get('scrollStartX'),
                            'scrollStartY': metadata.get('scrollStartY'),
                            'scrollDeltaX': metadata.get('scrollDeltaX'),
                            'scrollDeltaY': metadata.get('scrollDeltaY'),
                            'scrollDuration': metadata.get('scrollDuration'),
                            'triggerSource': metadata.get('triggerSource')
                        }
                        
                        # 对于scroll序列，进行分组
                        if action in ['scroll-start', 'scroll', 'scroll-end']:
                            seq_id = metadata.get('scrollSequenceId', 0)
                            if seq_id not in scroll_sequences:
                                scroll_sequences[seq_id] = []
                            scroll_sequences[seq_id].append(event_data)
                        
                        events.append(event_data)
                except:
                    continue
        
        # 存储scroll序列信息供后续使用
        self.scroll_sequences_map = scroll_sequences
                    
        return events
    
    # 注：移除了 _detect_scrolls_from_video 方法
    # 原因：视频检测 scroll 行为会质疑 training_manifest.jsonl 的准确性
    # 应该以 training_manifest.jsonl 为准，sentinel-browser 负责准确记录
    
    def _get_url_at_time(self, video_time: float) -> str:
        """获取指定视频时间点的URL"""
        target_timestamp = self.events[0]['timestamp'] + int(video_time * 1000)
        
        # 找到最接近的事件的URL
        closest_event = None
        min_diff = float('inf')
        
        for event in self.events:
            diff = abs(event['timestamp'] - target_timestamp)
            if diff < min_diff:
                min_diff = diff
                closest_event = event
        
        if closest_event:
            return closest_event.get('url', '')
        return ''
    
    # 注：移除了 _merge_video_detected_scrolls 方法
    # 原因：视频检测 scroll 行为会质疑 training_manifest.jsonl 的准确性
    
    def extract_and_analyze(self, output_dir: str, 
                           use_llm: bool = True,
                           create_long_screenshots: bool = True) -> Dict:
        """
        提取并分析视频
        
        Args:
            output_dir: 输出目录
            use_llm: 是否使用LLM视觉识别
            create_long_screenshots: 是否创建长截图
            
        Returns:
            分析结果汇总
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"[EnhancedVideoAnalyzer] 视频: {self.duration:.1f}s, {len(self.events)} 事件")
        
        # 注：移除了从视频检测滚动行为的功能
        # 原因：视频检测会质疑 training_manifest.jsonl 的准确性
        # 应该以 training_manifest.jsonl 为准
        
        # 1. 提取关键帧
        print("\n[1/4] 提取关键帧...")
        self.keyframes = self._extract_keyframes(str(output_path / "keyframes"))
        
        # 2. 按滚动序列分组关键帧（修复版）
        print("\n[2/4] 按滚动序列分组...")
        scroll_sequences = self._group_keyframes_by_scroll_sequences()
        self.page_sessions = scroll_sequences  # 保持兼容性

        # 3. 为每个滚动序列创建长截图
        if create_long_screenshots:
            print("\n[3/4] 创建滚动长截图...")
            self.long_screenshots = self._create_long_screenshots_for_sessions(
                scroll_sequences,
                str(output_path / "long_screenshots")
            )
        
        # 4. LLM视觉分析
        if use_llm and self.vision_analyzer:
            print("\n[4/4] LLM视觉分析...")
            self.visual_analysis = self._analyze_with_llm(
                str(output_path / "long_screenshots")
            )
        
        # 汇总结果
        return self._compile_results()
    
    def _extract_keyframes(self, keyframes_dir: str) -> List[VideoFrame]:
        """提取关键帧（智能选择）- 优化版，支持新的scroll事件类型"""
        keyframes_dir = Path(keyframes_dir)
        keyframes_dir.mkdir(parents=True, exist_ok=True)
        
        extracted = []
        prev_frame = None
        threshold = VIDEO_CONFIG.get("similarity_threshold", 0.95)
        scroll_change_threshold = 0.30  # 30%内容变化阈值
        
        # 按scroll序列分组处理
        scroll_sequence_frames = {}  # seq_id -> list of frames
        
        for i, event in enumerate(self.events):
            # 计算视频时间
            video_time = (event['timestamp'] - self.events[0]['timestamp']) / 1000
            frame_number = int(video_time * self.fps)
            
            if frame_number < 0 or frame_number >= self.total_frames:
                continue
            
            # 提取帧
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                continue
            
            event_type = event['type']
            
            # 智能选择：基于内容和事件类型
            should_extract = self._should_extract_frame(
                frame, prev_frame, event, threshold, i
            )
            
            if should_extract:
                # 保存帧
                frame_filename = f"frame_{i:04d}_{event_type}_{video_time:.3f}.jpg"
                frame_path = keyframes_dir / frame_filename
                cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                
                video_frame = VideoFrame(
                    timestamp=video_time,
                    frame_number=frame_number,
                    image_path=str(frame_path),
                    event_type=event_type,
                    event_data=event['data'],
                    similarity_score=0.0 if prev_frame is None else self._calculate_similarity(prev_frame, frame)
                )
                extracted.append(video_frame)
                prev_frame = frame
                print(f"  提取: {event_type} @ {video_time:.2f}s")
                
                # 对于scroll-start事件，开始跟踪该序列
                if event_type == 'scroll-start':
                    seq_id = event.get('scrollSequenceId', 0)
                    scroll_sequence_frames[seq_id] = {
                        'start_frame': frame,
                        'start_time': video_time,
                        'start_frame_num': frame_number,
                        'event_idx': i,
                        'extracted_frames': [video_frame]
                    }
                
                # 对于scroll-end事件，提取滚动过程中的帧
                elif event_type == 'scroll-end':
                    seq_id = event.get('scrollSequenceId', 0)
                    if seq_id in scroll_sequence_frames:
                        seq_data = scroll_sequence_frames[seq_id]
                        # 提取滚动过程中的帧（30%变化阈值）
                        mid_frames = self._extract_scroll_mid_frames(
                            seq_data, event, i, keyframes_dir, scroll_change_threshold
                        )
                        extracted.extend(mid_frames)
                        seq_data['extracted_frames'].extend(mid_frames)
                        
                        # 提取结束帧
                        end_frame_filename = f"frame_{i:04d}_scroll_end_{video_time:.3f}.jpg"
                        end_frame_path = keyframes_dir / end_frame_filename
                        cv2.imwrite(str(end_frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        
                        end_video_frame = VideoFrame(
                            timestamp=video_time,
                            frame_number=frame_number,
                            image_path=str(end_frame_path),
                            event_type='scroll_end',
                            event_data=event['data'],
                            similarity_score=0.0
                        )
                        extracted.append(end_video_frame)
                        seq_data['extracted_frames'].append(end_video_frame)
                        print(f"    滚动结束帧 @ {video_time:.2f}s")
                        
                        prev_frame = frame
        
        print(f"  共提取 {len(extracted)} 个关键帧")
        return extracted
    
    def _extract_scroll_mid_frames(self, seq_data: Dict, end_event: Dict, 
                                    event_idx: int, keyframes_dir: Path, 
                                    change_threshold: float) -> List[VideoFrame]:
        """
        提取滚动过程中30%内容变化的帧
        
        策略：
        1. 从scroll-start到scroll-end之间采样
        2. 每30%内容变化提取一帧
        3. 确保捕捉滚动过程中的关键变化
        """
        scroll_frames = []
        
        start_time = seq_data['start_time']
        end_time = (end_event['timestamp'] - self.events[0]['timestamp']) / 1000
        start_frame_num = seq_data['start_frame_num']
        start_frame = seq_data['start_frame']
        
        last_extracted_frame = start_frame
        last_video_time = start_time
        
        # 在滚动过程中密集采样（每50ms）
        check_interval = 0.05  # 50ms
        t = check_interval
        
        while start_time + t < end_time:
            video_time = start_time + t
            frame_number = int(video_time * self.fps)
            
            if frame_number >= self.total_frames:
                break
            
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                t += check_interval
                continue
            
            # 计算与上一提取帧的变化
            if last_extracted_frame is not None:
                similarity = self._calculate_similarity(last_extracted_frame, frame)
                change_ratio = 1.0 - similarity
                
                # 如果变化超过30%，提取该帧
                if change_ratio >= change_threshold:
                    frame_filename = f"frame_{event_idx:04d}_scroll_mid_{video_time:.3f}.jpg"
                    frame_path = keyframes_dir / frame_filename
                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    
                    video_frame = VideoFrame(
                        timestamp=video_time,
                        frame_number=frame_number,
                        image_path=str(frame_path),
                        event_type='scroll_mid',
                        event_data=end_event['data'],
                        similarity_score=similarity
                    )
                    scroll_frames.append(video_frame)
                    last_extracted_frame = frame
                    last_video_time = video_time
                    print(f"    滚动中: 变化 {change_ratio:.1%} @ {video_time:.2f}s")
            
            t += check_interval
        
        return scroll_frames
    
    def _should_extract_frame(self, frame: np.ndarray, prev_frame: Optional[np.ndarray],
                             event: Dict, threshold: float, event_idx: int) -> bool:
        """智能判断是否应该提取该帧 - 支持新的scroll事件类型"""
        event_type = event['type']
        
        # 1. 第一个帧总是提取
        if prev_frame is None:
            return True
        
        # 2. page-load 事件总是提取
        if event_type == 'page-load':
            return True
        
        # 3. click 事件总是提取
        if event_type == 'click':
            return True
        
        # 4. scroll-start 事件：总是提取（滚动开始状态）
        if event_type == 'scroll-start':
            return True
        
        # 5. scroll-end 事件：总是提取（滚动结束状态）
        if event_type == 'scroll-end':
            return True
        
        # 6. 旧的 scroll 事件（兼容旧数据）：总是提取第一帧
        if event_type == 'scroll':
            return True
        
        # 7. 基于视觉相似度
        similarity = self._calculate_similarity(prev_frame, frame)
        if similarity < threshold:
            return True
        
        return False
    
    def _calculate_similarity(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """计算帧相似度"""
        try:
            from skimage.metrics import structural_similarity as ssim
            
            gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
            
            if gray1.shape != gray2.shape:
                gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
            
            score, _ = ssim(gray1, gray2, full=True)
            return score
        except:
            return 0.0
    
    def _group_keyframes_by_scroll_sequences(self) -> List[Dict]:
        """
        按滚动序列分组关键帧 - 优化版
        
        新的逻辑：
        - 将 scroll、scroll_mid、scroll_end 事件归为同一个滚动序列
        - 一个"滚动序列"包含：
          * scroll 事件之前的帧（页面初始状态）
          * scroll 事件本身（滚动前）
          * scroll_mid 事件（滚动过程中，30%变化触发）
          * scroll_end 事件（滚动结束后，确保加载完成）
        - 只有包含 scroll 相关事件的序列才需要拼接
        """
        sequences = []
        current_sequence = None
        in_scroll_mode = False  # 是否处于滚动过程中
        
        for i, frame in enumerate(self.keyframes):
            event_type = frame.event_type
            event_data = frame.event_data
            url = event_data.get('window_context', {}).get('url', '')
            
            if event_type == 'page-load':
                # 如果有待处理的滚动序列，先保存
                if current_sequence is not None and in_scroll_mode:
                    sequences.append(current_sequence)
                    in_scroll_mode = False
                
                # 开始新序列
                parsed = urlparse(url)
                session_key = f"{parsed.netloc}{parsed.path}"[:80]
                
                current_sequence = {
                    'key': session_key,
                    'url': url,
                    'start_time': frame.timestamp,
                    'frames': [frame],
                    'event_types': [event_type],
                    'has_scroll': False,
                    'scroll_indices': [],  # 记录scroll事件在frames中的索引
                    'scroll_mid_indices': [],  # 记录scroll_mid事件
                    'scroll_end_indices': []   # 记录scroll_end事件
                }
                in_scroll_mode = False
                
            elif event_type == 'scroll':
                # 滚动开始
                if current_sequence is not None:
                    current_sequence['has_scroll'] = True
                    in_scroll_mode = True
                    current_sequence['frames'].append(frame)
                    current_sequence['event_types'].append(event_type)
                    current_sequence['scroll_indices'].append(len(current_sequence['frames']) - 1)
                    
            elif event_type == 'scroll_mid':
                # 滚动过程中
                if current_sequence is not None and in_scroll_mode:
                    current_sequence['frames'].append(frame)
                    current_sequence['event_types'].append(event_type)
                    current_sequence['scroll_mid_indices'].append(len(current_sequence['frames']) - 1)
                    
            elif event_type == 'scroll_end':
                # 滚动结束
                if current_sequence is not None and in_scroll_mode:
                    current_sequence['frames'].append(frame)
                    current_sequence['event_types'].append(event_type)
                    current_sequence['scroll_end_indices'].append(len(current_sequence['frames']) - 1)
                    
            elif event_type == 'click':
                # click 事件：如果之前有scroll，保存当前序列并开始新序列
                if current_sequence is not None:
                    if in_scroll_mode:
                        # 保存当前滚动序列
                        sequences.append(current_sequence)
                        
                        # 开始新序列（继承当前URL）
                        current_sequence = {
                            'key': current_sequence['key'],
                            'url': current_sequence['url'],
                            'start_time': frame.timestamp,
                            'frames': [frame],
                            'event_types': [event_type],
                            'has_scroll': False,
                            'scroll_indices': [],
                            'scroll_mid_indices': [],
                            'scroll_end_indices': []
                        }
                        in_scroll_mode = False
                    else:
                        current_sequence['frames'].append(frame)
                        current_sequence['event_types'].append(event_type)
        
        # 添加最后一个序列（如果包含scroll）
        if current_sequence is not None and current_sequence['has_scroll']:
            sequences.append(current_sequence)
        
        print(f"  识别 {len(sequences)} 个滚动序列:")
        for i, seq in enumerate(sequences):
            total_scroll_frames = len(seq['scroll_indices']) + len(seq['scroll_mid_indices']) + len(seq['scroll_end_indices'])
            print(f"    [{i+1}] {seq['key'][:50]}...")
            print(f"        总帧数: {len(seq['frames'])}, scroll相关帧: {total_scroll_frames}")
            print(f"          - scroll开始: {len(seq['scroll_indices'])}")
            print(f"          - scroll中间: {len(seq['scroll_mid_indices'])}")
            print(f"          - scroll结束: {len(seq['scroll_end_indices'])}")
        
        return sequences
    
    def _create_long_screenshots_for_sessions(self, sequences: List[Dict],
                                               output_dir: str) -> Dict[str, StitchResult]:
        """
        为每个滚动序列创建长截图

        正确的逻辑：
        - 每个序列包含 scroll 事件前后的帧
        - 将这些帧按时间顺序拼接，展示完整的滚动过程
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        long_screenshots = {}

        for i, seq in enumerate(sequences):
            frames = seq['frames']

            # 只处理有多个帧的序列
            if len(frames) < 2:
                print(f"  [{i+1}] {seq['key'][:40]}... 跳过（只有 {len(frames)} 帧）")
                continue

            # 检查是否有scroll事件
            if not seq.get('has_scroll', False):
                print(f"  [{i+1}] {seq['key'][:40]}... 跳过（无滚动事件）")
                continue

            # 生成文件名（包含scroll信息）
            safe_name = seq['key'].replace('/', '_').replace(':', '_')[:50]
            scroll_count = len(seq.get('scroll_indices', []))
            output_file = output_path / f"scroll_{i+1}_{safe_name}_{scroll_count}scrolls.jpg"

            print(f"  [{i+1}] 拼接滚动序列: {seq['key'][:40]}...")
            print(f"      帧数: {len(frames)}, scroll事件: {scroll_count}")

            # 获取图片路径（按时间顺序）
            image_paths = [f.image_path for f in frames]

            # 创建长截图
            result = self.stitcher.stitch_vertical(image_paths, str(output_file))

            long_screenshots[seq['key']] = result

            if result.success:
                print(f"      ✓ 成功: {output_file.name}")
                if hasattr(result, 'stitched_image') and result.stitched_image is not None:
                    print(f"      尺寸: {result.stitched_image.shape}")
            else:
                print(f"      ✗ 失败: {result.error_message}")

        return long_screenshots
    
    def _analyze_with_llm(self, long_screenshots_dir: str) -> Dict[str, Dict]:
        """使用LLM分析长截图"""
        if not self.vision_analyzer:
            return {}
        
        analyses = {}
        long_screenshots_path = Path(long_screenshots_dir)
        
        if not long_screenshots_path.exists():
            return {}
        
        # 分析每个长截图
        for screenshot_file in long_screenshots_path.glob("long_*.jpg"):
            print(f"  LLM分析: {screenshot_file.name}")
            
            try:
                result = self.vision_analyzer.analyze_long_image(str(screenshot_file))
                analyses[screenshot_file.stem] = result
                
                # 打印关键信息
                if 'parsed_data' in result:
                    data = result['parsed_data']
                    if isinstance(data, dict):
                        page_type = data.get('page_type', 'unknown')
                        print(f"    页面类型: {page_type}")
            except Exception as e:
                print(f"    分析失败: {e}")
                analyses[screenshot_file.stem] = {"error": str(e)}
        
        return analyses
    
    def _compile_results(self) -> Dict:
        """编译最终结果"""
        return {
            "total_events": len(self.events),
            "keyframes_extracted": len(self.keyframes),
            "long_screenshots_created": len([r for r in self.long_screenshots.values() if r.success]),
            "pages_analyzed": len(self.visual_analysis),
            "visual_elements": self._extract_visual_elements(),
            "page_understandings": self.visual_analysis
        }
    
    def _extract_visual_elements(self) -> List[Dict]:
        """提取视觉元素汇总"""
        elements = []
        
        for page_key, analysis in self.visual_analysis.items():
            if 'error' in analysis:
                continue
            
            parsed = analysis.get('parsed_data', {})
            if isinstance(parsed, dict):
                elements.append({
                    "page": page_key,
                    "page_type": parsed.get('page_type', 'unknown'),
                    "functions": parsed.get('functions', []),
                    "layout": parsed.get('layout', {})
                })
        
        return elements
    
    def release(self):
        """释放资源"""
        if self.cap:
            self.cap.release()

