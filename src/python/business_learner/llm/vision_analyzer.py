"""
LLM视觉识别模块
使用多模态大模型分析网页截图
"""

import base64
import json
from pathlib import Path
from typing import List, Dict, Optional
import requests
from datetime import datetime

from ..config.settings import LLM_CONFIG


class VisionAnalyzer:
    """视觉分析器 - 使用LLM分析网页截图"""
    
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        """
        初始化视觉分析器
        
        Args:
            api_key: LLM API密钥
            api_base: LLM API基础URL
        """
        self.api_key = api_key or LLM_CONFIG.get("api_key")
        self.api_base = api_base or LLM_CONFIG.get("api_base", "https://api.openai.com/v1")
        self.model = LLM_CONFIG.get("model", "gpt-4-vision-preview")
        self.max_tokens = LLM_CONFIG.get("max_tokens", 2000)
        self.temperature = LLM_CONFIG.get("temperature", 0.3)
        
    def analyze_image(self, image_path: str, prompt: Optional[str] = None) -> Dict:
        """
        分析单张图片
        
        Args:
            image_path: 图片路径
            prompt: 自定义提示词
            
        Returns:
            分析结果
        """
        if not Path(image_path).exists():
            return {"error": f"Image not found: {image_path}"}
        
        # 读取并编码图片
        base64_image = self._encode_image(image_path)
        
        # 构建提示词
        if not prompt:
            prompt = """分析这个网页截图，提取以下信息：
1. 页面类型（首页、列表页、详情页、表单页等）
2. 主要功能模块（导航、搜索、内容区等）
3. 关键UI元素（按钮、输入框、链接等）
4. 页面布局和视觉层次
5. 任何重要的业务信息

请以JSON格式返回结果。"""
        
        # 调用LLM API
        try:
            result = self._call_vision_api(base64_image, prompt)
            return self._parse_result(result, image_path)
        except Exception as e:
            return {
                "error": str(e),
                "image_path": image_path,
                "timestamp": datetime.now().isoformat()
            }
    
    def analyze_images_batch(self, image_paths: List[str], 
                            progress_callback=None) -> List[Dict]:
        """
        批量分析多张图片
        
        Args:
            image_paths: 图片路径列表
            progress_callback: 进度回调函数
            
        Returns:
            分析结果列表
        """
        results = []
        total = len(image_paths)
        
        for i, image_path in enumerate(image_paths):
            if progress_callback:
                progress_callback(i + 1, total, image_path)
            
            result = self.analyze_image(image_path)
            results.append(result)
            
        return results
    
    def analyze_long_image(self, image_path: str) -> Dict:
        """
        分析长图（拼接后的完整页面）
        
        Args:
            image_path: 长图路径
            
        Returns:
            分析结果
        """
        prompt = """这是一个完整网页的长截图。请分析整个页面：
1. 页面整体结构和布局
2. 所有可见的功能模块和区域
3. 完整的导航结构
4. 页面内容概览
5. 用户可能的操作流程

请详细描述这个页面的业务功能和用户体验。"""
        
        return self.analyze_image(image_path, prompt)
    
    def compare_images(self, image_path1: str, image_path2: str) -> Dict:
        """
        对比两张图片（用于检测页面变化）
        
        Args:
            image_path1: 第一张图片
            image_path2: 第二张图片
            
        Returns:
            对比结果
        """
        base64_image1 = self._encode_image(image_path1)
        base64_image2 = self._encode_image(image_path2)
        
        prompt = """对比这两张网页截图，分析：
1. 页面发生了什么变化
2. 用户执行了什么操作
3. 页面状态如何转换
4. 业务逻辑是什么

请以JSON格式返回对比结果。"""
        
        try:
            result = self._call_vision_api_comparison(
                base64_image1, base64_image2, prompt
            )
            return self._parse_result(result, f"{image_path1}_vs_{image_path2}")
        except Exception as e:
            return {
                "error": str(e),
                "image1": image_path1,
                "image2": image_path2
            }
    
    def _encode_image(self, image_path: str) -> str:
        """将图片编码为base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _call_vision_api(self, base64_image: str, prompt: str) -> str:
        """调用视觉API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")
        
        return response.json()["choices"][0]["message"]["content"]
    
    def _call_vision_api_comparison(self, base64_image1: str, 
                                    base64_image2: str, prompt: str) -> str:
        """调用视觉API（对比两张图）"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "第一张图片:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image1}"
                            }
                        },
                        {"type": "text", "text": "第二张图片:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image2}"
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")
        
        return response.json()["choices"][0]["message"]["content"]
    
    def _parse_result(self, result: str, image_path: str) -> Dict:
        """解析LLM返回的结果"""
        parsed = {
            "image_path": image_path,
            "raw_analysis": result,
            "timestamp": datetime.now().isoformat(),
            "parsed_data": {}
        }
        
        # 尝试提取JSON
        try:
            # 查找JSON代码块
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                json_str = result.split("```")[1].split("```")[0]
            else:
                json_str = result
            
            parsed["parsed_data"] = json.loads(json_str)
        except:
            # 如果不是JSON格式，保留原始文本
            parsed["parsed_data"] = {"description": result}
        
        return parsed

