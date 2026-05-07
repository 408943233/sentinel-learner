"""
大模型接口模块 - 封装 Kimi API 调用
"""

from .kimi_client import KimiClient
from .prompts import PromptTemplates

__all__ = ['KimiClient', 'PromptTemplates']
