"""
增强型记忆系统核心
整合 ChromaDB（向量检索）和 openclaw-memory-skill（结构化验证）
"""

import hashlib
from typing import List, Dict, Optional, Any, Tuple

from ..embedders.multimodal_embedder import MultimodalEmbedder
from ..storage.chroma_storage import ChromaStorage
from ..storage.ontology_adapter import OntologyAdapter
from ..extractors.task_extractor import TaskExtractor
from .query_result import QueryResult, Evidence, EvidenceType
from .fusion_engine import SSMFusionEngine


class EnhancedMemorySystem:
    """
    增强型记忆系统
    
    架构：
    1. ChromaDB - 负责向量存储和语义检索
    2. openclaw-memory-skill - 负责结构化验证和置信度评估
    3. MultimodalEmbedder - 负责文本和图像嵌入
    """
    
    def __init__(self,
                 collection_name: str = "sentinel_knowledge",
                 persist_directory: Optional[str] = None,
                 api_key: Optional[str] = None):
        """
        初始化增强记忆系统
        
        Args:
            collection_name: ChromaDB 集合名称
            persist_directory: ChromaDB 持久化目录
            api_key: OpenAI API Key
        """
        # 初始化组件
        self.embedder = MultimodalEmbedder(api_key=api_key)
        self.vector_store = ChromaStorage(
            collection_name=collection_name,
            persist_directory=persist_directory
        )
        self.ontology = OntologyAdapter()
        self.extractor = TaskExtractor()
        self.fusion = SSMFusionEngine()
        
        # 配置
        self.min_confidence_threshold = 0.95
        self.top_k_retrieval = 10
        self.top_k_final = 5
        
    def index_task(self, task_path: str) -> bool:
        """
        索引 task 到记忆系统
        
        Args:
            task_path: task 目录路径
            
        Returns:
            是否成功
        """
        print(f"[EnhancedMemorySystem] 开始索引 task: {task_path}")
        
        try:
            # 1. 提取文本数据
            text_chunks = self.extractor.extract_text_chunks(task_path)
            print(f"  - 提取文本块: {len(text_chunks)} 个")
            
            # 2. 提取图像数据
            image_chunks = self.extractor.extract_image_chunks(task_path)
            print(f"  - 提取图像块: {len(image_chunks)} 个")
            
            # 3. 索引文本
            if text_chunks:
                self._index_text_chunks(text_chunks)
            
            # 4. 索引图像
            if image_chunks:
                self._index_image_chunks(image_chunks)
            
            print(f"[EnhancedMemorySystem] 索引完成")
            return True
            
        except Exception as e:
            print(f"[EnhancedMemorySystem] 索引失败: {e}")
            return False
    
    def _index_text_chunks(self, chunks: List[Dict]):
        """索引文本块（使用稳定 ID + upsert，避免重复文档）"""
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_texts(texts)

        valid_chunks = []
        valid_embeddings = []
        valid_ids = []
        valid_metadatas = []

        for chunk, embedding in zip(chunks, embeddings):
            if not embedding:
                continue

            content_digest = hashlib.sha256(
                f"{chunk['task_id']}:{chunk['source']}:{chunk['text'][:200]}".encode()
            ).hexdigest()[:12]
            chunk_id = f"text_{chunk['task_id']}_{content_digest}"

            valid_chunks.append(chunk)
            valid_embeddings.append(embedding)
            valid_ids.append(chunk_id)
            valid_metadatas.append({
                "source": chunk["source"],
                "task_id": chunk["task_id"],
                "timestamp": chunk.get("timestamp", ""),
                "type": "text"
            })

            self.ontology.create_knowledge_entity(
                content=chunk["text"],
                source=chunk["source"],
                task_id=chunk["task_id"],
                confidence=0.9,
                authority_level="observation",
                metadata={
                    "chunk_id": chunk_id,
                    "timestamp": chunk.get("timestamp", "")
                }
            )

        if valid_ids:
            self.vector_store.upsert_texts(
                ids=valid_ids,
                texts=[c["text"] for c in valid_chunks],
                embeddings=valid_embeddings,
                metadatas=valid_metadatas
            )
            print(f"  - 成功索引文本: {len(valid_ids)} 个")
    
    def _index_image_chunks(self, chunks: List[Dict]):
        """索引图像块（若图像模型不可用则跳过）"""
        try:
            image_paths = [c["path"] for c in chunks]
        except Exception:
            print("  - 图像路径提取失败，跳过图像索引")
            return

        try:
            embeddings = self.embedder.embed_images(image_paths)
        except Exception as e:
            print(f"  - 图像嵌入模型不可用，跳过图像索引: {e}")
            return

        valid_chunks = []
        valid_embeddings = []
        valid_ids = []
        valid_metadatas = []

        for chunk, embedding in zip(chunks, embeddings):
            if not embedding:
                continue

            chunk_id = f"img_{chunk['task_id']}_{hashlib.sha256((chunk['task_id'] + ':' + chunk['path']).encode()).hexdigest()[:12]}"

            valid_chunks.append(chunk)
            valid_embeddings.append(embedding)
            valid_ids.append(chunk_id)
            valid_metadatas.append({
                "source": chunk["source"],
                "task_id": chunk["task_id"],
                "timestamp": chunk.get("timestamp", ""),
                "type": "image",
                "video_time": chunk.get("video_time", "")
            })

        if valid_ids:
            try:
                self.vector_store.add_images(
                    ids=valid_ids,
                    image_paths=[c["path"] for c in valid_chunks],
                    embeddings=valid_embeddings,
                    metadatas=valid_metadatas
                )
                print(f"  - 成功索引图像: {len(valid_ids)} 个")
            except Exception as e:
                print(f"  - ChromaDB 图像存储失败，跳过: {e}")
    
    def query(self, question: str, top_k: int = 5) -> QueryResult:
        """
        语义查询 (双向融合)
        """

        # 使用融合引擎
        fusion_answer = self.fusion.query(
            question=question,
            chroma_store=self.vector_store,
            embedder=self.embedder,
            top_k=top_k
        )

        # 转换为 QueryResult
        evidences = []
        for fr in fusion_answer.results:
            evidences.append(Evidence(
                id=fr.task_id or fr.source_detail,
                type=EvidenceType.FUSION,
                content=fr.content,
                source=fr.source_detail,
                task_id=fr.task_id,
                confidence=fr.confidence,
                authority_level="observation",
                metadata={
                    "provenance": fr.provenance,
                    "chroma_distance": fr.chroma_distance,
                    "graph_entities_count": len(fr.graph_entities)
                }
            ))

        return QueryResult(
            query=question,
            answer=fusion_answer.answer,
            confidence=fusion_answer.confidence,
            evidences=evidences,
            total_found=len(fusion_answer.results),
            query_time_ms=fusion_answer.query_time_ms,
            consistency_score=fusion_answer.confidence,
            coverage_score=0.85 if fusion_answer.graph_count > 0 else 0.5,
            authority_score=0.9 if fusion_answer.strategy == "graph_only" else 0.75
        )
    
    def _validate_evidences(self, 
                           vector_results: List[Dict]) -> List[Evidence]:
        """
        验证证据的权威性和置信度
        
        Args:
            vector_results: 向量检索结果
            question: 查询问题
            
        Returns:
            验证后的证据列表
        """
        evidences = []
        
        for result in vector_results:
            metadata = result.get("metadata", {})
            content = result.get("content", "")
            source = metadata.get("source", "unknown")
            task_id = metadata.get("task_id", "")
            
            # 查询知识图谱获取完整元数据
            entity = self.ontology.get_entity_by_content(content)
            
            if entity:
                # 使用知识图谱的验证结果
                validation = self.ontology.validate_entity(entity)
                confidence = validation["overall_score"]
                authority_level = entity.get("metadata", {}).get("authority_level", "manual")
            else:
                # 使用默认置信度
                confidence = 0.7
                authority_level = "observation"
            
            # 计算向量相似度作为辅助置信度
            distance = result.get("distance", 1.0)
            similarity_score = 1.0 - min(distance, 1.0)
            
            # 融合置信度
            final_confidence = confidence * 0.7 + similarity_score * 0.3
            
            # 确定证据类型
            if metadata.get("type") == "image":
                evidence_type = EvidenceType.IMAGE
            else:
                evidence_type = EvidenceType.TEXT
            
            evidence = Evidence(
                id=result.get("id", ""),
                type=evidence_type,
                content=content,
                source=source,
                task_id=task_id,
                confidence=final_confidence,
                authority_level=authority_level,
                metadata=metadata
            )
            
            evidences.append(evidence)
        
        # 按置信度排序
        evidences.sort(key=lambda e: e.confidence, reverse=True)
        
        return evidences
    
    def _generate_answer(self, 
                        question: str, 
                        evidences: List[Evidence]) -> Tuple[str, float, Dict]:
        """
        生成回答
        
        Args:
            question: 问题
            evidences: 证据列表
            
        Returns:
            (回答, 置信度, 详细评分)
        """
        if not evidences:
            return "未找到足够证据", 0.0, {"consistency": 0, "coverage": 0, "authority": 0}
        
        # 1. 证据一致性评分
        consistency_score = self._calculate_consistency(evidences)
        
        # 2. 问题覆盖度评分
        coverage_score = self._calculate_coverage(question, evidences)
        
        # 3. 权威等级评分
        authority_score = self._calculate_authority(evidences)
        
        # 4. 综合置信度
        top_evidence = evidences[0]
        base_confidence = top_evidence.confidence
        
        # 加权融合
        final_confidence = (
            base_confidence * 0.4 +
            consistency_score * 0.25 +
            coverage_score * 0.2 +
            authority_score * 0.15
        )
        
        # 5. 生成回答（基于最可信的证据）
        if final_confidence >= self.min_confidence_threshold:
            answer = self._synthesize_answer(evidences[:3])
        else:
            answer = self._generate_conservative_answer(evidences)
        
        return answer, final_confidence, {
            "consistency": consistency_score,
            "coverage": coverage_score,
            "authority": authority_score
        }
    
    def _calculate_consistency(self, evidences: List[Evidence]) -> float:
        """计算证据一致性"""
        if len(evidences) < 2:
            return 1.0
        
        # 检查顶级证据之间的一致性
        top_evidences = evidences[:3]
        similarities = []
        
        for i in range(len(top_evidences)):
            for j in range(i + 1, len(top_evidences)):
                # 使用嵌入计算语义相似度
                emb1 = self.embedder.embed_text(top_evidences[i].content[:500])
                emb2 = self.embedder.embed_text(top_evidences[j].content[:500])
                
                if emb1 and emb2:
                    sim = self.embedder.compute_similarity(emb1, emb2)
                    similarities.append(sim)
        
        if not similarities:
            return 0.5
        
        return sum(similarities) / len(similarities)
    
    def _calculate_coverage(self, question: str, evidences: List[Evidence]) -> float:
        """计算问题覆盖度"""
        # 提取问题的关键词
        question_keywords = set(self._extract_keywords(question))
        
        if not question_keywords:
            return 0.5
        
        # 检查证据覆盖了多少关键词
        covered_keywords = set()
        for evidence in evidences[:3]:
            evidence_keywords = set(self._extract_keywords(evidence.content))
            covered_keywords.update(evidence_keywords & question_keywords)
        
        coverage = len(covered_keywords) / len(question_keywords)
        return min(coverage, 1.0)
    
    def _calculate_authority(self, evidences: List[Evidence]) -> float:
        """计算权威等级评分"""
        if not evidences:
            return 0.0
        
        # 基于权威等级计算
        authority_scores = []
        for evidence in evidences[:3]:
            priority = self.ontology.get_authority_priority(evidence.authority_level)
            # 转换为分数（1-4分映射到0.75-1.0）
            score = 1.0 - (priority - 1) * 0.083
            authority_scores.append(score)
        
        return sum(authority_scores) / len(authority_scores)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简化版）"""
        # 这里可以使用更复杂的 NLP 方法
        # 简化实现：提取长度大于2的中文字符串和英文单词
        import re
        
        # 中文词汇
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,}', text)
        
        # 英文单词
        english_words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        
        return chinese_words + english_words
    
    def _synthesize_answer(self, evidences: List[Evidence]) -> str:
        """综合证据生成回答"""
        # 简化实现：返回最相关证据的摘要
        # 实际可以使用 LLM 生成更自然的回答
        
        if not evidences:
            return "未找到相关信息"
        
        # 合并证据内容
        combined_content = "\n".join([
            f"[{i+1}] {e.content[:200]}..."
            for i, e in enumerate(evidences[:3])
        ])
        
        return f"基于以下证据：\n{combined_content}"
    
    def _generate_conservative_answer(self, 
                                     evidences: List[Evidence]) -> str:
        """生成保守回答（置信度不足时）"""
        if not evidences:
            return "抱歉，未找到足够可靠的信息来回答这个问题。"
        
        best_evidence = evidences[0]
        return (
            f"根据现有信息（置信度：{best_evidence.confidence:.2f}）：\n"
            f"{best_evidence.content[:300]}...\n"
            f"\n注意：此回答置信度较低，建议进一步核实。"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "vector_store": self.vector_store.get_collection_stats(),
            "thresholds": {
                "min_confidence": self.min_confidence_threshold,
                "top_k_retrieval": self.top_k_retrieval
            }
        }
