"""
Prompt 模板
用于各种 LLM 任务
"""

import json
from typing import List, Dict, Any, Optional


class PromptTemplates:
    """Prompt 模板集合"""
    
    @staticmethod
    def website_knowledge_analysis(
        task_data: Dict[str, Any],
        dom_snapshots: Optional[List[Dict]] = None
    ) -> str:
        """
        网站知识分析 Prompt
        
        分析任务数据，提取网站结构、业务逻辑和用户流程
        """
        
        prompt = f"""请分析以下网站录制数据，提取网站的知识和业务逻辑。

## 任务基本信息
- 任务ID: {task_data.get('task_id', 'unknown')}
- 域名: {task_data.get('domain', 'unknown')}
- 事件总数: {len(task_data.get('events', []))}
- 页面数: {len(task_data.get('pages', {}))}

## 操作统计
{json.dumps(task_data.get('actions', {}), indent=2, ensure_ascii=False)}

## 页面信息
"""
        
        # 添加页面信息
        for page_key, page_info in list(task_data.get('pages', {}).items())[:5]:
            prompt += f"""
### 页面: {page_key}
- 访问次数: {page_info.get('visit_count', 0)}
- 页面类型: {', '.join(page_info.get('page_types', ['unknown']))}
- 操作分布: {json.dumps(page_info.get('actions', {}), ensure_ascii=False)}
- 平均DOM统计: {json.dumps(page_info.get('avg_dom_stats', {}), ensure_ascii=False)}
"""
        
        # 添加导航流信息
        prompt += f"""
## 导航流程
{json.dumps(task_data.get('navigation_flows', [])[:10], indent=2, ensure_ascii=False)}

## API 端点
{json.dumps(list(task_data.get('api_endpoints', []))[:10], indent=2, ensure_ascii=False)}

请分析以上数据，以 JSON 格式输出以下信息：

```json
{{
  "website_overview": {{
    "domain": "网站域名",
    "industry": "行业类型（金融/电商/企业官网等）",
    "main_function": "主要功能描述"
  }},
  "page_structure": [
    {{
      "page_type": "页面类型",
      "url_pattern": "URL模式",
      "purpose": "页面用途",
      "key_elements": ["关键元素1", "关键元素2"],
      "typical_actions": ["典型操作1", "典型操作2"]
    }}
  ],
  "user_flows": [
    {{
      "flow_name": "流程名称",
      "steps": [
        {{"action": "操作", "target": "目标", "purpose": "目的"}}
      ],
      "entry_points": ["入口页面"],
      "exit_points": ["出口页面"]
    }}
  ],
  "business_logic": {{
    "core_features": ["核心功能1", "核心功能2"],
    "data_patterns": ["数据模式1", "数据模式2"],
    "interaction_patterns": ["交互模式1", "交互模式2"]
  }},
  "technical_insights": {{
    "frontend_framework": "推测的前端框架",
    "api_structure": "API结构特点",
    "state_management": "状态管理方式"
  }}
}}
```

请确保输出是有效的 JSON 格式。"""
        
        return prompt
    
    @staticmethod
    def action_sequence_generation(
        page_context: Dict[str, Any],
        goal: str,
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        操作序列生成 Prompt
        
        根据页面上下文和目标生成操作序列
        """
        
        history_str = ""
        if history:
            history_str = f"""
## 已执行的操作历史
{json.dumps(history[-5:], indent=2, ensure_ascii=False)}
"""
        
        prompt = f"""请根据以下页面上下文，生成完成目标的操作序列。

## 目标
{goal}

## 当前页面信息
- URL: {page_context.get('url', 'unknown')}
- 页面类型: {page_context.get('page_type', 'unknown')}
- 标题: {page_context.get('title', '')}

## 页面结构
{json.dumps(page_context.get('dom_stats', {}), indent=2, ensure_ascii=False)}

## 可交互元素
"""
        
        # 添加可交互元素
        elements = page_context.get('interactive_elements', [])
        for i, elem in enumerate(elements[:15]):
            prompt += f"{i+1}. {elem.get('tagName', 'unknown')} - {elem.get('text', '')[:30]} (选择器: {elem.get('selector', 'unknown')})\n"
        
        prompt += history_str
        
        prompt += f"""
请生成操作序列以完成目标。以 JSON 格式输出：

```json
{{
  "actions": [
    {{
      "type": "操作类型 (click/input/scroll/navigate等)",
      "target": {{
        "selector": "CSS选择器或XPath",
        "tagName": "元素标签名",
        "text": "元素文本",
        "coordinates": {{"x": 100, "y": 200}}
      }},
      "value": "输入值（如果是input操作）",
      "expected_outcome": "期望的结果",
      "confidence": 0.95,
      "reasoning": "选择此操作的理由"
    }}
  ],
  "estimated_steps": 5,
  "alternative_paths": ["备选路径1", "备选路径2"],
  "risk_factors": ["可能的风险1", "可能的风险2"]
}}
```

请确保：
1. 选择器尽可能精确
2. 每个操作都有明确的目的
3. 考虑页面加载和异步操作
4. 输出有效的 JSON 格式"""
        
        return prompt
    
    @staticmethod
    def similarity_evaluation(
        original_actions: List[Dict],
        simulated_actions: List[Dict],
        context: Optional[Dict] = None
    ) -> str:
        """
        相似度评估 Prompt
        
        比较原始操作和模拟操作的相似度
        """
        
        prompt = f"""请比较以下两组操作序列的相似度。

## 原始操作序列（用户真实操作）
{json.dumps(original_actions, indent=2, ensure_ascii=False)}

## 模拟操作序列（AI生成的操作）
{json.dumps(simulated_actions, indent=2, ensure_ascii=False)}
"""
        
        if context:
            prompt += f"""
## 上下文信息
- 页面URL: {context.get('url', 'unknown')}
- 页面类型: {context.get('page_type', 'unknown')}
- 目标: {context.get('goal', 'unknown')}
"""
        
        prompt += """
请评估两组操作的相似度，以 JSON 格式输出：

```json
{
  "overall_similarity": 0.85,
  "metrics": {
    "action_sequence": {
      "score": 0.90,
      "analysis": "操作顺序的匹配程度分析"
    },
    "target_elements": {
      "score": 0.85,
      "analysis": "目标元素选择的匹配程度分析"
    },
    "timing": {
      "score": 0.70,
      "analysis": "操作时机的匹配程度分析"
    },
    "intent": {
      "score": 0.95,
      "analysis": "操作意图的匹配程度分析"
    }
  },
  "matched_actions": [
    {
      "original_index": 0,
      "simulated_index": 0,
      "similarity": 0.95,
      "notes": "完全匹配"
    }
  ],
  "mismatched_actions": [
    {
      "index": 2,
      "original": "原始操作",
      "simulated": "模拟操作",
      "reason": "不匹配的原因"
    }
  ],
  "analysis": {
    "strengths": ["优势1", "优势2"],
    "weaknesses": ["不足1", "不足2"],
    "improvement_suggestions": ["改进建议1", "改进建议2"]
  },
  "learning_quality": "excellent|good|fair|poor",
  "recommendations": ["后续学习建议"]
}
```

评估标准：
- excellent (0.9-1.0): 几乎完全匹配，学习成功
- good (0.7-0.9): 主要流程匹配，细节有差异
- fair (0.5-0.7): 部分匹配，需要改进
- poor (0.0-0.5): 匹配度低，需要重新学习"""
        
        return prompt
    
    @staticmethod
    def dom_structure_analysis(
        dom_snapshot: Dict[str, Any],
        changes: Optional[List[Dict]] = None
    ) -> str:
        """
        DOM 结构分析 Prompt
        """
        
        prompt = f"""请分析以下 DOM 结构。

## DOM 统计信息
{json.dumps(dom_snapshot.get('stats', {}), indent=2, ensure_ascii=False)}

## 关键元素
"""
        
        elements = dom_snapshot.get('key_elements', [])
        for elem in elements[:20]:
            prompt += f"- {elem.get('tagName')}: {elem.get('text', '')[:50]} ({elem.get('selector')})\n"
        
        if changes:
            prompt += f"""
## DOM 变化
{json.dumps(changes, indent=2, ensure_ascii=False)}
"""
        
        prompt += """
请分析 DOM 结构，以 JSON 格式输出：

```json
{
  "layout_type": "布局类型（如：header-main-footer, sidebar-content等）",
  "component_structure": ["组件1", "组件2"],
  "interactive_zones": [
    {
      "name": "交互区域名称",
      "selector": "选择器",
      "elements": ["元素1", "元素2"],
      "purpose": "用途"
    }
  ],
  "accessibility_issues": ["可访问性问题1"],
  "performance_considerations": ["性能考虑1"]
}
```"""
        
        return prompt


if __name__ == '__main__':
    # 测试模板
    test_data = {
        'task_id': 'test_001',
        'domain': 'example.com',
        'events': [],
        'pages': {
            'home': {
                'visit_count': 5,
                'page_types': ['home'],
                'actions': {'click': 10, 'scroll': 3}
            }
        },
        'actions': {'click': 20, 'scroll': 5},
        'navigation_flows': [],
        'api_endpoints': set(['/api/data'])
    }
    
    prompt = PromptTemplates.website_knowledge_analysis(test_data)
    print("生成的 Prompt 长度:", len(prompt))
    print("\nPrompt 预览:")
    print(prompt[:500] + "...")
