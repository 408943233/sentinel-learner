"""
API Schema 深层解析模块
从 API 响应中提取完整的 Schema 结构，包括字段类型、嵌套关系等
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum


class FieldType(Enum):
    """字段类型"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass
class SchemaField:
    """Schema 字段定义"""
    name: str
    field_type: FieldType
    required: bool = False
    description: str = ""
    example: Any = None
    nested_fields: List['SchemaField'] = field(default_factory=list)
    array_item_type: Optional['SchemaField'] = None


@dataclass
class APISchema:
    """API Schema 定义"""
    endpoint: str
    method: str = "GET"
    description: str = ""
    request_schema: Optional[SchemaField] = None
    response_schema: Optional[SchemaField] = None
    business_entity: str = ""
    pagination_info: Optional[Dict] = None


class APISchemaExtractor:
    """API Schema 提取器"""

    def __init__(self, api_responses_path: str):
        """
        初始化提取器

        Args:
            api_responses_path: api_responses.json 路径
        """
        self.api_path = Path(api_responses_path)
        self.data = self._load_data()

    def _load_data(self) -> Dict:
        """加载 API 响应数据"""
        if not self.api_path.exists():
            return {}

        with open(self.api_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def extract_schemas(self) -> List[APISchema]:
        """
        提取所有 API 的 Schema

        Returns:
            API Schema 列表
        """
        schemas = []

        for url, response in self.data.items():
            schema = self._extract_single_schema(url, response)
            if schema:
                schemas.append(schema)

        print(f"[APISchemaExtractor] 提取 {len(schemas)} 个 API Schema")
        return schemas

    def _extract_single_schema(self, url: str, response: Dict) -> Optional[APISchema]:
        """提取单个 API 的 Schema"""
        body = self._parse_body(response.get('body', {}))

        if not body:
            return None

        # 推断业务实体类型
        business_entity = self._infer_business_entity(url)

        # 构建响应 Schema
        response_schema = self._build_schema_from_data(body, "root")

        # 提取分页信息
        pagination_info = self._extract_pagination_info(body)

        return APISchema(
            endpoint=url,
            method=response.get('method', 'GET'),
            description=self._generate_description(url, business_entity),
            response_schema=response_schema,
            business_entity=business_entity,
            pagination_info=pagination_info
        )

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

    def _infer_business_entity(self, url: str) -> str:
        """从 URL 推断业务实体类型"""
        url_lower = url.lower()

        patterns = {
            'announcement': '公告',
            'notice': '通知',
            'recruitment': '招聘',
            'campus': '校园招聘',
            'job': '职位',
            'position': '职位',
            'product': '产品',
            'service': '服务',
            'user': '用户',
            'order': '订单',
            'category': '分类',
            'tag': '标签',
            'comment': '评论',
            'article': '文章',
            'news': '新闻',
            'banner': '轮播图',
            'config': '配置',
            'setting': '设置',
        }

        for pattern, entity in patterns.items():
            if pattern in url_lower:
                return entity

        return '数据'

    def _build_schema_from_data(self, data: Any, field_name: str) -> SchemaField:
        """从数据构建 Schema 字段"""
        field_type = self._infer_type(data)

        if field_type == FieldType.OBJECT and isinstance(data, dict):
            nested_fields = []
            for key, value in data.items():
                nested_field = self._build_schema_from_data(value, key)
                nested_fields.append(nested_field)

            return SchemaField(
                name=field_name,
                field_type=field_type,
                nested_fields=nested_fields,
                example=self._get_example_value(data)
            )

        elif field_type == FieldType.ARRAY and isinstance(data, list):
            if data:
                item_schema = self._build_schema_from_data(data[0], "item")
                return SchemaField(
                    name=field_name,
                    field_type=field_type,
                    array_item_type=item_schema,
                    example=data[:3] if len(data) > 3 else data
                )
            else:
                return SchemaField(
                    name=field_name,
                    field_type=field_type,
                    example=[]
                )

        else:
            return SchemaField(
                name=field_name,
                field_type=field_type,
                example=data
            )

    def _infer_type(self, value: Any) -> FieldType:
        """推断数据类型"""
        if value is None:
            return FieldType.NULL
        elif isinstance(value, bool):
            return FieldType.BOOLEAN
        elif isinstance(value, int):
            return FieldType.INTEGER
        elif isinstance(value, float):
            return FieldType.NUMBER
        elif isinstance(value, str):
            return FieldType.STRING
        elif isinstance(value, list):
            return FieldType.ARRAY
        elif isinstance(value, dict):
            return FieldType.OBJECT
        else:
            return FieldType.STRING

    def _extract_pagination_info(self, body: Dict) -> Optional[Dict]:
        """提取分页信息"""
        data = body.get('data', {})

        if not isinstance(data, dict):
            return None

        pagination_keys = ['page', 'size', 'total', 'pages', 'hasNext', 'hasPrevious']
        found_keys = [k for k in pagination_keys if k in data]

        if found_keys:
            return {
                'has_pagination': True,
                'fields': found_keys,
                'page': data.get('page'),
                'size': data.get('size'),
                'total': data.get('total'),
                'pages': data.get('pages')
            }

        return None

    def _generate_description(self, url: str, entity: str) -> str:
        """生成 API 描述"""
        if 'list' in url.lower() or 'get' in url.lower():
            return f"获取{entity}列表"
        elif 'detail' in url.lower():
            return f"获取{entity}详情"
        elif 'create' in url.lower() or 'add' in url.lower():
            return f"创建{entity}"
        elif 'update' in url.lower():
            return f"更新{entity}"
        elif 'delete' in url.lower() or 'remove' in url.lower():
            return f"删除{entity}"
        else:
            return f"{entity}相关操作"

    def _get_example_value(self, data: Any) -> Any:
        """获取示例值（截断长数据）"""
        if isinstance(data, dict):
            return {k: self._get_example_value(v) for k, v in list(data.items())[:5]}
        elif isinstance(data, list):
            return [self._get_example_value(item) for item in data[:3]]
        elif isinstance(data, str) and len(data) > 100:
            return data[:100] + "..."
        else:
            return data

    def get_schema_summary(self, schemas: List[APISchema]) -> Dict:
        """
        获取 Schema 统计摘要

        Args:
            schemas: Schema 列表

        Returns:
            统计信息
        """
        summary = {
            'total_apis': len(schemas),
            'business_entities': {},
            'endpoints': []
        }

        for schema in schemas:
            entity = schema.business_entity
            if entity not in summary['business_entities']:
                summary['business_entities'][entity] = 0
            summary['business_entities'][entity] += 1

            summary['endpoints'].append({
                'url': schema.endpoint,
                'method': schema.method,
                'entity': entity,
                'description': schema.description
            })

        return summary

    def export_openapi_spec(self, schemas: List[APISchema]) -> Dict:
        """
        导出为 OpenAPI 风格的规范

        Args:
            schemas: Schema 列表

        Returns:
            OpenAPI 规范字典
        """
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "API Schema",
                "version": "1.0.0"
            },
            "paths": {}
        }

        for schema in schemas:
            path = schema.endpoint.replace('https://', '').replace('http://', '')
            path = '/' + path.split('/', 1)[1] if '/' in path else path

            spec["paths"][path] = {
                schema.method.lower(): {
                    "summary": schema.description,
                    "tags": [schema.business_entity],
                    "responses": {
                        "200": {
                            "description": "成功响应",
                            "content": {
                                "application/json": {
                                    "schema": self._schema_to_dict(schema.response_schema)
                                }
                            }
                        }
                    }
                }
            }

        return spec

    def _schema_to_dict(self, field: SchemaField) -> Dict:
        """将 SchemaField 转换为字典"""
        result = {
            "type": field.field_type.value,
            "description": field.description
        }

        if field.example is not None:
            result["example"] = field.example

        if field.nested_fields:
            result["properties"] = {}
            for nested in field.nested_fields:
                result["properties"][nested.name] = self._schema_to_dict(nested)

        if field.array_item_type:
            result["items"] = self._schema_to_dict(field.array_item_type)

        return result
