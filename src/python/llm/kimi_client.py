"""
Kimi API 客户端
支持 Kimi Coding API (通过 anthropic 库)
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional, Generator
from pathlib import Path

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("  ⚠️ anthropic 库未安装，使用 requests 方式调用")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class KimiClient:
    """Kimi Coding API 客户端"""
    
    DEFAULT_BASE_URL = "https://api.kimi.com/coding/"
    DEFAULT_MODEL = "k2p5"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3
    ):
        self.api_key = api_key or os.getenv('KIMI_CODING_API_KEY')
        if not self.api_key:
            raise ValueError("请提供 Kimi API Key 或设置 KIMI_CODING_API_KEY 环境变量")
        
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # 尝试使用 anthropic 库
        if ANTHROPIC_AVAILABLE:
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.use_anthropic = True
        else:
            self.client = None
            self.use_anthropic = False
        
        logger.info(f"KimiClient 初始化完成，模型: {self.model}, 使用 anthropic: {self.use_anthropic}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            max_tokens: 最大 token 数
            temperature: 温度参数
            stream: 是否流式输出
        
        Returns:
            API 响应
        """
        try:
            if self.use_anthropic:
                return self._chat_with_anthropic(messages, max_tokens, temperature, stream)
            else:
                return self._chat_with_requests(messages, max_tokens, temperature)
            
        except Exception as e:
            logger.error(f"Kimi API 调用失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _chat_with_anthropic(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """使用 anthropic 库调用"""
        
        # 转换消息格式
        system_message = ""
        user_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            elif msg['role'] == 'user':
                user_messages.append({
                    "role": "user",
                    "content": msg['content']
                })
            elif msg['role'] == 'assistant':
                user_messages.append({
                    "role": "assistant", 
                    "content": msg['content']
                })
        
        # 调用 API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature or self.temperature,
            system=system_message if system_message else None,
            messages=user_messages
        )
        
        return {
            'success': True,
            'content': response.content[0].text,
            'usage': {
                'prompt_tokens': response.usage.input_tokens,
                'completion_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            }
        }
    
    def _chat_with_requests(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """使用 requests 调用"""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 转换消息格式
        system_message = ""
        user_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                user_messages.append(msg)
        
        data = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature,
            "messages": user_messages
        }
        
        if system_message:
            data["system"] = system_message
        
        response = requests.post(
            f"{self.base_url}v1/messages",
            headers=headers,
            json=data,
            timeout=120
        )
        
        response.raise_for_status()
        result = response.json()
        
        return {
            'success': True,
            'content': result['content'][0]['text'],
            'usage': {
                'prompt_tokens': result['usage']['input_tokens'],
                'completion_tokens': result['usage']['output_tokens'],
                'total_tokens': result['usage']['input_tokens'] + result['usage']['output_tokens']
            }
        }
    
    def analyze_website_knowledge(
        self,
        task_data: Dict[str, Any],
        dom_snapshots: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        分析网站知识
        
        Args:
            task_data: 任务数据
            dom_snapshots: DOM 快照列表
        
        Returns:
            分析结果
        """
        from .prompts import PromptTemplates
        
        prompt = PromptTemplates.website_knowledge_analysis(
            task_data=task_data,
            dom_snapshots=dom_snapshots
        )
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的网站分析师，擅长从用户行为数据中提取网站结构和业务逻辑。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        result = self.chat(messages)
        
        if result['success']:
            try:
                # 尝试解析 JSON 响应
                content = result['content']
                # 处理可能的 markdown 代码块
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                knowledge = json.loads(content.strip())
                return {
                    'success': True,
                    'knowledge': knowledge,
                    'raw_response': result['content']
                }
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败: {e}")
                return {
                    'success': True,
                    'knowledge': None,
                    'raw_response': result['content'],
                    'parse_error': str(e)
                }
        
        return result
    
    def generate_action_sequence(
        self,
        page_context: Dict[str, Any],
        goal: str,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        生成操作序列
        
        Args:
            page_context: 页面上下文
            goal: 目标描述
            history: 历史操作
        
        Returns:
            操作序列
        """
        from .prompts import PromptTemplates
        
        prompt = PromptTemplates.action_sequence_generation(
            page_context=page_context,
            goal=goal,
            history=history
        )
        
        messages = [
            {
                "role": "system",
                "content": "你是一个网页自动化操作专家，能够根据页面上下文生成合理的用户操作序列。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        result = self.chat(messages)
        
        if result['success']:
            try:
                content = result['content']
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                actions = json.loads(content.strip())
                return {
                    'success': True,
                    'actions': actions,
                    'raw_response': result['content']
                }
            except json.JSONDecodeError:
                return {
                    'success': True,
                    'actions': None,
                    'raw_response': result['content']
                }
        
        return result
    
    def evaluate_similarity(
        self,
        original_actions: List[Dict],
        simulated_actions: List[Dict],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        评估操作相似度
        
        Args:
            original_actions: 原始操作
            simulated_actions: 模拟操作
            context: 上下文信息
        
        Returns:
            相似度评估结果
        """
        from .prompts import PromptTemplates
        
        prompt = PromptTemplates.similarity_evaluation(
            original_actions=original_actions,
            simulated_actions=simulated_actions,
            context=context
        )
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的测试评估专家，擅长比较两组操作的相似度并给出详细分析。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        result = self.chat(messages)
        
        if result['success']:
            try:
                content = result['content']
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                evaluation = json.loads(content.strip())
                return {
                    'success': True,
                    'evaluation': evaluation,
                    'raw_response': result['content']
                }
            except json.JSONDecodeError:
                return {
                    'success': True,
                    'evaluation': None,
                    'raw_response': result['content']
                }
        
        return result


if __name__ == '__main__':
    # 测试客户端
    import sys
    
    # 测试简单对话
    client = KimiClient()
    
    messages = [
        {"role": "user", "content": "你好，请简单介绍一下自己"}
    ]
    
    result = client.chat(messages)
    
    if result['success']:
        print("响应内容:")
        print(result['content'])
        print(f"\nToken 使用: {result['usage']}")
    else:
        print(f"错误: {result['error']}")
