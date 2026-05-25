"""
多模态嵌入器
支持文本和图像的嵌入生成
"""

import os
import base64
from typing import List, Optional, Union
from pathlib import Path
import numpy as np


class MultimodalEmbedder:
    """多模态嵌入器（优先本地模型，OpenAI API 为 fallback）"""

    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 默认维度，兼容 OpenAI 1536

    def __init__(self,
                 text_model: str = "all-MiniLM-L6-v2",
                 image_model: str = "clip-vit-base-patch32",
                 api_key: Optional[str] = None):
        self.text_model = text_model
        self.image_model = image_model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        self._text_embedder = None     # sentence-transformers 本地模型
        self._text_client = None       # OpenAI API (fallback)
        self._image_processor = None
        self._image_model_instance = None
        self._embedding_dim = None     # 运行时确定

    def _init_text_embedder(self):
        """初始化本地文本嵌入（优先 sentence-transformers，fallback OpenAI）"""
        if self._text_embedder is not None or self._text_client is not None:
            return

        # 优先尝试本地 sentence-transformers（仅本调用离线，不污染全局环境）
        _hf_offline = os.environ.get('HF_HUB_OFFLINE')
        _tr_offline = os.environ.get('TRANSFORMERS_OFFLINE')
        try:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            from sentence_transformers import SentenceTransformer
            self._text_embedder = SentenceTransformer(self.text_model, local_files_only=True)
            dim = self._text_embedder.get_sentence_embedding_dimension()
            self._embedding_dim = dim
            MultimodalEmbedder.EMBEDDING_DIM = dim
            print(f"[MultimodalEmbedder] 本地模型就绪: {self.text_model} (dim={dim})")
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"[MultimodalEmbedder] 本地模型加载失败: {e}")
        finally:
            if _hf_offline is not None:
                os.environ['HF_HUB_OFFLINE'] = _hf_offline
            else:
                os.environ.pop('HF_HUB_OFFLINE', None)
            if _tr_offline is not None:
                os.environ['TRANSFORMERS_OFFLINE'] = _tr_offline
            else:
                os.environ.pop('TRANSFORMERS_OFFLINE', None)

        # Fallback OpenAI
        if self.api_key:
            try:
                from openai import OpenAI
                self._text_client = OpenAI(api_key=self.api_key)
                self._embedding_dim = 1536
                print("[MultimodalEmbedder] Fallback OpenAI API")
            except ImportError:
                raise ImportError(
                    "请安装嵌入依赖: pip install sentence-transformers openai")

    def _init_text_client(self):
        """兼容旧接口"""
        self._init_text_embedder()
    
    def _init_image_model(self):
        """初始化图像嵌入模型"""
        if self._image_model_instance is None:
            try:
                from transformers import CLIPProcessor, CLIPModel
                import torch
                
                self._image_processor = CLIPProcessor.from_pretrained(
                    f"openai/{self.image_model}",
                    use_fast=True
                )
                self._image_model_instance = CLIPModel.from_pretrained(
                    f"openai/{self.image_model}"
                )
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                self._image_model_instance.to(self._device)
            except ImportError:
                raise ImportError("请安装 transformers 和 torch: pip install transformers torch")
    
    def embed_text(self, text: str) -> List[float]:
        """生成单个文本嵌入"""
        self._init_text_embedder()

        text = text.strip()
        if not text:
            return []

        if self._text_embedder is not None:
            try:
                vec = self._text_embedder.encode(text, normalize_embeddings=True)
                return vec.tolist()
            except Exception as e:
                print(f"[MultimodalEmbedder] 本地嵌入失败: {e}")

        if self._text_client is not None:
            try:
                response = self._text_client.embeddings.create(
                    model=self.text_model,
                    input=text
                )
                return response.data[0].embedding
            except Exception as e:
                print(f"[MultimodalEmbedder] OpenAI嵌入失败: {e}")

        return []
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量生成文本嵌入"""
        self._init_text_embedder()

        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = [t.strip() for t in texts[i:i + batch_size] if t.strip()]
            if not batch:
                continue

            if self._text_embedder is not None:
                try:
                    vecs = self._text_embedder.encode(batch, normalize_embeddings=True,
                                                       batch_size=batch_size,
                                                       show_progress_bar=False)
                    embeddings.extend(vecs.tolist())
                    continue
                except Exception as e:
                    print(f"[MultimodalEmbedder] 本地批量嵌入失败: {e}")

            if self._text_client is not None:
                try:
                    response = self._text_client.embeddings.create(
                        model=self.text_model,
                        input=batch
                    )
                    batch_emb = [item.embedding for item in response.data]
                    embeddings.extend(batch_emb)
                except Exception as e:
                    print(f"[MultimodalEmbedder] OpenAI批量嵌入失败: {e}")
                    embeddings.extend([[]] * len(batch))

        return embeddings
    
    def embed_image(self, image_path: str) -> List[float]:
        """
        生成图像嵌入
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            嵌入向量
        """
        self._init_image_model()
        
        try:
            from PIL import Image
            import torch
            
            # 加载图像
            image = Image.open(image_path).convert("RGB")
            
            # 预处理
            inputs = self._image_processor(
                images=image,
                return_tensors="pt"
            ).to(self._device)
            
            # 生成嵌入
            with torch.no_grad():
                image_features = self._image_model_instance.get_image_features(**inputs)
                # 归一化
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            
            return image_features.cpu().numpy()[0].tolist()
        except Exception as e:
            print(f"[MultimodalEmbedder] 图像嵌入失败 {image_path}: {e}")
            return []
    
    def embed_images(self, image_paths: List[str], batch_size: int = 4) -> List[List[float]]:
        """
        批量生成图像嵌入
        
        Args:
            image_paths: 图像路径列表
            batch_size: 批处理大小
            
        Returns:
            嵌入向量列表
        """
        self._init_image_model()
        
        embeddings = []
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            
            try:
                from PIL import Image
                import torch
                
                # 加载图像
                images = []
                for path in batch_paths:
                    try:
                        img = Image.open(path).convert("RGB")
                        images.append(img)
                    except Exception as e:
                        print(f"[MultimodalEmbedder] 加载图像失败 {path}: {e}")
                        images.append(None)
                
                # 过滤无效图像
                valid_images = [img for img in images if img is not None]
                if not valid_images:
                    embeddings.extend([[]] * len(batch_paths))
                    continue
                
                # 预处理
                inputs = self._image_processor(
                    images=valid_images,
                    return_tensors="pt"
                ).to(self._device)
                
                # 生成嵌入
                with torch.no_grad():
                    image_features = self._image_model_instance.get_image_features(**inputs)
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                
                batch_embeddings = image_features.cpu().numpy().tolist()
                
                # 对齐结果（包含无效图像的位置）
                valid_idx = 0
                for img in images:
                    if img is not None:
                        embeddings.append(batch_embeddings[valid_idx])
                        valid_idx += 1
                    else:
                        embeddings.append([])
                
            except Exception as e:
                print(f"[MultimodalEmbedder] 批量图像嵌入失败: {e}")
                embeddings.extend([[]] * len(batch_paths))
        
        return embeddings
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        计算两个嵌入向量的余弦相似度
        
        Args:
            embedding1: 向量1
            embedding2: 向量2
            
        Returns:
            相似度分数 (0-1)
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # 余弦相似度
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
