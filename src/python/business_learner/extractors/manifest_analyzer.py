"""
Training Manifest 深度分析器
提取用户意图序列和完整操作流程
"""

import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class UserIntent:
    """用户意图"""
    timestamp: int
    video_time: str
    intent_type: str  # navigate, interact, browse_content, search, submit
    description: str
    target_element: str
    page_url: str
    confidence: float = 1.0


@dataclass
class OperationStep:
    """操作步骤"""
    step_number: int
    timestamp: int
    video_time: str
    action: str  # page-load, click, scroll, input, submit
    target: str
    semantic_label: str
    page_url: str
    page_title: str
    user_intent: str
    api_calls: List[Dict] = field(default_factory=list)
    dom_changes: List[Dict] = field(default_factory=list)
    duration_ms: int = 0  # 该步骤持续时间


@dataclass
class BusinessFlow:
    """业务流程"""
    flow_id: str
    name: str
    description: str
    start_url: str
    end_url: str
    steps: List[OperationStep]
    user_intents: List[UserIntent]
    total_duration_ms: int
    page_transitions: List[Dict]  # 页面跳转序列


@dataclass
class ManifestAnalysisResult:
    """Manifest分析结果"""
    total_events: int
    user_intents: List[UserIntent]
    business_flows: List[BusinessFlow]
    page_visits: List[Dict]  # 页面访问序列
    interaction_patterns: Dict[str, Any]  # 交互模式统计
    error_events: List[Dict]  # 错误事件


