"""
时间对齐器
对齐video、manifest、api等多源数据的时间戳
"""

import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TimeRange:
    """时间范围"""
    start: int  # 毫秒时间戳
    end: int
    source: str
    
    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass
class AlignedEvent:
    """对齐后的事件"""
    unified_timestamp: int  # 统一时间戳
    video_time_ms: Optional[int]  # 视频时间（毫秒）
    manifest_timestamp: Optional[int]  # manifest时间戳
    api_timestamp: Optional[int]  # API时间戳
    event_type: str
    data: Dict[str, Any]
    sources: List[str]  # 包含该事件的数据源


@dataclass
class AlignmentResult:
    """对齐结果"""
    aligned_events: List[AlignedEvent]
    time_mapping: Dict[str, Dict[int, int]]  # 各源到统一时间的映射
    anchor_points: List[Dict]  # 对齐锚点
    drift_analysis: Dict[str, Any]  # 时间漂移分析


class TemporalAligner:
    """时间对齐器"""
    
    def __init__(self, tolerance_ms: int = 500):
        """
        初始化对齐器
        
        Args:
            tolerance_ms: 事件匹配容差（毫秒）
        """
        self.tolerance = tolerance_ms
        self.anchor_events: List[Dict] = []
        
    def align(self,
              video_events: Optional[List[Dict]] = None,
              manifest_events: Optional[List[Dict]] = None,
              api_events: Optional[List[Dict]] = None,
              dom_events: Optional[List[Dict]] = None) -> AlignmentResult:
        """
        执行时间对齐
        
        Args:
            video_events: 视频事件列表
            manifest_events: manifest事件列表
            api_events: API事件列表
            dom_events: DOM事件列表
            
        Returns:
            对齐结果
        """
        print("  [时间对齐] 收集时间范围...")
        time_ranges = self._collect_time_ranges(
            video_events, manifest_events, api_events, dom_events
        )
        
        print("  [时间对齐] 识别锚点事件...")
        self.anchor_events = self._identify_anchor_events(
            video_events, manifest_events, api_events
        )
        print(f"    发现 {len(self.anchor_events)} 个锚点")
        
        print("  [时间对齐] 计算时间映射...")
        time_mapping = self._calculate_time_mapping()
        
        print("  [时间对齐] 对齐所有事件...")
        aligned_events = self._align_all_events(
            video_events, manifest_events, api_events, dom_events, time_mapping
        )
        print(f"    对齐 {len(aligned_events)} 个事件")
        
        print("  [时间对齐] 分析时间漂移...")
        drift_analysis = self._analyze_time_drift(aligned_events)
        
        return AlignmentResult(
            aligned_events=aligned_events,
            time_mapping=time_mapping,
            anchor_points=self.anchor_events,
            drift_analysis=drift_analysis
        )
    
    def _collect_time_ranges(self, *event_lists) -> List[TimeRange]:
        """收集各源的时间范围"""
        ranges = []
        sources = ['video', 'manifest', 'api', 'dom']
        
        for events, source in zip(event_lists, sources):
            if not events:
                continue
            
            timestamps = []
            for e in events:
                ts = self._extract_timestamp(e, source)
                if ts:
                    timestamps.append(ts)
            
            if timestamps:
                ranges.append(TimeRange(
                    start=min(timestamps),
                    end=max(timestamps),
                    source=source
                ))
        
        return ranges
    
    def _extract_timestamp(self, event: Dict, source: str) -> Optional[int]:
        """从事件中提取时间戳（统一转换为毫秒）"""
        ts = event.get('timestamp', 0)
        
        if not ts:
            return None
        
        # 统一转换为毫秒时间戳
        if source == 'video':
            # 视频时间可能是秒（浮点数），转换为毫秒
            if isinstance(ts, float) and ts < 1000000000:
                return int(ts * 1000)
            return int(ts)
        elif source == 'manifest':
            # manifest时间通常是毫秒级Unix时间戳
            return int(ts)
        elif source == 'api':
            # API时间可能是秒或毫秒
            if isinstance(ts, (int, float)):
                if ts < 1000000000:
                    return int(ts * 1000)
                return int(ts)
        elif source == 'dom':
            return int(ts)
        
        return int(ts) if ts else None
    
    def _identify_anchor_events(self,
                                video_events: Optional[List[Dict]],
                                manifest_events: Optional[List[Dict]],
                                api_events: Optional[List[Dict]]) -> List[Dict]:
        """识别锚点事件（用于对齐的关键事件）"""
        anchors = []
        
        # 使用page-load事件作为锚点
        if manifest_events:
            for event in manifest_events:
                if event.get('event_details', {}).get('action') == 'page-load':
                    anchor = {
                        'type': 'page_load',
                        'manifest_timestamp': event.get('timestamp'),
                        'video_time': self._parse_video_time(event.get('video_time', '')),
                        'url': event.get('window_context', {}).get('url', ''),
                        'confidence': 1.0
                    }
                    anchors.append(anchor)
        
        # 使用API调用作为锚点
        if api_events:
            for event in api_events[:5]:  # 使用前5个API调用
                anchor = {
                    'type': 'api_call',
                    'api_timestamp': event.get('timestamp'),
                    'url': event.get('url', '')[:50],
                    'confidence': 0.8
                }
                anchors.append(anchor)
        
        return anchors
    
    def _parse_video_time(self, video_time: str) -> Optional[int]:
        """解析视频时间字符串为毫秒"""
        if not video_time:
            return None
        
        try:
            # 格式: "00:00:01.806"
            parts = video_time.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int((hours * 3600 + minutes * 60 + seconds) * 1000)
        except:
            pass
        
        return None
    
    def _calculate_time_mapping(self) -> Dict[str, Dict[int, int]]:
        """计算各源到统一时间的映射"""
        mapping = {
            'video': {},
            'manifest': {},
            'api': {},
            'dom': {}
        }
        
        # 使用manifest时间作为基准
        if self.anchor_events:
            base_time = self.anchor_events[0].get('manifest_timestamp', 0)
            
            for anchor in self.anchor_events:
                manifest_ts = anchor.get('manifest_timestamp')
                video_ts = anchor.get('video_time')
                api_ts = anchor.get('api_timestamp')
                
                if manifest_ts:
                    unified_time = manifest_ts - base_time
                    mapping['manifest'][manifest_ts] = unified_time
                    
                    if video_ts:
                        mapping['video'][video_ts] = unified_time
                    if api_ts:
                        mapping['api'][api_ts] = unified_time
        
        return mapping
    
    def _align_all_events(self,
                         video_events: Optional[List[Dict]],
                         manifest_events: Optional[List[Dict]],
                         api_events: Optional[List[Dict]],
                         dom_events: Optional[List[Dict]],
                         time_mapping: Dict) -> List[AlignedEvent]:
        """对齐所有事件"""
        aligned = []
        
        # 收集所有事件
        all_events = []
        
        if video_events:
            for e in video_events:
                all_events.append({
                    'source': 'video',
                    'timestamp': e.get('timestamp', 0),
                    'type': e.get('event_type', 'unknown'),
                    'data': e
                })
        
        if manifest_events:
            for e in manifest_events:
                all_events.append({
                    'source': 'manifest',
                    'timestamp': e.get('timestamp', 0),
                    'type': e.get('event_details', {}).get('action', 'unknown'),
                    'data': e
                })
        
        if api_events:
            for e in api_events:
                all_events.append({
                    'source': 'api',
                    'timestamp': e.get('timestamp', 0),
                    'type': 'api_call',
                    'data': e
                })
        
        if dom_events:
            for e in dom_events:
                all_events.append({
                    'source': 'dom',
                    'timestamp': e.get('timestamp', 0),
                    'type': 'dom_change',
                    'data': e
                })
        
        # 按时间戳排序
        all_events.sort(key=lambda x: x['timestamp'])
        
        # 合并相近的事件
        merged = self._merge_nearby_events(all_events)
        
        # 转换为AlignedEvent
        for m in merged:
            unified_ts = self._calculate_unified_timestamp(m, time_mapping)
            
            aligned_event = AlignedEvent(
                unified_timestamp=unified_ts,
                video_time_ms=m.get('video_timestamp'),
                manifest_timestamp=m.get('manifest_timestamp'),
                api_timestamp=m.get('api_timestamp'),
                event_type=m.get('type', 'unknown'),
                data=m.get('merged_data', {}),
                sources=m.get('sources', [])
            )
            aligned.append(aligned_event)
        
        return aligned
    
    def _merge_nearby_events(self, events: List[Dict]) -> List[Dict]:
        """合并时间相近的事件"""
        if not events:
            return []
        
        merged = []
        current_group = [events[0]]
        
        for event in events[1:]:
            # 检查是否与当前组的时间相近
            last_event = current_group[-1]
            time_diff = abs(event['timestamp'] - last_event['timestamp'])
            
            if time_diff <= self.tolerance:
                current_group.append(event)
            else:
                # 合并当前组
                merged.append(self._merge_event_group(current_group))
                current_group = [event]
        
        # 合并最后一组
        if current_group:
            merged.append(self._merge_event_group(current_group))
        
        return merged
    
    def _merge_event_group(self, group: List[Dict]) -> Dict:
        """合并事件组"""
        timestamps = {e['source']: e['timestamp'] for e in group}
        types = [e['type'] for e in group]
        sources = [e['source'] for e in group]
        
        # 合并数据
        merged_data = {}
        for e in group:
            merged_data[e['source']] = e['data']
        
        return {
            'video_timestamp': timestamps.get('video'),
            'manifest_timestamp': timestamps.get('manifest'),
            'api_timestamp': timestamps.get('api'),
            'dom_timestamp': timestamps.get('dom'),
            'type': types[0] if len(set(types)) == 1 else 'composite',
            'sources': sources,
            'merged_data': merged_data,
            'timestamp': group[0]['timestamp']  # 使用第一个事件的时间
        }
    
    def _calculate_unified_timestamp(self, 
                                     merged_event: Dict, 
                                     time_mapping: Dict) -> int:
        """计算统一时间戳"""
        # 优先使用manifest时间
        if merged_event.get('manifest_timestamp'):
            manifest_ts = merged_event['manifest_timestamp']
            if manifest_ts in time_mapping.get('manifest', {}):
                return time_mapping['manifest'][manifest_ts]
            return manifest_ts
        
        # 其次使用video时间
        if merged_event.get('video_timestamp'):
            video_ts = merged_event['video_timestamp']
            if video_ts in time_mapping.get('video', {}):
                return time_mapping['video'][video_ts]
            return video_ts
        
        # 最后使用原始时间戳
        return merged_event.get('timestamp', 0)
    
    def _analyze_time_drift(self, aligned_events: List[AlignedEvent]) -> Dict:
        """分析时间漂移"""
        if not aligned_events:
            return {}
        
        # 计算各源之间的时间差
        drifts = []
        
        for event in aligned_events:
            timestamps = []
            if event.video_time_ms:
                timestamps.append(('video', event.video_time_ms))
            if event.manifest_timestamp:
                timestamps.append(('manifest', event.manifest_timestamp))
            if event.api_timestamp:
                timestamps.append(('api', event.api_timestamp))
            
            if len(timestamps) >= 2:
                for i in range(len(timestamps)):
                    for j in range(i + 1, len(timestamps)):
                        drift = abs(timestamps[i][1] - timestamps[j][1])
                        drifts.append({
                            'source_pair': f"{timestamps[i][0]}-{timestamps[j][0]}",
                            'drift_ms': drift
                        })
        
        if not drifts:
            return {'status': 'insufficient_data'}
        
        # 统计漂移
        drift_values = [d['drift_ms'] for d in drifts]
        
        return {
            'status': 'analyzed',
            'total_measurements': len(drifts),
            'avg_drift_ms': sum(drift_values) / len(drift_values),
            'max_drift_ms': max(drift_values),
            'min_drift_ms': min(drift_values),
            'drift_by_pair': self._aggregate_by_pair(drifts)
        }
    
    def _aggregate_by_pair(self, drifts: List[Dict]) -> Dict:
        """按源对聚合漂移"""
        by_pair = {}
        
        for d in drifts:
            pair = d['source_pair']
            if pair not in by_pair:
                by_pair[pair] = []
            by_pair[pair].append(d['drift_ms'])
        
        # 计算统计值
        result = {}
        for pair, values in by_pair.items():
            result[pair] = {
                'count': len(values),
                'avg': sum(values) / len(values),
                'max': max(values),
                'min': min(values)
            }
        
        return result


if __name__ == "__main__":
    # 测试
    aligner = TemporalAligner(tolerance_ms=500)
    
    # 测试数据
    video_events = [
        {'timestamp': 1000, 'event_type': 'page_load', 'data': {}},
        {'timestamp': 3000, 'event_type': 'click', 'data': {}}
    ]
    
    manifest_events = [
        {'timestamp': 1778034753537, 'event_details': {'action': 'page-load'}, 'video_time': '00:00:01.000'},
        {'timestamp': 1778034755537, 'event_details': {'action': 'click'}, 'video_time': '00:00:03.000'}
    ]
    
    api_events = [
        {'timestamp': 1778034753600, 'url': '/api/data'},
        {'timestamp': 1778034755600, 'url': '/api/click'}
    ]
    
    result = aligner.align(video_events, manifest_events, api_events)
    
    print("\n=== 时间对齐结果 ===")
    print(f"对齐事件数: {len(result.aligned_events)}")
    print(f"锚点数: {len(result.anchor_points)}")
    print(f"\n漂移分析:")
    print(json.dumps(result.drift_analysis, indent=2))
