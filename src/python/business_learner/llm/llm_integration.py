"""
LLM Integration Module (理解层)
使用大模型进行深度业务理解
"""

import json
import os
from typing import List, Dict, Optional, Any
import requests
from dataclasses import dataclass

from ..config.settings import LLM_CONFIG


@dataclass
class LLMResponse:
    """LLM响应"""
    success: bool
    content: str
    parsed_data: Dict = None
    error_message: str = ""


class LLMIntegrationModule:
    """LLM集成模块 - 理解层核心"""
    
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        初始化LLM模块
        
        Args:
            api_key: API密钥
            api_base: API基础URL
        """
        self.api_key = api_key or LLM_CONFIG.get("api_key") or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or LLM_CONFIG.get("api_base", "https://api.openai.com/v1")
        self.model = LLM_CONFIG.get("model", "gpt-4")
        self.max_tokens = LLM_CONFIG.get("max_tokens", 4000)
        self.temperature = LLM_CONFIG.get("temperature", 0.3)
    
    def _call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """调用LLM"""
        if not self.api_key:
            return LLMResponse(
                success=False,
                content="",
                error_message="未配置API密钥"
            )
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return LLMResponse(
                    success=True,
                    content=content,
                    parsed_data=self._parse_json_from_response(content)
                )
            else:
                return LLMResponse(
                    success=False,
                    content="",
                    error_message=f"API错误: {response.status_code} - {response.text}"
                )
        except Exception as e:
            return LLMResponse(
                success=False,
                content="",
                error_message=str(e)
            )
    
    def _parse_json_from_response(self, content: str) -> Dict:
        """从响应中解析JSON"""
        try:
            # 尝试直接解析
            return json.loads(content)
        except:
            pass
        
        # 尝试提取代码块中的JSON
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                # 尝试找到JSON对象
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1:
                    json_str = content[start:end+1]
                else:
                    return {"raw_text": content}
            
            return json.loads(json_str)
        except:
            return {"raw_text": content}
    
    # ========== Prompt 1: 页面结构理解 ==========
    def understand_page_structure(self, 
                                   page_info: Dict,
                                   dom_elements: List[Dict],
                                   visual_description: Optional[str] = None) -> LLMResponse:
        """
        页面结构理解
        
        Args:
            page_info: 页面基本信息
            dom_elements: DOM元素列表
            visual_description: 视觉描述（可选）
            
        Returns:
            LLM响应
        """
        system_prompt = """你是一个专业的网页结构分析专家。请分析网页的结构和功能。"""
        
        prompt = f"""请分析以下网页的结构：

## 页面基本信息
- URL: {page_info.get('url', 'N/A')}
- 标题: {page_info.get('title', 'N/A')}
- 页面类型: {page_info.get('page_type', 'N/A')}

## DOM元素
```json
{json.dumps(dom_elements[:30], ensure_ascii=False, indent=2)}
```

## 任务
请分析这个页面，识别：
1. 功能模块（导航、搜索、内容区等）
2. 导航结构（主导航、面包屑、页脚等）
3. 主要内容区域
4. 页面布局类型

请以JSON格式返回：
{{
    "page_structure": {{
        "layout_type": "布局类型",
        "main_sections": ["主要区域1", "主要区域2"],
        "navigation": {{
            "header_nav": ["导航项1", "导航项2"],
            "sidebar": ["侧边栏项1"],
            "footer": ["页脚项1"]
        }}
    }},
    "functional_modules": [
        {{"name": "模块名", "type": "模块类型", "description": "描述"}}
    ],
    "content_areas": [
        {{"name": "内容区名", "content_type": "内容类型", "importance": "high/medium/low"}}
    ]
}}"""
        
        return self._call_llm(prompt, system_prompt)
    
    # ========== Prompt 2: 业务流程理解 ==========
    def understand_business_process(self,
                                     process_steps: List[Dict],
                                     page_transitions: List[Dict]) -> LLMResponse:
        """
        业务流程理解
        
        Args:
            process_steps: 流程步骤列表
            page_transitions: 页面转换列表
            
        Returns:
            LLM响应
        """
        system_prompt = """你是一个业务流程分析专家。请分析用户操作序列，理解业务目的和流程。"""
        
        prompt = f"""请分析以下用户操作流程：

## 操作步骤
```json
{json.dumps(process_steps, ensure_ascii=False, indent=2)}
```

