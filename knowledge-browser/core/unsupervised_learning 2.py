#!/usr/bin/env python3
"""
无监督学习模块 - 自动发现页面模式和用户行为模式
"""
import json
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from datetime import datetime
import hashlib


class PagePattern:
    """页面模式"""
    def __init__(self, pattern_id: str, features: Dict[str, Any]):
        self.pattern_id = pattern_id
        self.features = features
        self.occurrences = 0
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.examples: List[str] = []
        
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "features": self.features,
            "occurrences": self.occurrences,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "examples": self.examples[:5]  # 只保存前5个示例
        }


class BehaviorPattern:
    """用户行为模式"""
    def __init__(self, pattern_id: str, action_sequence: List[str], context: Dict):
        self.pattern_id = pattern_id
        self.action_sequence = action_sequence
        self.context = context
        self.frequency = 0
        self.success_rate = 1.0
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "action_sequence": self.action_sequence,
            "context": self.context,
            "frequency": self.frequency,
            "success_rate": self.success_rate,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat()
        }


class UnsupervisedLearning:
    """无监督学习引擎"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        
        # 页面模式库
        self.page_patterns: Dict[str, PagePattern] = {}
        
        # 行为模式库
        self.behavior_patterns: Dict[str, BehaviorPattern] = {}
        
        # 元素类型统计
        self.element_stats: Dict[str, int] = defaultdict(int)
        
        # 操作序列缓存
        self.action_buffer: List[Dict] = []
        self.buffer_size = 50
        
        # 相似度阈值
        self.similarity_threshold = 0.8
        
    def analyze_page_structure(self, url: str, html: str, styles: List[Dict]) -> Dict:
        """分析页面结构，提取模式"""
        # 提取页面特征
        features = self._extract_page_features(html, styles)
        
        # 生成页面指纹
        fingerprint = self._generate_page_fingerprint(features)
        
        # 查找或创建模式
        if fingerprint in self.page_patterns:
            pattern = self.page_patterns[fingerprint]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
        else:
            pattern = PagePattern(fingerprint, features)
            pattern.occurrences = 1
            pattern.examples.append(url)
            self.page_patterns[fingerprint] = pattern
            
        return {
            "pattern_id": fingerprint,
            "is_new_pattern": pattern.occurrences == 1,
            "occurrences": pattern.occurrences,
            "features": features
        }
        
    def _extract_page_features(self, html: str, styles: List[Dict]) -> Dict:
        """提取页面特征"""
        features = {
            "element_types": defaultdict(int),
            "common_classes": defaultdict(int),
            "layout_patterns": [],
            "interactive_elements": 0,
            "form_elements": 0,
            "link_count": 0,
            "image_count": 0
        }
        
        for style in styles:
            tag = style.get('tag', '')
            class_name = style.get('className', '')
            
            # 统计元素类型
            features["element_types"][tag] += 1
            
            # 统计常用类名
            if class_name:
                for cls in class_name.split():
                    features["common_classes"][cls] += 1
                    
            # 统计交互元素
            if tag in ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']:
                features["interactive_elements"] += 1
                
            # 统计表单元素
            if tag in ['INPUT', 'SELECT', 'TEXTAREA', 'FORM']:
                features["form_elements"] += 1
                
            # 统计链接
            if tag == 'A':
                features["link_count"] += 1
                
            # 统计图片
            if tag == 'IMG':
                features["image_count"] += 1
                
        # 提取布局模式（基于元素位置）
        features["layout_patterns"] = self._extract_layout_patterns(styles)
        
        return features
        
    def _extract_layout_patterns(self, styles: List[Dict]) -> List[str]:
        """提取布局模式"""
        patterns = []
        
        # 按Y坐标分组，找出水平布局
        y_groups = defaultdict(list)
        for style in styles:
            rect = style.get('rect', {})
            y = int(rect.get('y', 0) / 50) * 50  # 按50px分组
            y_groups[y].append(style)
            
        # 找出常见的行模式
        for y, elements in sorted(y_groups.items()):
            if len(elements) >= 3:  # 一行至少3个元素
                tags = [e.get('tag', 'DIV') for e in elements[:5]]
                pattern = f"row_{'_'.join(tags)}"
                patterns.append(pattern)
                
        return patterns[:10]  # 只保留前10个模式
        
    def _generate_page_fingerprint(self, features: Dict) -> str:
        """生成页面指纹"""
        # 基于元素类型分布生成指纹
        element_dist = sorted(features["element_types"].items(), key=lambda x: x[1], reverse=True)[:10]
        fingerprint_str = json.dumps(element_dist, sort_keys=True)
        return hashlib.md5(fingerprint_str.encode()).hexdigest()[:16]
        
    def learn_from_actions(self, actions: List[Dict], navigation_history: List[Dict]) -> Dict:
        """从操作序列中学习行为模式"""
        if len(actions) < 2:
            return {"patterns_found": 0}
            
        # 添加到缓冲区
        self.action_buffer.extend(actions)
        if len(self.action_buffer) > self.buffer_size:
            self.action_buffer = self.action_buffer[-self.buffer_size:]
            
        # 发现行为模式
        patterns_found = []
        
        # 1. 发现常见的操作序列
        sequence_patterns = self._discover_sequence_patterns(actions)
        patterns_found.extend(sequence_patterns)
        
        # 2. 发现页面转换模式
        transition_patterns = self._discover_transition_patterns(actions, navigation_history)
        patterns_found.extend(transition_patterns)
        
        # 3. 发现高频操作元素
        element_patterns = self._discover_element_patterns(actions)
        patterns_found.extend(element_patterns)
        
        # 更新行为模式库
        for pattern_data in patterns_found:
            pattern_id = pattern_data["pattern_id"]
            if pattern_id in self.behavior_patterns:
                self.behavior_patterns[pattern_id].frequency += 1
                self.behavior_patterns[pattern_id].last_seen = datetime.now()
            else:
                pattern = BehaviorPattern(
                    pattern_id,
                    pattern_data["action_sequence"],
                    pattern_data["context"]
                )
                pattern.frequency = 1
                self.behavior_patterns[pattern_id] = pattern
                
        return {
            "patterns_found": len(patterns_found),
            "total_patterns": len(self.behavior_patterns),
            "new_patterns": [p for p in patterns_found if p.get("is_new", False)]
        }
        
    def _discover_sequence_patterns(self, actions: List[Dict]) -> List[Dict]:
        """发现操作序列模式"""
        patterns = []
        
        # 提取操作类型序列
        action_types = [a.get('type', 'unknown') for a in actions]
        
        # 寻找重复的模式（长度2-5）
        for length in range(2, min(6, len(action_types))):
            for i in range(len(action_types) - length + 1):
                sequence = action_types[i:i+length]
                sequence_str = ' -> '.join(sequence)
                
                # 检查这个序列是否在其他地方出现
                count = self._count_sequence_occurrences(action_types, sequence)
                
                if count >= 2:  # 至少出现2次
                    pattern_id = hashlib.md5(sequence_str.encode()).hexdigest()[:12]
                    patterns.append({
                        "pattern_id": f"seq_{pattern_id}",
                        "type": "sequence",
                        "action_sequence": sequence,
                        "frequency": count,
                        "context": {"sequence_str": sequence_str},
                        "is_new": pattern_id not in [p.pattern_id.replace('seq_', '') for p in self.behavior_patterns.values()]
                    })
                    
        return patterns
        
    def _count_sequence_occurrences(self, action_types: List[str], sequence: List[str]) -> int:
        """计算序列出现次数"""
        count = 0
        for i in range(len(action_types) - len(sequence) + 1):
            if action_types[i:i+len(sequence)] == sequence:
                count += 1
        return count
        
    def _discover_transition_patterns(self, actions: List[Dict], navigation_history: List[Dict]) -> List[Dict]:
        """发现页面转换模式"""
        patterns = []
        
        # 分析操作前后的页面变化
        for i, action in enumerate(actions):
            if action.get('type') == 'click':
                # 查找点击前后的URL变化
                before_url = self._get_url_at_time(action.get('timestamp'), navigation_history, before=True)
                after_url = self._get_url_at_time(action.get('timestamp'), navigation_history, before=False)
                
                if before_url and after_url and before_url != after_url:
                    transition = f"{before_url} -> {after_url}"
                    pattern_id = hashlib.md5(transition.encode()).hexdigest()[:12]
                    
                    patterns.append({
                        "pattern_id": f"trans_{pattern_id}",
                        "type": "transition",
                        "action_sequence": ["click"],
                        "context": {
                            "from_url": before_url,
                            "to_url": after_url,
                            "trigger": action.get('target', {}).get('text', 'unknown')
                        },
                        "is_new": pattern_id not in [p.pattern_id.replace('trans_', '') for p in self.behavior_patterns.values()]
                    })
                    
        return patterns
        
    def _get_url_at_time(self, timestamp: str, navigation_history: List[Dict], before: bool = True) -> Optional[str]:
        """获取特定时间点的URL"""
        if not timestamp:
            return None
            
        try:
            target_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return None
            
        closest_url = None
        for nav in navigation_history:
            nav_time = datetime.fromisoformat(nav.get('timestamp', '').replace('Z', '+00:00'))
            if before and nav_time <= target_time:
                closest_url = nav.get('url')
            elif not before and nav_time >= target_time:
                return nav.get('url')
                
        return closest_url
        
    def _discover_element_patterns(self, actions: List[Dict]) -> List[Dict]:
        """发现高频操作元素模式"""
        patterns = []
        
        # 统计元素点击频率
        element_clicks = defaultdict(int)
        for action in actions:
            if action.get('type') in ['click', 'dblclick']:
                target = action.get('target', {})
                element_key = f"{target.get('tagName', 'UNKNOWN')}_{target.get('id', '')}_{target.get('className', '')[:20]}"
                element_clicks[element_key] += 1
                
        # 找出高频元素
        for element_key, count in element_clicks.items():
            if count >= 3:  # 至少点击3次
                pattern_id = hashlib.md5(element_key.encode()).hexdigest()[:12]
                patterns.append({
                    "pattern_id": f"elem_{pattern_id}",
                    "type": "element",
                    "action_sequence": ["click"],
                    "context": {"element": element_key, "click_count": count},
                    "is_new": pattern_id not in [p.pattern_id.replace('elem_', '') for p in self.behavior_patterns.values()]
                })
                
        return patterns
        
    def predict_next_action(self, current_context: Dict) -> Optional[Dict]:
        """基于学习到的模式预测下一步操作"""
        if not self.behavior_patterns:
            return None
            
        # 基于当前上下文匹配最可能的模式
        matched_patterns = []
        
        for pattern in self.behavior_patterns.values():
            score = self._calculate_match_score(pattern, current_context)
            if score > 0.5:
                matched_patterns.append((pattern, score))
                
        if not matched_patterns:
            return None
            
        # 按分数排序，返回最可能的下一步
        matched_patterns.sort(key=lambda x: x[1], reverse=True)
        best_pattern = matched_patterns[0][0]
        
        return {
            "predicted_action": best_pattern.action_sequence[0] if best_pattern.action_sequence else None,
            "confidence": matched_patterns[0][1],
            "pattern_id": best_pattern.pattern_id,
            "context": best_pattern.context
        }
        
    def _calculate_match_score(self, pattern: BehaviorPattern, context: Dict) -> float:
        """计算模式匹配分数"""
        score = 0.0
        
        # 基于频率
        score += min(pattern.frequency / 10, 0.3)
        
        # 基于成功率
        score += pattern.success_rate * 0.3
        
        # 基于上下文匹配
        if pattern.context.get('from_url') == context.get('current_url'):
            score += 0.4
            
        return min(score, 1.0)
        
    def generate_knowledge_report(self) -> Dict:
        """生成知识报告"""
        return {
            "summary": {
                "total_page_patterns": len(self.page_patterns),
                "total_behavior_patterns": len(self.behavior_patterns),
                "total_recorded_actions": sum(p.occurrences for p in self.page_patterns.values()),
                "learning_date": datetime.now().isoformat()
            },
            "page_patterns": [p.to_dict() for p in sorted(self.page_patterns.values(), 
                                                          key=lambda x: x.occurrences, reverse=True)[:10]],
            "behavior_patterns": [p.to_dict() for p in sorted(self.behavior_patterns.values(), 
                                                              key=lambda x: x.frequency, reverse=True)[:10]],
            "insights": self._generate_insights()
        }
        
    def _generate_insights(self) -> List[str]:
        """生成洞察"""
        insights = []
        
        # 高频页面模式
        if self.page_patterns:
            top_page = max(self.page_patterns.values(), key=lambda x: x.occurrences)
            insights.append(f"最常访问的页面类型已出现 {top_page.occurrences} 次")
            
        # 常见操作序列
        seq_patterns = [p for p in self.behavior_patterns.values() if p.pattern_id.startswith('seq_')]
        if seq_patterns:
            top_seq = max(seq_patterns, key=lambda x: x.frequency)
            insights.append(f"最常见的操作序列: {' -> '.join(top_seq.action_sequence)} (出现 {top_seq.frequency} 次)")
            
        # 高频点击元素
        elem_patterns = [p for p in self.behavior_patterns.values() if p.pattern_id.startswith('elem_')]
        if elem_patterns:
            top_elem = max(elem_patterns, key=lambda x: x.frequency)
            insights.append(f"最常点击的元素类型: {top_elem.context.get('element', 'unknown')}")
            
        return insights
        
    def save_knowledge(self, filepath: str):
        """保存学习到的知识"""
        knowledge = self.generate_knowledge_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
        print(f"💾 知识库已保存: {filepath}")
        
    def load_knowledge(self, filepath: str):
        """加载学习到的知识"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                knowledge = json.load(f)
                
            # 恢复页面模式
            for p_data in knowledge.get('page_patterns', []):
                pattern = PagePattern(p_data['pattern_id'], p_data['features'])
                pattern.occurrences = p_data.get('occurrences', 0)
                self.page_patterns[pattern.pattern_id] = pattern
                
            # 恢复行为模式
            for p_data in knowledge.get('behavior_patterns', []):
                pattern = BehaviorPattern(
                    p_data['pattern_id'],
                    p_data['action_sequence'],
                    p_data['context']
                )
                pattern.frequency = p_data.get('frequency', 0)
                self.behavior_patterns[pattern.pattern_id] = pattern
                
            print(f"📚 知识库已加载: {filepath}")
            return True
        except Exception as e:
            print(f"⚠️ 加载知识库失败: {e}")
            return False
