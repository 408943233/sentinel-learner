"""
API客户端模块 - 支持多种API提供商，使用tenacity实现优雅重试
"""
import base64
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

from .config import get_config
from .exceptions import APIError, RateLimitError, TimeoutError
from .performance_monitor import monitor


class APIProvider(Enum):
    """API提供商枚举"""
    KIMI = "kimi"
    OPENCLAW = "openclaw"
    MOONSHOT = "moonshot"


@dataclass
class APIResponse:
    """API响应数据结构"""
    content: str
    provider: APIProvider
    latency: float
    tokens_used: Optional[int] = None


class BaseAPIClient(ABC):
    """API客户端基类"""
    
    def __init__(self, provider: APIProvider):
        self.provider = provider
        self.config = get_config().api
        self.session = requests.Session()
        
        # 配置连接池
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    @abstractmethod
    def call(self, image_base64: str, prompt: str) -> APIResponse:
        """调用API"""
        pass
    
    def _encode_image(self, image_path: str) -> str:
        """将图片编码为base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


class KimiAPIClient(BaseAPIClient):
    """Kimi Coding API客户端"""
    
    def __init__(self):
        super().__init__(APIProvider.KIMI)
        self.api_key = self.config.kimi_api_key
        self.base_url = self.config.kimi_base_url
        
        if not self.api_key:
            raise ConfigError("Kimi API Key未设置")
        
        # 尝试导入anthropic库
        try:
            from anthropic import Anthropic
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.config.api_timeout
            )
            self.anthropic_available = True
        except ImportError:
            print("  ⚠️ anthropic库未安装，使用requests方式调用")
            self.anthropic_available = False
    
    @monitor.track_time("kimi_api_call")
    def call(self, image_base64: str, prompt: str) -> APIResponse:
        """调用Kimi API"""
        start_time = time.time()
        
        if self.anthropic_available:
            return self._call_with_anthropic(image_base64, prompt, start_time)
        else:
            return self._call_with_requests(image_base64, prompt, start_time)
    
    def _call_with_anthropic(self, image_base64: str, prompt: str, start_time: float) -> APIResponse:
        """使用anthropic库调用"""
        from anthropic import Anthropic
        
        max_retries = self.config.max_retries
        
        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(
                    model=self.config.kimi_model,
                    max_tokens=32768,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image", "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64
                            }}
                        ]
                    }]
                ) as stream:
                    content = ""
                    for text in stream.text_stream:
                        content += text
                
                latency = time.time() - start_time
                return APIResponse(
                    content=content,
                    provider=self.provider,
                    latency=latency
                )
                
            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'rate_limit' in error_str:
                    # 使用更保守的退避策略：从30秒开始，每次翻倍，最多300秒
                    wait_time = min(30 * (2 ** attempt), self.config.max_retry_delay)
                    if attempt < max_retries - 1:
                        print(f"  ⏳ Kimi API限流，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RateLimitError(f"Kimi API限流，已重试{max_retries}次")
                elif 'timeout' in error_str.lower():
                    raise TimeoutError(f"Kimi API超时: {e}")
                else:
                    raise APIError(f"Kimi API调用失败: {e}")
        
        raise APIError("Kimi API调用失败，超出最大重试次数")
    
    def _call_with_requests(self, image_base64: str, prompt: str, start_time: float) -> APIResponse:
        """使用requests调用（备用方案）"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.config.kimi_model,
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image', 'source': {
                        'type': 'base64',
                        'media_type': 'image/jpeg',
                        'data': image_base64
                    }}
                ]
            }],
            'max_tokens': 32768,
            'stream': True
        }
        
        max_retries = self.config.max_retries
        
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f'{self.base_url}/messages',
                    headers=headers,
                    json=payload,
                    timeout=self.config.api_timeout,
                    stream=True
                )
                
                if response.status_code == 429:
                    wait_time = min(60 * (2 ** attempt), self.config.max_retry_delay)
                    if attempt < max_retries - 1:
                        print(f"  ⏳ Kimi API限流(429)，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RateLimitError("Kimi API限流，已重试最大次数")
                
                response.raise_for_status()
                
                # 处理流式响应
                content = ""
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data = line_str[6:]
                            if data != '[DONE]':
                                try:
                                    import json
                                    chunk = json.loads(data)
                                    if 'content' in chunk:
                                        content += chunk['content']
                                except:
                                    pass
                
                latency = time.time() - start_time
                return APIResponse(
                    content=content,
                    provider=self.provider,
                    latency=latency
                )
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = min(30 * (2 ** attempt), self.config.max_retry_delay)
                    print(f"  ⏳ 请求超时，等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise TimeoutError(f"Kimi API超时，已重试{max_retries}次")
            
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = min(10 * (2 ** attempt), self.config.max_retry_delay)
                    print(f"  ⚠️ 请求失败: {e}，等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise APIError(f"Kimi API请求失败: {e}")
        
        raise APIError("Kimi API调用失败，超出最大重试次数")


class MoonshotAPIClient(BaseAPIClient):
    """Moonshot API客户端"""
    
    def __init__(self):
        super().__init__(APIProvider.MOONSHOT)
        self.api_key = self.config.moonshot_api_key
        self.base_url = self.config.moonshot_base_url
        
        if not self.api_key:
            raise ConfigError("Moonshot API Key未设置")
        
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.openai_available = True
        except ImportError:
            print("  ⚠️ openai库未安装，使用requests方式调用")
            self.openai_available = False
    
    @monitor.track_time("moonshot_api_call")
    def call(self, image_base64: str, prompt: str) -> APIResponse:
        """调用Moonshot API"""
        start_time = time.time()
        
        if self.openai_available:
            return self._call_with_openai(image_base64, prompt, start_time)
        else:
            return self._call_with_requests(image_base64, prompt, start_time)
    
    def _call_with_openai(self, image_base64: str, prompt: str, start_time: float) -> APIResponse:
        """使用openai库调用"""
        response = self.client.chat.completions.create(
            model="kimi-k2.5",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }}
                ]
            }],
            temperature=1,
            max_tokens=32768
        )
        
        content = response.choices[0].message.content
        latency = time.time() - start_time
        
        return APIResponse(
            content=content,
            provider=self.provider,
            latency=latency,
            tokens_used=response.usage.total_tokens if response.usage else None
        )
    
    def _call_with_requests(self, image_base64: str, prompt: str, start_time: float) -> APIResponse:
        """使用requests调用"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'kimi-k2.5',
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {
                        'url': f'data:image/jpeg;base64,{image_base64}'
                    }}
                ]
            }],
            'temperature': 1,
            'max_tokens': 32768
        }
        
        max_retries = self.config.max_retries
        
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f'{self.base_url}/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=self.config.api_timeout
                )
                
                if response.status_code == 429:
                    wait_time = min(60 * (2 ** attempt), self.config.max_retry_delay)
                    if attempt < max_retries - 1:
                        print(f"  ⏳ Moonshot API限流，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                
                response.raise_for_status()
                result = response.json()
                
                content = result['choices'][0]['message']['content']
                latency = time.time() - start_time
                
                return APIResponse(
                    content=content,
                    provider=self.provider,
                    latency=latency,
                    tokens_used=result.get('usage', {}).get('total_tokens')
                )
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = min(10 * (2 ** attempt), self.config.max_retry_delay)
                    print(f"  ⚠️ Moonshot API失败: {e}，等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise APIError(f"Moonshot API调用失败: {e}")
        
        raise APIError("Moonshot API调用失败，超出最大重试次数")


class APIClientManager:
    """API客户端管理器 - 管理多个API提供商"""
    
    def __init__(self):
        self.clients: Dict[APIProvider, BaseAPIClient] = {}
        self._init_clients()
    
    def _init_clients(self):
        """初始化所有可用的API客户端"""
        config = get_config().api
        
        # 按优先级初始化
        if config.kimi_api_key:
            try:
                self.clients[APIProvider.KIMI] = KimiAPIClient()
                print("  ✅ Kimi API客户端初始化成功")
            except Exception as e:
                print(f"  ⚠️ Kimi API客户端初始化失败: {e}")
        
        if config.moonshot_api_key:
            try:
                self.clients[APIProvider.MOONSHOT] = MoonshotAPIClient()
                print("  ✅ Moonshot API客户端初始化成功")
            except Exception as e:
                print(f"  ⚠️ Moonshot API客户端初始化失败: {e}")
    
    def call_with_fallback(self, image_base64: str, prompt: str) -> Optional[APIResponse]:
        """
        调用API，带自动降级
        优先级: Kimi -> Moonshot
        """
        providers = [APIProvider.KIMI, APIProvider.MOONSHOT]
        
        for provider in providers:
            if provider in self.clients:
                try:
                    print(f"  🔄 尝试使用 {provider.value} API...")
                    response = self.clients[provider].call(image_base64, prompt)
                    print(f"  ✅ {provider.value} API调用成功 ({response.latency:.2f}s)")
                    return response
                except RateLimitError as e:
                    print(f"  ⚠️ {provider.value} API限流: {e}")
                    continue
                except TimeoutError as e:
                    print(f"  ⚠️ {provider.value} API超时: {e}")
                    continue
                except APIError as e:
                    print(f"  ⚠️ {provider.value} API错误: {e}")
                    continue
        
        print("  ❌ 所有API都失败")
        return None
    
    def get_available_providers(self) -> List[str]:
        """获取可用的API提供商列表"""
        return [p.value for p in self.clients.keys()]


# 便捷函数
def get_api_manager() -> APIClientManager:
    """获取API管理器实例"""
    return APIClientManager()
