"""
ChromaDB 向量存储层
负责向量数据的存储和检索
"""

import os
from typing import List, Dict, Optional, Any
from pathlib import Path
import json


class ChromaStorage:
    """ChromaDB 存储管理器"""
    
    def __init__(self, 
                 collection_name: str = "sentinel_knowledge",
                 persist_directory: Optional[str] = None,
                 embedding_dimension: int = 1536):
        """
        初始化 ChromaDB 存储
        
        Args:
            collection_name: 集合名称
            persist_directory: 持久化目录
            embedding_dimension: 嵌入维度
        """
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension
        self.persist_directory = persist_directory or os.path.expanduser(
            "~/.sentinel/chroma_db"
        )
        
        self._client = None
        self._collection = None
        
    def _init_client(self):
        """初始化 ChromaDB 客户端"""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                
                # 创建持久化目录
                Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
                
                # 初始化客户端
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                
                # 获取或创建集合
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                
            except ImportError:
                raise ImportError("请安装 chromadb: pip install chromadb")
    
    def add_texts(self,
                  ids: List[str],
                  texts: List[str],
                  embeddings: List[List[float]],
                  metadatas: Optional[List[Dict]] = None) -> bool:
        """
        添加文本到向量存储

        Args:
            ids: 唯一标识符列表
            texts: 文本内容列表
            embeddings: 嵌入向量列表
            metadatas: 元数据列表

        Returns:
            是否成功
        """
        self._init_client()

        if not ids or not texts or not embeddings:
            return False

        try:
            if metadatas:
                metadatas = [
                    {k: self._serialize_value(v) for k, v in m.items()}
                    for m in metadatas
                ]

            self._collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas
            )
            return True
        except Exception as e:
            print(f"[ChromaStorage] 添加文本失败: {e}")
            return False

    def upsert_texts(self,
                     ids: List[str],
                     texts: List[str],
                     embeddings: List[List[float]],
                     metadatas: Optional[List[Dict]] = None) -> bool:
        """
        添加或更新文本到向量存储（幂等：相同 ID 自动覆盖，避免重复文档）

        Args:
            ids: 唯一标识符列表
            texts: 文本内容列表
            embeddings: 嵌入向量列表
            metadatas: 元数据列表

        Returns:
            是否成功
        """
        self._init_client()

        if not ids or not texts or not embeddings:
            return False

        try:
            if metadatas:
                metadatas = [
                    {k: self._serialize_value(v) for k, v in m.items()}
                    for m in metadatas
                ]

            self._collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas
            )
            return True
        except Exception as e:
            print(f"[ChromaStorage] upsert 文本失败: {e}")
            return False
    
    def add_images(self,
                   ids: List[str],
                   image_paths: List[str],
                   embeddings: List[List[float]],
                   metadatas: Optional[List[Dict]] = None) -> bool:
        """
        添加图像到向量存储
        
        Args:
            ids: 唯一标识符列表
            image_paths: 图像路径列表
            embeddings: 嵌入向量列表
            metadatas: 元数据列表
            
        Returns:
            是否成功
        """
        self._init_client()
        
        if not ids or not image_paths or not embeddings:
            return False
        
        try:
            # 图像存储路径作为文档内容
            if metadatas is None:
                metadatas = []
            
            # 确保每个 metadata 包含图像路径
            for i, path in enumerate(image_paths):
                if i < len(metadatas):
                    metadatas[i]['image_path'] = path
                    metadatas[i]['type'] = 'image'
                else:
                    metadatas.append({'image_path': path, 'type': 'image'})
            
            # 序列化元数据
            metadatas = [
                {k: self._serialize_value(v) for k, v in m.items()}
                for m in metadatas
            ]
            
            self._collection.add(
                ids=ids,
                documents=image_paths,  # 存储路径作为文档
                embeddings=embeddings,
                metadatas=metadatas
            )
            return True
        except Exception as e:
            print(f"[ChromaStorage] 添加图像失败: {e}")
            return False
    
    def query(self,
              query_embedding: List[float],
              n_results: int = 10,
              filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        向量相似度查询
        
        Args:
            query_embedding: 查询向量
            n_results: 返回结果数量
            filter_dict: 过滤条件
            
        Returns:
            查询结果列表
        """
        self._init_client()
        
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filter_dict
            )
            
            # 格式化结果
            formatted_results = []
            if results['ids'] and results['ids'][0]:
                for i, doc_id in enumerate(results['ids'][0]):
                    result = {
                        'id': doc_id,
                        'content': results['documents'][0][i] if results['documents'] else None,
                        'distance': results['distances'][0][i] if results['distances'] else None,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                    }
                    formatted_results.append(result)
            
            return formatted_results
        except Exception as e:
            print(f"[ChromaStorage] 查询失败: {e}")
            return []
    
    def query_by_text(self,
                      query_text: str,
                      n_results: int = 10) -> List[Dict]:
        """
        文本查询（需要外部提供嵌入）
        
        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            
        Returns:
            查询结果列表
        """
        # 注意：这里需要外部提供 embedder 来生成查询向量
        # 为了保持解耦，由调用方生成嵌入后调用 query 方法
        raise NotImplementedError("请使用 MultimodalEmbedder 生成嵌入后调用 query 方法")
    
    def delete(self, ids: List[str]) -> bool:
        """
        删除指定 ID 的文档
        
        Args:
            ids: ID 列表
            
        Returns:
            是否成功
        """
        self._init_client()
        
        try:
            self._collection.delete(ids=ids)
            return True
        except Exception as e:
            print(f"[ChromaStorage] 删除失败: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Returns:
            统计信息
        """
        self._init_client()
        
        try:
            count = self._collection.count()
            return {
                'collection_name': self.collection_name,
                'total_documents': count,
                'persist_directory': self.persist_directory,
                'embedding_dimension': self.embedding_dimension
            }
        except Exception as e:
            print(f"[ChromaStorage] 获取统计信息失败: {e}")
            return {}
    
    def reset_collection(self) -> bool:
        """
        重置集合（清空所有数据）
        
        Returns:
            是否成功
        """
        self._init_client()
        
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except Exception as e:
            print(f"[ChromaStorage] 重置集合失败: {e}")
            return False
    
    def _serialize_value(self, value: Any) -> Any:
        """序列化元数据值"""
        if isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        else:
            return str(value)