class ManifestAnalyzer:
    """Manifest深度分析器"""
    
    # 用户意图映射
    INTENT_MAPPING = {
        "navigate": ["page-load"],
        "interact": ["click"],
        "browse_content": ["scroll"],
        "input_data": ["input", "change"],
        "submit_form": ["submit"],
        "hover": ["mouseover", "mouseenter"]
    }
    
    def __init__(self, manifest_path: str):
        """
        初始化分析器
        
        Args:
            manifest_path: manifest文件路径
        """
        self.manifest_path = Path(manifest_path)
        self.events: List[Dict] = []
        
    def load_events(self) -> List[Dict]:
        """加载所有事件"""
        events = []
        if not self.manifest_path.exists():
            return events
            
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except:
                    continue
        
        self.events = events
        return events
    
    def analyze(self) -> ManifestAnalysisResult:
        """
        执行完整分析
        
        Returns:
            分析结果
        """
        print("  [Manifest分析] 加载事件...")
        self.load_events()
        print(f"    共 {len(self.events)} 个事件")
        
        print("  [Manifest分析] 提取用户意图...")
        user_intents = self._extract_user_intents()
        print(f"    识别 {len(user_intents)} 个用户意图")
        
        print("  [Manifest分析] 构建业务流程...")
        business_flows = self._build_business_flows()
        print(f"    构建 {len(business_flows)} 个业务流程")
        
        print("  [Manifest分析] 分析页面访问...")
        page_visits = self._analyze_page_visits()
        print(f"    访问 {len(page_visits)} 个页面")
        
        print("  [Manifest分析] 统计交互模式...")
        interaction_patterns = self._analyze_interaction_patterns()
        
        print("  [Manifest分析] 识别错误事件...")
        error_events = self._extract_error_events()
        print(f"    发现 {len(error_events)} 个错误事件")
        
        return ManifestAnalysisResult(
            total_events=len(self.events),
            user_intents=user_intents,
            business_flows=business_flows,
            page_visits=page_visits,
            interaction_patterns=interaction_patterns,
            error_events=error_events
        )
    
    def _extract_user_intents(self) -> List[UserIntent]:
        """提取用户意图序列"""
        intents = []
        
        for event in self.events:
            metadata = event.get("_metadata", {})
            event_details = event.get("event_details", {})
            window_context = event.get("window_context", {})
            
            action = event_details.get("action", "")
            intent_list = metadata.get("user_intents", [])
            
            # 确定意图类型
            intent_type = self._determine_intent_type(action, intent_list)
            
            # 构建意图描述
            description = self._build_intent_description(event)
            
            intent = UserIntent(
                timestamp=event.get("timestamp", 0),
                video_time=event.get("video_time", ""),
                intent_type=intent_type,
                description=description,
                target_element=event_details.get("semantic_label", ""),
                page_url=window_context.get("url", ""),
                confidence=1.0 if intent_list else 0.5
            )
            intents.append(intent)
        
        return intents
    
    def _determine_intent_type(self, action: str, intent_list: List[str]) -> str:
        """确定意图类型"""
        # 优先使用manifest中的意图
        if intent_list:
            return intent_list[0]
        
        # 根据action推断
        for intent_type, actions in self.INTENT_MAPPING.items():
            if action in actions:
                return intent_type
        
        return "unknown"
    
    def _build_intent_description(self, event: Dict) -> str:
        """构建意图描述"""
        event_details = event.get("event_details", {})
        action = event_details.get("action", "")
        semantic = event_details.get("semantic_label", "")
        
        if action == "page-load":
            return f"导航到页面"
        elif action == "click":
            return f"点击: {semantic}"
        elif action == "scroll":
            return f"浏览页面内容"
        else:
            return f"{action}: {semantic}"
    
    def _build_business_flows(self) -> List[BusinessFlow]:
        """构建业务流程"""
        flows = []
        
        # 按页面加载分割流程
        flow_segments = self._segment_by_page_load()
        
        for i, segment in enumerate(flow_segments):
            if len(segment) < 2:
                continue
            
            # 构建步骤
            steps = self._build_operation_steps(segment)
            
            # 提取意图
            intents = [
                UserIntent(
                    timestamp=e.get("timestamp", 0),
                    video_time=e.get("video_time", ""),
                    intent_type=self._determine_intent_type(
                        e.get("event_details", {}).get("action", ""),
                        e.get("_metadata", {}).get("user_intents", [])
                    ),
                    description=self._build_intent_description(e),
                    target_element=e.get("event_details", {}).get("semantic_label", ""),
                    page_url=e.get("window_context", {}).get("url", ""),
                    confidence=1.0
                )
                for e in segment
            ]
            
            # 计算持续时间
            start_time = segment[0].get("timestamp", 0)
            end_time = segment[-1].get("timestamp", 0)
            total_duration = end_time - start_time
            
            # 页面跳转
            transitions = self._extract_page_transitions(segment)
            
            flow = BusinessFlow(
                flow_id=f"flow_{i+1}",
                name=self._generate_flow_name(segment),
                description=self._generate_flow_description(segment),
                start_url=segment[0].get("window_context", {}).get("url", ""),
                end_url=segment[-1].get("window_context", {}).get("url", ""),
                steps=steps,
                user_intents=intents,
                total_duration_ms=total_duration,
                page_transitions=transitions
            )
            flows.append(flow)
        
        return flows
    
    def _segment_by_page_load(self) -> List[List[Dict]]:
        """按页面加载分割事件序列"""
        segments = []
        current_segment = []
        
        for event in self.events:
            action = event.get("event_details", {}).get("action", "")
            
            if action == "page-load":
                if current_segment:
                    segments.append(current_segment)
                current_segment = [event]
            else:
                current_segment.append(event)
        
        if current_segment:
            segments.append(current_segment)
        
        return segments
    
    def _build_operation_steps(self, segment: List[Dict]) -> List[OperationStep]:
        """构建操作步骤"""
        steps = []
        
        for i, event in enumerate(segment):
            event_details = event.get("event_details", {})
            window_context = event.get("window_context", {})
            network_corr = event.get("network_correlation", {})
            page_state = event.get("page_state", {})
            
            # 计算持续时间
            duration = 0
            if i < len(segment) - 1:
                next_time = segment[i + 1].get("timestamp", 0)
                curr_time = event.get("timestamp", 0)
                duration = next_time - curr_time
            
            step = OperationStep(
                step_number=i + 1,
                timestamp=event.get("timestamp", 0),
                video_time=event.get("video_time", ""),
                action=event_details.get("action", ""),
                target=event_details.get("dom_path", ""),
                semantic_label=event_details.get("semantic_label", ""),
                page_url=window_context.get("url", ""),
                page_title=event.get("_metadata", {}).get("title", ""),
                user_intent=self._determine_intent_type(
                    event_details.get("action", ""),
                    event.get("_metadata", {}).get("user_intents", [])
                ),
                api_calls=network_corr.get("api_requests", []),
                dom_changes=page_state.get("mutations", []),
                duration_ms=duration
            )
            steps.append(step)
        
        return steps
    
    def _extract_page_transitions(self, segment: List[Dict]) -> List[Dict]:
        """提取页面跳转序列"""
        transitions = []
        prev_url = None
        
        for event in segment:
            url = event.get("window_context", {}).get("url", "")
            if url != prev_url and prev_url:
                transitions.append({
                    "from": prev_url,
                    "to": url,
                    "timestamp": event.get("timestamp", 0),
                    "trigger": event.get("event_details", {}).get("action", "")
                })
            prev_url = url
        
        return transitions
    
    def _generate_flow_name(self, segment: List[Dict]) -> str:
        """生成流程名称"""
        if not segment:
            return "未知流程"
        
        start_url = segment[0].get("window_context", {}).get("url", "")
        end_url = segment[-1].get("window_context", {}).get("url", "")
        
        # 提取路径
        start_path = start_url.split("/")[-1] if "/" in start_url else start_url
        end_path = end_url.split("/")[-1] if "/" in end_url else end_url
        
        if start_path == end_path:
            return f"浏览 {start_path}"
        else:
            return f"从 {start_path} 到 {end_path}"
    
    def _generate_flow_description(self, segment: List[Dict]) -> str:
        """生成流程描述"""
        if not segment:
            return ""
        
        actions = [e.get("event_details", {}).get("action", "") for e in segment]
        action_counts = {}
        for a in actions:
            action_counts[a] = action_counts.get(a, 0) + 1
        
        desc_parts = []
        for action, count in action_counts.items():
            if action == "page-load":
                desc_parts.append(f"访问 {count} 个页面")
            elif action == "click":
                desc_parts.append(f"点击 {count} 次")
            elif action == "scroll":
                desc_parts.append(f"滚动 {count} 次")
        
        return "，".join(desc_parts)
    
    def _analyze_page_visits(self) -> List[Dict]:
        """分析页面访问"""
        visits = []
        current_visit = None
        
        for event in self.events:
            url = event.get("window_context", {}).get("url", "")
            action = event.get("event_details", {}).get("action", "")
            timestamp = event.get("timestamp", 0)
            
            if action == "page-load":
                if current_visit:
                    current_visit["end_time"] = timestamp
                    current_visit["duration"] = timestamp - current_visit["start_time"]
                    visits.append(current_visit)
                
                current_visit = {
                    "url": url,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "duration": 0,
                    "events": 1,
                    "actions": [action]
                }
            elif current_visit:
                current_visit["events"] += 1
                current_visit["actions"].append(action)
                current_visit["end_time"] = timestamp
                current_visit["duration"] = timestamp - current_visit["start_time"]
        
        if current_visit:
            visits.append(current_visit)
        
        return visits
    
    def _analyze_interaction_patterns(self) -> Dict[str, Any]:
        """分析交互模式"""
        patterns = {
            "total_clicks": 0,
            "total_scrolls": 0,
            "total_page_loads": 0,
            "unique_pages": set(),
            "action_sequence": [],
            "most_clicked_elements": {},
            "scroll_depths": []
        }
        
        for event in self.events:
            action = event.get("event_details", {}).get("action", "")
            url = event.get("window_context", {}).get("url", "")
            semantic = event.get("event_details", {}).get("semantic_label", "")
            
            patterns["action_sequence"].append(action)
            patterns["unique_pages"].add(url)
            
            if action == "click":
                patterns["total_clicks"] += 1
                patterns["most_clicked_elements"][semantic] = \
                    patterns["most_clicked_elements"].get(semantic, 0) + 1
            elif action == "scroll":
                patterns["total_scrolls"] += 1
            elif action == "page-load":
                patterns["total_page_loads"] += 1
        
        # 转换set为list以便JSON序列化
        patterns["unique_pages"] = list(patterns["unique_pages"])
        
        # 排序最常点击的元素
        patterns["most_clicked_elements"] = dict(
            sorted(patterns["most_clicked_elements"].items(), 
                   key=lambda x: x[1], reverse=True)[:10]
        )
        
        return patterns
    
    def _extract_error_events(self) -> List[Dict]:
        """提取错误事件"""
        errors = []
        
        for event in self.events:
            page_state = event.get("page_state", {})
            
            if page_state.get("has_errors", False):
                errors.append({
                    "timestamp": event.get("timestamp", 0),
                    "video_time": event.get("video_time", ""),
                    "url": event.get("window_context", {}).get("url", ""),
                    "action": event.get("event_details", {}).get("action", ""),
                    "error_details": page_state.get("errors", [])
                })
        
        return errors

