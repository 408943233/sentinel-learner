"""
API数据提取模块
从API响应中提取业务实体
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any

from ..utils.models import APIEntity, ConfidenceLevel


class APIExtractor:
    """API数据提取器"""
    
    # URL模式到业务类型的映射
    URL_PATTERNS = {
        'announcement': ('announcement', '公告系统'),
        'notice': ('announcement', '公告系统'),
        'recruitment': ('recruitment', '招聘系统'),
        'campus': ('recruitment', '招聘系统'),
        'job': ('recruitment', '招聘系统'),
        'product': ('product', '产品系统'),
        'service': ('service', '服务系统'),
    }
    
    def __init__(self, api_responses_path: str):
        """
        初始化提取器
        
        Args:
            api_responses_path: api_responses.json路径
        """
        self.api_path = Path(api_responses_path)
        self.data = self._load_data()
    
    def _load_data(self) -> Dict:
        """加载API响应数据"""
        if not self.api_path.exists():
            return {}
            
        with open(self.api_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract_entities(self) -> List[APIEntity]:
        """
        提取所有业务实体
        
        Returns:
            业务实体列表
        """
        entities = []
        
        for url, response in self.data.items():
            # 确定业务类型
            entity_type, domain = self._infer_business_type(url)
            
            # 解析响应体
            body = self._parse_body(response.get('body', {}))
            
            # 提取数据列表
            data_list = self._extract_data_list(body)
            
            # 创建实体
            for item in data_list:
                if isinstance(item, dict):
                    entity = self._create_entity(item, entity_type, url)
                    if entity:
                        entities.append(entity)
        
        print(f"[APIExtractor] 提取 {len(entities)} 个业务实体")
        return entities
    
    def _infer_business_type(self, url: str) -> tuple:
        """从URL推断业务类型"""
        url_lower = url.lower()
        
        for pattern, (entity_type, domain) in self.URL_PATTERNS.items():
            if pattern in url_lower:
                return entity_type, domain
        
        return 'generic', '通用系统'
    
    def _parse_body(self, body: Any) -> Dict:
        """解析响应体"""
        if isinstance(body, str):
            try:
                return json.loads(body)
            except:
                return {}
        elif isinstance(body, dict):
            return body
        else:
            return {}
    
    def _extract_data_list(self, body: Dict) -> List:
        """从响应体中提取数据列表"""
        data = body.get('data')
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # 可能是分页数据
            list_key = None
            for key in ['list', 'items', 'records', 'data']:
                if key in data:
                    list_key = key
                    break
            
            if list_key and isinstance(data[list_key], list):
                return data[list_key]
            else:
                return [data]
        else:
            return []
    
    def _create_entity(self, item: Dict, entity_type: str, source_url: str) -> Optional[APIEntity]:
        """创建业务实体"""
        # 提取实体名称
        name = self._extract_name(item)
        
        if not name:
            return None
        
        return APIEntity(
            entity_type=entity_type,
            name=name,
            attributes=item,
            source_url=source_url,
            confidence=ConfidenceLevel.HIGH
        )
    
    def _extract_name(self, item: Dict) -> str:
        """从数据项中提取名称"""
        # 优先级：title > name > label > id
        for key in ['title', 'name', 'label', 'id', 'key']:
            if key in item and item[key]:
                value = item[key]
                if isinstance(value, str):
                    return value.strip()
                else:
                    return str(value)
        
        return ''
    
    def get_entity_summary(self, entities: List[APIEntity]) -> Dict:
        """
        获取实体统计摘要
        
        Args:
            entities: 实体列表
            
        Returns:
            统计信息
        """
        summary = {}
        
        for entity in entities:
            entity_type = entity.entity_type
            if entity_type not in summary:
                summary[entity_type] = {
                    'count': 0,
                    'examples': []
                }
            
            summary[entity_type]['count'] += 1
            
            if len(summary[entity_type]['examples']) < 3:
                summary[entity_type]['examples'].append(entity.name)
        
        return summary

