"""
LLM业务理解模块
基于融合数据生成业务理解
"""

import json
from typing import List, Dict, Optional
from dataclasses import asdict

from ..utils.models import PageUnderstanding, BusinessProcess, TaskUnderstanding


class BusinessUnderstander:
    """业务理解器"""
    
    def __init__(self):
        """初始化理解器"""
        pass
    
    def understand_page(self, page: PageUnderstanding) -> Dict:
        """
        理解单个页面
        
        Args:
            page: 页面理解结果
            
        Returns:
            业务理解字典
        """
        understanding = {
            "page_type": page.page_info.page_type,
            "business_domain": page.page_info.business_domain,
            "purpose": self._infer_page_purpose(page),
            "key_functions": self._extract_functions(page),
            "entities": self._summarize_entities(page.api_entities),
            "confidence": page.overall_confidence.value
        }
        
        return understanding
    
    def understand_process(self, process: BusinessProcess) -> Dict:
        """
        理解业务流程
        
        Args:
            process: 业务流程
            
        Returns:
            流程理解字典
        """
        return {
            "name": process.name,
            "description": process.description,
            "step_count": len(process.steps),
            "user_intent": self._infer_user_intent(process),
            "start_page": process.start_page,
            "end_page": process.end_page
        }
    
    def generate_task_summary(self, task: TaskUnderstanding) -> str:
        """
        生成任务总结
        
        Args:
            task: 任务理解
            
        Returns:
            总结文本
        """
        lines = [
            f"# 业务系统分析报告",
            f"",
            f"## 基本信息",
            f"- 业务系统: {task.business_system}",
            f"- 业务领域: {task.business_domain}",
            f"- 分析页面数: {len(task.pages)}",
            f"- 识别流程数: {len(task.processes)}",
            f"",
            f"## 页面类型分布"
        ]
        
        # 统计页面类型
        page_types = {}
        for page in task.pages:
            pt = page.page_info.page_type
            page_types[pt] = page_types.get(pt, 0) + 1
        
        for pt, count in page_types.items():
            lines.append(f"- {pt}: {count} 个页面")
        
        # 业务流程
        lines.extend([
            f"",
            f"## 业务流程"
        ])
        
        for process in task.processes:
            lines.append(f"- {process.name}: {len(process.steps)} 个步骤")
        
        # 关键发现
        if task.key_findings:
            lines.extend([
                f"",
                f"## 关键发现"
            ])
            for finding in task.key_findings:
                lines.append(f"- {finding}")
        
        return "\n".join(lines)
    
    def _infer_page_purpose(self, page: PageUnderstanding) -> str:
        """推断页面目的"""
        purposes = {
            'homepage': '展示系统主要功能和导航入口',
            'recruitment': '展示招聘信息，支持职位浏览和申请',
            'announcement': '展示系统公告和通知',
            'product': '展示产品信息和服务',
            'about': '介绍系统背景和联系方式',
            'login': '用户身份验证入口',
        }
        
        return purposes.get(page.page_info.page_type, '提供特定业务功能')
    
    def _extract_functions(self, page: PageUnderstanding) -> List[str]:
        """提取页面功能"""
        functions = []
        
        # 从交互元素提取功能
        for element in page.fused_elements:
            if element.get('type') == 'interactive_element':
                text = element.get('text', '')
                tag = element.get('tag', '')
                
                # 推断功能
                if tag == 'button':
                    functions.append(f"操作: {text}")
                elif tag == 'a':
                    functions.append(f"导航: {text}")
                elif tag == 'input':
                    functions.append(f"输入: {text}")
        
        # 从API实体提取功能
        for entity in page.api_entities:
            functions.append(f"数据: {entity.entity_type} - {entity.name}")
        
        return list(set(functions))[:10]  # 去重并限制数量
    
    def _summarize_entities(self, entities) -> Dict:
        """总结实体信息"""
        summary = {}
        
        for entity in entities:
            et = entity.entity_type
            if et not in summary:
                summary[et] = {
                    'count': 0,
                    'examples': []
                }
            
            summary[et]['count'] += 1
            if len(summary[et]['examples']) < 3:
                summary[et]['examples'].append(entity.name)
        
        return summary
    
    def _infer_user_intent(self, process: BusinessProcess) -> str:
        """推断用户意图"""
        # 根据流程步骤推断
        actions = [step.action_type for step in process.steps]
        
        if 'click' in actions and 'scroll' in actions:
            return "浏览信息并执行操作"
        elif 'click' in actions:
            return "执行特定操作"
        elif 'scroll' in actions:
            return "浏览内容"
        else:
            return "访问系统功能"
    
    def identify_key_findings(self, task: TaskUnderstanding) -> List[str]:
        """识别关键发现"""
        findings = []
        
        # 1. 多页面类型
        page_types = set(p.page_info.page_type for p in task.pages)
        if len(page_types) > 1:
            findings.append(f"系统包含多种页面类型: {', '.join(page_types)}")
        
        # 2. 业务实体
        entity_types = set(e.entity_type for e in task.entities)
        if entity_types:
            findings.append(f"识别到业务实体类型: {', '.join(entity_types)}")
        
        # 3. 用户流程
        if task.processes:
            findings.append(f"发现 {len(task.processes)} 个用户操作流程")
        
        # 4. 数据质量
        def is_low_confidence(confidence):
            if hasattr(confidence, 'value'):
                return confidence.value == 'low'
            elif hasattr(confidence, 'overall_confidence'):
                return confidence.overall_confidence < 0.5
            else:
                return False
        
        low_confidence_pages = [p for p in task.pages if is_low_confidence(p.overall_confidence)]
        if low_confidence_pages:
            findings.append(f"注意: {len(low_confidence_pages)} 个页面可信度较低")
        
        return findings


if __name__ == "__main__":
    # 测试
    understander = BusinessUnderstander()
    
    # 创建测试数据
    from ..utils.models import PageInfo, APIEntity, ConfidenceLevel
    
    page = PageUnderstanding(
        page_info=PageInfo(
            url="https://example.com",
            title="招聘页面",
            page_type="recruitment",
            business_domain="招聘系统"
        ),
        api_entities=[
            APIEntity(entity_type="job", name="软件工程师", attributes={}, source_url="")
        ]
    )
    
    understanding = understander.understand_page(page)
    print(json.dumps(understanding, ensure_ascii=False, indent=2))