## 页面转换
```json
{json.dumps(page_transitions, ensure_ascii=False, indent=2)}
```

## 任务
请分析这个操作序列，理解：
1. 用户的业务目的是什么？
2. 完整的操作流程是什么？
3. 每个步骤的业务意义
4. 是否有可选路径或分支？

请以JSON格式返回：
{{
    "business_goal": "业务目标描述",
    "process_summary": "流程概要",
    "detailed_steps": [
        {{
            "step_number": 1,
            "action": "操作",
            "business_meaning": "业务意义",
            "page": "所在页面"
        }}
    ],
    "alternative_paths": ["可选路径1", "可选路径2"],
    "key_decision_points": ["决策点1", "决策点2"]
}}"""
        
        return self._call_llm(prompt, system_prompt)
    
    # ========== Prompt 3: 业务实体提取 ==========
    def extract_business_entities(self,
                                   page_content: str,
                                   api_data: List[Dict],
                                   page_type: str) -> LLMResponse:
        """
        业务实体提取
        
        Args:
            page_content: 页面文本内容
            api_data: API数据
            page_type: 页面类型
            
        Returns:
            LLM响应
        """
        system_prompt = """你是一个业务数据提取专家。请从页面中提取业务实体和数据。"""
        
        prompt = f"""请从以下页面中提取业务实体：

## 页面类型
{page_type}

## 页面内容
```
{page_content[:2000]}
```

## API数据
```json
{json.dumps(api_data, ensure_ascii=False, indent=2)}
```

## 任务
请提取页面中的业务数据实体，例如：
- 公司信息（名称、地址、联系方式等）
- 产品信息（名称、价格、描述等）
- 配置项（设置、选项、参数等）
- 业务对象（订单、用户、文章等）

请以JSON格式返回：
{{
    "entities": [
        {{
            "entity_type": "实体类型",
            "entity_name": "实体名称",
            "attributes": {{
                "属性1": "值1",
                "属性2": "值2"
            }},
            "source": "数据来源",
            "confidence": "high/medium/low"
        }}
    ],
    "entity_relationships": [
        {{
            "from": "实体A",
            "relationship": "关系类型",
            "to": "实体B"
        }}
    ]
}}"""
        
        return self._call_llm(prompt, system_prompt)
    
    # ========== Prompt 4: 变更影响分析 ==========
    def analyze_change_impact(self,
                              change_description: str,
                              affected_pages: List[Dict],
                              system_context: Dict) -> LLMResponse:
        """
        变更影响分析
        
        Args:
            change_description: 变更描述
            affected_pages: 受影响的页面列表
            system_context: 系统上下文
            
        Returns:
            LLM响应
        """
        system_prompt = """你是一个系统架构分析师。请分析变更对系统的影响。"""
        
        prompt = f"""请分析以下变更对系统的影响：

## 变更描述
{change_description}

## 系统上下文
```json
{json.dumps(system_context, ensure_ascii=False, indent=2)}
```

## 可能受影响的页面
```json
{json.dumps(affected_pages, ensure_ascii=False, indent=2)}
```

## 任务
请分析如果进行这个变更，会影响：
1. 哪些页面和功能？
2. 哪些业务流程？
3. 哪些数据实体？
4. 潜在的风险和注意事项
5. 建议的实施步骤

请以JSON格式返回：
{{
    "impact_summary": "影响概要",
    "affected_components": {{
        "pages": ["页面1", "页面2"],
        "functions": ["功能1", "功能2"],
        "processes": ["流程1", "流程2"],
        "entities": ["实体1", "实体2"]
    }},
    "risk_assessment": {{
        "level": "high/medium/low",
        "risks": ["风险1", "风险2"],
        "mitigations": ["缓解措施1", "缓解措施2"]
    }},
    "implementation_steps": [
        "步骤1: xxx",
        "步骤2: xxx"
    ],
    "testing_considerations": ["测试点1", "测试点2"]
}}"""
        
        return self._call_llm(prompt, system_prompt)
    
    # ========== 批量处理方法 ==========
    def batch_understand_pages(self, pages_data: List[Dict]) -> List[LLMResponse]:
        """批量理解多个页面"""
        results = []
        for page_data in pages_data:
            result = self.understand_page_structure(
                page_data.get('info', {}),
                page_data.get('elements', []),
                page_data.get('visual_description')
            )
            results.append(result)
        return results

