"""
Task 数据提取器
从 Sentinel Browser 录制的 task 中提取文本和图像数据
"""

import json
from typing import List, Dict, Optional, Any
from pathlib import Path


class TaskExtractor:
    """Task 数据提取器"""
    
    def __init__(self):
        self.max_chunk_size = 1000  # 文本块最大长度
        self.chunk_overlap = 200    # 文本块重叠长度
    
    def extract_text_chunks(self, task_path: str) -> List[Dict]:
        """
        从 task 中提取文本块
        
        Args:
            task_path: task 目录路径
            
        Returns:
            文本块列表
        """
        task_path = Path(task_path)
        task_id = task_path.name
        chunks = []
        
        # 1. 提取 manifest 中的事件
        manifest_chunks = self._extract_from_manifest(task_path, task_id)
        chunks.extend(manifest_chunks)
        
        # 2. 提取 API 响应
        api_chunks = self._extract_from_api(task_path, task_id)
        chunks.extend(api_chunks)
        
        # 3. 提取 DOM 快照
        dom_chunks = self._extract_from_dom(task_path, task_id)
        chunks.extend(dom_chunks)
        
        return chunks
    
    def _extract_from_manifest(self, task_path: Path, task_id: str) -> List[Dict]:
        """从 training_manifest.jsonl 提取"""
        chunks = []
        manifest_path = task_path / "training_manifest.jsonl"
        
        if not manifest_path.exists():
            return chunks
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f):
                    if not line.strip():
                        continue
                    
                    try:
                        event = json.loads(line)
                        
                        # 提取关键信息
                        event_type = event.get('type', '')
                        timestamp = event.get('timestamp', '')
                        url = event.get('url', '')
                        
                        # 构建文本描述
                        description = self._describe_event(event)
                        if description:
                            chunks.append({
                                'text': description,
                                'source': f'manifest:{event_type}',
                                'task_id': task_id,
                                'timestamp': timestamp,
                                'url': url,
                                'line_num': line_num
                            })
                        
                        # 提取页面状态信息
                        page_state = event.get('page_state', {})
                        if page_state:
                            state_desc = self._describe_page_state(page_state, url)
                            if state_desc:
                                chunks.append({
                                    'text': state_desc,
                                    'source': 'manifest:page_state',
                                    'task_id': task_id,
                                    'timestamp': timestamp,
                                    'url': url
                                })
                        
                        # 提取网络请求信息
                        network = event.get('network', {})
                        requests = network.get('requests', [])
                        for req in requests[:3]:  # 限制数量
                            req_desc = self._describe_request(req)
                            if req_desc:
                                chunks.append({
                                    'text': req_desc,
                                    'source': 'manifest:network',
                                    'task_id': task_id,
                                    'timestamp': timestamp,
                                    'url': url
                                })
                        
                    except json.JSONDecodeError:
                        continue
                    
                    # 限制处理行数
                    if line_num > 1000:
                        break
                        
        except Exception as e:
            print(f"[TaskExtractor] 读取 manifest 失败: {e}")
        
        return chunks
    
    def _extract_from_api(self, task_path: Path, task_id: str) -> List[Dict]:
        """从 api_responses.json 提取"""
        chunks = []
        api_path = task_path / "network" / "api_responses.json"
        
        if not api_path.exists():
            return chunks
        
        try:
            with open(api_path, 'r', encoding='utf-8') as f:
                api_data = json.load(f)
            
            # 处理 API 响应
            for endpoint, response in api_data.items():
                # 简化 API 描述
                desc = f"API端点: {endpoint}\n"
                
                # 提取关键字段
                if isinstance(response, dict):
                    if 'data' in response:
                        data = response['data']
                        if isinstance(data, list) and data:
                            desc += f"返回数据: 列表，包含 {len(data)} 项\n"
                            if len(data) > 0 and isinstance(data[0], dict):
                                desc += f"字段: {list(data[0].keys())}\n"
                        elif isinstance(data, dict):
                            desc += f"返回字段: {list(data.keys())}\n"
                
                chunks.append({
                    'text': desc,
                    'source': 'api_response',
                    'task_id': task_id,
                    'endpoint': endpoint
                })
                
        except Exception as e:
            print(f"[TaskExtractor] 读取 API 响应失败: {e}")
        
        return chunks
    
    def _extract_from_dom(self, task_path: Path, task_id: str) -> List[Dict]:
        """从 DOM 快照提取"""
        chunks = []
        dom_dir = task_path / "dom"
        
        if not dom_dir.exists():
            return chunks
        
        try:
            # 获取所有 snapshot 文件
            snapshot_files = sorted(dom_dir.glob("snapshot_*.json"))
            
            # 只处理前 20 个 snapshot
            for snapshot_file in snapshot_files[:20]:
                try:
                    with open(snapshot_file, 'r', encoding='utf-8') as f:
                        snapshot = json.load(f)
                    
                    # 提取页面信息
                    url = snapshot.get('url', '')
                    title = snapshot.get('title', '')
                    
                    # 提取 rrweb 事件中的文本
                    rrweb_event = snapshot.get('rrwebEvent', {})
                    if rrweb_event.get('type') == 2:  # Full snapshot
                        node = rrweb_event.get('data', {}).get('node', {})
                        text_content = self._extract_text_from_node(node)
                        
                        if text_content:
                            # 分块
                            sub_chunks = self._chunk_text(text_content)
                            for i, chunk in enumerate(sub_chunks):
                                chunks.append({
                                    'text': f"页面: {title}\nURL: {url}\n内容:\n{chunk}",
                                    'source': f'dom:snapshot',
                                    'task_id': task_id,
                                    'snapshot_file': snapshot_file.name,
                                    'chunk_index': i
                                })
                    
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"[TaskExtractor] 读取 DOM 失败: {e}")
        
        return chunks
    
    def extract_image_chunks(self, task_path: str) -> List[Dict]:
        """
        从 task 中提取图像
        
        Args:
            task_path: task 目录路径
            
        Returns:
            图像块列表
        """
        task_path = Path(task_path)
        task_id = task_path.name
        chunks = []
        
        # 1. 从视频提取关键帧
        video_chunks = self._extract_from_video(task_path, task_id)
        chunks.extend(video_chunks)
        
        # 2. 从 previews 目录提取截图
        preview_chunks = self._extract_from_previews(task_path, task_id)
        chunks.extend(preview_chunks)
        
        return chunks
    
    def _extract_from_video(self, task_path: Path, task_id: str) -> List[Dict]:
        """从视频提取关键帧"""
        chunks = []
        video_dir = task_path / "video"
        
        if not video_dir.exists():
            return chunks
        
        # 查找视频文件
        video_files = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.webm"))
        
        for video_file in video_files:
            # 检查是否已有提取的关键帧
            keyframes_dir = video_dir / "keyframes"
            if keyframes_dir.exists():
                # 使用已有的关键帧
                for img_file in sorted(keyframes_dir.glob("*.jpg"))[:20]:
                    chunks.append({
                        'path': str(img_file),
                        'source': 'video:keyframe',
                        'task_id': task_id,
                        'video_file': video_file.name,
                        'video_time': img_file.stem.replace('frame_', '')
                    })
            else:
                print(f"[TaskExtractor] 未找到关键帧，跳过视频文件: {video_file}")
        
        return chunks
    
    def _extract_from_previews(self, task_path: Path, task_id: str) -> List[Dict]:
        """从 previews 目录提取"""
        chunks = []
        previews_dir = task_path / "previews"
        
        if not previews_dir.exists():
            return chunks
        
        # 查找截图
        snapshots_dir = previews_dir / "snapshots"
        if snapshots_dir.exists():
            for img_file in sorted(snapshots_dir.glob("*.png"))[:10]:
                chunks.append({
                    'path': str(img_file),
                    'source': 'preview:snapshot',
                    'task_id': task_id
                })
        
        return chunks
    
    def _describe_event(self, event: Dict) -> str:
        """描述事件"""
        event_type = event.get('type', '')
        url = event.get('url', '')
        title = event.get('title', '')
        
        descriptions = {
            'page-load-start': f"页面开始加载: {url}",
            'page-load-complete': f"页面加载完成: {title} ({url})",
            'click': f"用户点击: {url}",
            'scroll': f"用户滚动页面: {url}",
            'scroll-start': f"用户开始滚动: {url}",
            'input': f"用户输入: {url}",
        }
        
        return descriptions.get(event_type, f"事件: {event_type} at {url}")
    
    def _describe_page_state(self, state: Dict, url: str) -> str:
        """描述页面状态"""
        fingerprint = state.get('fingerprint', {})
        details = fingerprint.get('details', {})
        dom_stats = details.get('dom_stats', {})
        
        desc = f"页面状态 ({url}):\n"
        desc += f"  - 按钮数: {dom_stats.get('buttons', 0)}\n"
        desc += f"  - 链接数: {dom_stats.get('links', 0)}\n"
        desc += f"  - 表单数: {dom_stats.get('forms', 0)}\n"
        desc += f"  - 输入框: {dom_stats.get('inputs', 0)}\n"
        desc += f"  - 图片数: {dom_stats.get('images', 0)}\n"
        desc += f"  - 页面类型: {details.get('page_type', 'unknown')}"
        
        return desc
    
    def _describe_request(self, req: Dict) -> str:
        """描述网络请求"""
        req_type = req.get('type', '')
        method = req.get('method', '')
        url = req.get('url', '')
        status = req.get('status', 0)
        
        return f"{method} {req_type.upper()} 请求: {url} (状态: {status})"
    
    def _extract_text_from_node(self, node: Dict) -> str:
        """从 DOM 节点提取文本"""
        texts = []
        
        def traverse(n):
            if not isinstance(n, dict):
                return
            
            # 提取文本内容
            if n.get('type') == 3:  # Text node
                text = n.get('textContent', '')
                if text and len(text.strip()) > 5:
                    texts.append(text.strip())
            
            # 递归子节点
            for child in n.get('childNodes', []):
                traverse(child)
        
        traverse(node)
        
        # 去重并合并
        unique_texts = list(dict.fromkeys(texts))
        return '\n'.join(unique_texts[:50])  # 限制数量
    
    def _chunk_text(self, text: str) -> List[str]:
        """将长文本分块"""
        if len(text) <= self.max_chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.max_chunk_size
            
            # 寻找合适的分割点
            if end < len(text):
                # 尝试在句子边界分割
                for sep in ['\n\n', '\n', '。', '；', '. ']:
                    pos = text.rfind(sep, start, end)
                    if pos > start + self.max_chunk_size // 2:
                        end = pos + len(sep)
                        break
            
            chunks.append(text[start:end].strip())
            start = end - self.chunk_overlap
        
        return chunks
