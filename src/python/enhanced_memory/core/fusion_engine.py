"""
SSM 双向融合引擎

桥接 ChromaDB（语义记忆）和 graph.jsonl（结构化记忆），
实现双向查询、去重、溯源。

核心桥接字段: task_id
  - ChromaDB metadata.task_id ←→ graph.jsonl TaskRecording.task_id
"""

import json
import os
import re
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class FusedResult:
    """融合后的单一结果"""
    content: str
    confidence: float
    source: str                     # "graph" | "chroma" | "fusion"
    source_detail: str              # 更具体的来源 (WebPage/DataFlow/chroma:manifest:...)
    task_id: str = ""
    graph_entities: List[Dict] = field(default_factory=list)  # 关联的 graph 实体
    chroma_distance: Optional[float] = None
    provenance: str = ""            # 溯源说明


@dataclass
class FusionAnswer:
    """融合引擎的完整回答"""
    query: str
    answer: str
    confidence: float
    results: List[FusedResult]
    graph_count: int
    chroma_count: int
    strategy: str                   # "graph_only" | "chroma_only" | "bidirectional"
    query_time_ms: float


class SSMFusionEngine:
    """
    双向融合引擎

    三种查询策略:
    1. graph_only   — 关键词明确，一行精确查询出答案
    2. chroma_graph — ChromaDB 搜 → task_id 回溯 graph 验证 + 补充
    3. bidirectional — 两边同时查 → task_id 去重 → 交叉补全 → 溯源
    """

    EXACT_KEYWORD_THRESHOLD = 0.5    # keyword 密度 > 此值 → graph_only
    CHROMA_CONFIDENCE_BOOST = 0.15   # graph 验证通过后的置信度提升

    ENTITY_LABELS = {
        "FunctionalModule": "功能模块 模块 功能",
        "DataFlow": "数据流 API 接口 端点 endpoint",
        "WebPage": "页面 网页 page",
        "Navigation": "导航 跳转 路由",
        "DataEntity": "数据实体 实体 业务对象",
        "DesignSystem": "设计系统 设计 颜色 字体 品牌色 品牌 样式 style",
        "UserPath": "用户路径 操作路径 流程",
        "InteractionPattern": "交互模式 交互 pattern",
        "TaskRecording": "录制 任务 task 录制记录",
        "JSError": "错误 报错 JS错误 异常 error 故障",
        "DOMSnapshot": "DOM快照 快照 DOM",
    }

    def __init__(self, graph_path: str = None):
        self.graph_path = graph_path or os.path.expanduser(
            "~/.openclaw/workspace/memory/ontology/graph.jsonl"
        )
        self._entities: Optional[List[Dict]] = None
        self._by_type: Optional[Dict[str, List[Dict]]] = None
        self._id_index: Optional[Dict[str, Dict]] = None

    def _load_graph(self):
        """延迟加载 graph.jsonl 到内存索引（应用 update 记录）"""
        if self._entities is not None:
            return

        self._entities = []
        self._by_type = {}
        self._id_index = {}
        _entity_map = {}

        if not os.path.exists(self.graph_path):
            return

        with open(self.graph_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue

                op = record.get("op")
                if op == "create":
                    e = record.get("entity", record)
                elif op == "update":
                    eid = record.get("id")
                    if eid and eid in _entity_map:
                        _entity_map[eid]["properties"].update(record.get("properties", {}))
                    continue
                elif op == "delete":
                    eid = record.get("id")
                    _entity_map.pop(eid, None)
                    continue
                else:
                    e = record

                etype = e.get("type", "")
                if etype == "Relation":
                    continue

                eid = e.get("id", "")
                if eid:
                    _entity_map[eid] = e

        self._entities = list(_entity_map.values())
        for e in self._entities:
            etype = e.get("type", "")
            self._by_type.setdefault(etype, []).append(e)
            eid = e.get("id", "")
            if eid:
                self._id_index[eid] = e

    # ==================== 策略路由 ====================

    def _classify_query(self, question: str) -> str:
        """判断问题类型，决定融合策略"""
        chinese = set(re.findall(r'[\u4e00-\u9fa5]{2,}', question))
        english = set(re.findall(r'[a-zA-Z]{2,}', question.lower()))

        self._load_graph()

        exact_hits = 0
        total_keywords = len(chinese) + len(english)
        if total_keywords == 0:
            return "bidirectional"

        for entity_list in self._by_type.values():
            for e in entity_list:
                etype = e.get("type", "")
                props = e.get("properties", {})
                if not props:
                    continue
                searchable = str(props.get("name", "")) + " " + \
                             str(props.get("purpose", "")) + " " + \
                             str(props.get("api", "")) + " " + \
                             str(props.get("url", "")) + " " + \
                             str(props.get("renders_to", "")) + " " + etype + " " + \
                             self.ENTITY_LABELS.get(etype, "")
                searchable_lower = searchable.lower()

                for kw in chinese:
                    if kw in searchable:
                        exact_hits += 1
                        break
                    found = any(sk in searchable for sk in
                                [kw[i:i+2] for i in range(len(kw)-1)] if len(sk) >= 2)
                    if found:
                        exact_hits += 0.5
                        break

                for kw in english:
                    if kw in searchable_lower:
                        exact_hits += 1
                        break

        keyword_density = exact_hits / total_keywords if total_keywords > 0 else 0

        if keyword_density > self.EXACT_KEYWORD_THRESHOLD:
            return "graph_only"
        elif keyword_density > 0.15:
            return "bidirectional"
        else:
            return "chroma_graph"

    # ==================== Graph 精确查询 ====================

    def query_graph(self, entity_type: str = None,
                    keyword: str = None,
                    filters: Dict[str, str] = None) -> List[Dict]:
        """从 graph.jsonl 精确查询实体"""
        self._load_graph()

        results = []

        for e in self._entities:
            if entity_type and e.get("type") != entity_type:
                continue
            props = e.get("properties", {})
            if not props:
                continue

            if keyword:
                searchable = json.dumps(props, ensure_ascii=False).lower()
                if keyword.lower() not in searchable:
                    continue

            if filters:
                match = True
                for k, v in filters.items():
                    if str(props.get(k, "")).lower() != str(v).lower():
                        match = False
                        break
                if not match:
                    continue

            results.append(e)

        return results

    def query_graph_by_task_id(self, task_id: str,
                               entity_types: List[str] = None) -> Dict[str, List[Dict]]:
        """通过 task_id 回溯 graph 中关联的所有实体"""
        self._load_graph()

        # 1. 找到 TaskRecording
        task_recording = None
        for e in self._by_type.get("TaskRecording", []):
            if e.get("properties", {}).get("task_id") == task_id:
                task_recording = e
                break
        if not task_recording:
            return {}

        task_entity_id = task_recording["id"]

        # 2. 找到所有关系 (Relation: from → to)
        related_ids = set()
        for e in self._by_type.get("Relation", []):
            rprops = e.get("properties", {})
            if rprops.get("from") == task_entity_id and rprops.get("type") == "recorded":
                related_ids.add(rprops.get("to"))

        # 3. 收集关联实体
        result = {}
        for eid in related_ids:
            entity = self._id_index.get(eid)
            if not entity:
                continue
            etype = entity.get("type", "")
            if entity_types and etype not in entity_types:
                continue
            result.setdefault(etype, []).append(entity)

        # 4. 也通过 Relations 找到 System 关联的 Module/DataFlow 等
        for e in self._by_type.get("Relation", []):
            rprops = e.get("properties", {})
            rtype = rprops.get("type", "")
            # relation from System or TaskRecording to FunctionModule/DataFlow/etc
            if rtype.startswith("has_"):
                to_id = rprops.get("to", "")
                to_entity = self._id_index.get(to_id)
                if to_entity:
                    src_task = to_entity.get("properties", {}).get("source_task", "")
                    if src_task == task_id or src_task == task_recording.get("properties", {}).get("task_id", ""):
                        etype = to_entity.get("type", "")
                        if entity_types and etype not in entity_types:
                            continue
                        result.setdefault(etype, []).append(to_entity)

        return result

    # ==================== 双向融合查询 ====================

    def query(self,
              question: str,
              chroma_store=None,
              embedder=None,
              top_k: int = 5) -> FusionAnswer:
        """
        双向融合查询入口

        Args:
            question: 用户问题
            chroma_store: ChromaStorage 实例
            embedder: MultimodalEmbedder 实例
            top_k: 返回结果数

        Returns:
            FusionAnswer
        """
        import time
        start = time.time()

        strategy = self._classify_query(question)
        fused_results = []

        # 提取问题关键词: 完整词 + 2-char tokens (用于中文匹配)
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', question)
        keywords += re.findall(r'[a-zA-Z]{2,}', question.lower())
        # 追加 2-char 子词: "在线客服" → +"在线" +"线客" +"客服"
        extra_tokens = set()
        for kw in keywords:
            for i in range(len(kw) - 1):
                extra_tokens.add(kw[i:i+2])
        keywords = list(set(keywords) | extra_tokens)

        if strategy == "graph_only":
            graph_results = self._graph_exact_search(question, keywords)
            fused_results = self._build_graph_only_results(graph_results, keywords)
            chroma_count = 0
            # reverse expand: graph → ChromaDB 反向扩展补充上下文
            if chroma_store and embedder and fused_results:
                fused_results = self._graph_to_chroma_expand(
                    fused_results, graph_results, chroma_store, embedder, question)
            if not fused_results and chroma_store and embedder:
                strategy = "chroma_graph"
                q_emb = embedder.embed_text(question)
                chroma_results = chroma_store.query(q_emb, n_results=10) if q_emb else []
                fused_results = self._fuse_chroma_to_graph(
                    chroma_results, graph_results, question, keywords)
                chroma_count = len(chroma_results)

        elif strategy == "chroma_graph":
            chroma_results = []
            if chroma_store and embedder:
                q_emb = embedder.embed_text(question)
                if q_emb:
                    chroma_results = chroma_store.query(q_emb, n_results=10)
            graph_results = self._graph_exact_search(question, keywords)
            fused_results = self._fuse_chroma_to_graph(chroma_results, graph_results, question, keywords)
            chroma_count = len(chroma_results)
            # reverse expand for graph-only results embedded in fusion
            if chroma_store and embedder:
                fused_results = self._graph_to_chroma_expand(
                    fused_results, graph_results, chroma_store, embedder, question)

        else:  # bidirectional
            chroma_results = []
            if chroma_store and embedder:
                q_emb = embedder.embed_text(question)
                if q_emb:
                    chroma_results = chroma_store.query(q_emb, n_results=10)
            graph_results = self._graph_exact_search(question, keywords)
            fused_results = self._bidirectional_fuse(chroma_results, graph_results, question, keywords)
            chroma_count = len(chroma_results)
            # reverse expand for graph-only results in bidirectional
            if chroma_store and embedder:
                fused_results = self._graph_to_chroma_expand(
                    fused_results, graph_results, chroma_store, embedder, question)

        # 排序 + top-k
        fused_results.sort(key=lambda x: x.confidence, reverse=True)
        fused_results = fused_results[:top_k]

        answer, confidence = self._synthesize_final_answer(
            question, fused_results, strategy
        )

        query_time = (time.time() - start) * 1000

        return FusionAnswer(
            query=question,
            answer=answer,
            confidence=confidence,
            results=fused_results,
            graph_count=len(self._by_type) if self._by_type else 0,
            chroma_count=chroma_count,
            strategy=strategy,
            query_time_ms=query_time
        )

    # ==================== graph_only 策略 ====================

    def _graph_exact_search(self, question: str,
                            keywords: List[str]) -> Dict[str, List[Dict]]:
        """在 graph 中搜索匹配的实体"""
        self._load_graph()
        results = {}

        for kw in keywords:
            if len(kw) < 2:
                continue

            for etype, entities in self._by_type.items():
                if etype == "Relation":
                    continue
                for e in entities:
                    props = e.get("properties", {})
                    searchable = " ".join(str(v) for v in props.values()) + " " + etype + " " + \
                                 self.ENTITY_LABELS.get(etype, "")
                    if kw in searchable:
                        results.setdefault(etype, []).append(e)

        # 去重
        for etype in results:
            seen = set()
            unique = []
            for e in results[etype]:
                eid = e.get("id", "")
                if eid not in seen:
                    seen.add(eid)
                    unique.append(e)
            results[etype] = unique

        return results

    def _build_graph_only_results(self,
                                   graph_results: Dict[str, List[Dict]],
                                   keywords: List[str] = None) -> List[FusedResult]:
        """从 graph 结果构建 FusedResult 列表，按关键词相关度排序"""
        priority_order = ["FunctionalModule", "DataFlow", "WebPage",
                          "DataEntity", "Navigation", "UserPath",
                          "DesignSystem", "InteractionPattern",
                          "JSError", "TaskRecording"]

        # 计算子词
        all_terms = set(keywords or [])
        for kw in (keywords or []):
            for i in range(len(kw) - 1):
                sub = kw[i:i+2]
                if len(sub) >= 2:
                    all_terms.add(sub)

        scored = []
        for etype in priority_order:
            for e in graph_results.get(etype, []):
                props = e.get("properties", {})
                searchable_full = " ".join(str(v) for v in props.values()) + " " + etype + " " + \
                                  self.ENTITY_LABELS.get(etype, "")
                # 仅 name/url 等关键字段用于精确匹配（权重更高）
                name_field = str(props.get("name", "")) + " " + str(props.get("url", ""))
                score = 0
                for term in all_terms:
                    if len(term) < 2:
                        continue
                    if term in name_field:
                        score += 4  # name/url 精确匹配 → 高权重
                    elif term in searchable_full:
                        score += 1  # purpose 等宽松匹配 → 低权重

                desc = self._describe_entity(etype, props)
                scored.append((score, FusedResult(
                    content=desc,
                    confidence=min(0.95, 0.5 + score * 0.05),
                    source="graph",
                    source_detail=f"graph:{etype}",
                    task_id=props.get("source_task", ""),
                    graph_entities=[e],
                    provenance=f"graph.jsonl → {etype} (关键词命中={score})"
                )))

        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored]

    def _describe_entity(self, etype: str, props: Dict) -> str:
        """将实体属性转为可读描述"""
        if etype == "FunctionalModule":
            pages = props.get("pages", [])
            return (f"功能模块: {props.get('name', '?')} — "
                    f"{props.get('purpose', '')[:80]}"
                    f"{' (页面: ' + ', '.join(pages[:3]) + ')' if pages else ''}")
        elif etype == "DataFlow":
            fields = props.get("data_fields", [])
            return (f"API: {props.get('api', '?')} — "
                    f"用途: {props.get('purpose', '')[:60]}"
                    f"{' (字段: ' + ', '.join(fields[:5]) + ')' if fields else ''}")
        elif etype == "WebPage":
            return (f"页面: {props.get('url', '?')} "
                    f"(节点数: {props.get('node_count', 0)})")
        elif etype == "Navigation":
            return (f"导航: {props.get('from_page', '?')[:40]} "
                    f"→ {props.get('to_page', '?')[:40]}")
        elif etype == "DataEntity":
            fields = props.get("fields", [])
            return (f"数据实体: {props.get('name', '?')} "
                    f"{'(' + ', '.join(fields[:8]) + ')' if fields else ''}")
        elif etype == "DesignSystem":
            return (f"设计系统: 颜色={props.get('colors', [])[:5]}, "
                    f"字体={props.get('fonts', [])[:3]}")
        elif etype == "UserPath":
            steps = props.get("steps", [])
            return f"用户路径: {props.get('name', '?')} ({len(steps)} 步)"
        elif etype == "JSError":
            return (f"JS错误: {props.get('type', '?')} — "
                    f"{str(props.get('message', ''))[:100]}  "
                    f"(页面: {str(props.get('page_url', props.get('url', '')))[:50]})")
        else:
            name = props.get("name", "") or props.get("url", "") or props.get("title", "")
            return f"{etype}: {str(name)[:80]}"

    # ==================== ChromaDB → graph 验证 ====================

    def _fuse_chroma_to_graph(self,
                               chroma_results: List[Dict],
                               graph_results: Dict[str, List[Dict]],
                               question: str,
                               keywords: List[str] = None) -> List[FusedResult]:
        """ChromaDB 搜 → graph 按 task_id 回溯验证 + 补充信息"""
        fused = []

        # 先添加 graph 的直接命中结果
        fused.extend(self._build_graph_only_results(graph_results, keywords))

        # 对每个 ChromaDB 结果，通过 task_id 桥接到 graph
        task_keys = set()
        for cr in chroma_results:
            meta = cr.get("metadata", {})
            tid = meta.get("task_id", "")
            if not tid:
                continue
            task_keys.add(tid)

        # 批量查询所有 task_id 对应的 graph 实体
        task_graph_cache = {}
        for tid in task_keys:
            task_graph_cache[tid] = self.query_graph_by_task_id(
                tid, entity_types=["WebPage", "DataFlow", "FunctionalModule"]
            )

        for cr in chroma_results:
            meta = cr.get("metadata", {})
            tid = meta.get("task_id", "")
            content = cr.get("content", "") or ""
            distance = cr.get("distance", 1.0)
            chroma_sim = 1.0 - min(distance, 1.0)

            # 从 graph 获取关联实体
            related = task_graph_cache.get(tid, {})
            graph_entities = []
            for elist in related.values():
                graph_entities.extend(elist)

            # 计算 graph 验证分
            keywords = self._extract_keywords(question)
            graph_match_score = self._keyword_match_score(
                related, keywords
            )

            if graph_entities:
                confidence = max(
                    0.6,
                    chroma_sim * 0.4 + graph_match_score * 0.35 + 0.8 * 0.25
                )
                source_detail = f"chroma:verified|graph:{'+'.join(related.keys())}"
                # 用 graph 信息补充内容
                if related:
                    best_type = list(related.keys())[0]
                    if related[best_type]:
                        entity_desc = self._describe_entity(
                            best_type, related[best_type][0].get("properties", {})
                        )
                        content = f"[ChromaDB: {content[:80]}...] + [Graph: {entity_desc}]"
            else:
                confidence = chroma_sim * 0.7 + 0.5 * 0.3
                source_detail = "chroma:unverified"

            # 去重: 如果已有一条内容相似的结果 (content 重叠 > 50%)，跳过
            is_dup = False
            for existing in fused:
                overlap = self._content_overlap(content, existing.content)
                if overlap > 0.5:
                    if confidence > existing.confidence:
                        existing.confidence = confidence
                    is_dup = True
                    break
            if is_dup:
                continue

            fused.append(FusedResult(
                content=content,
                confidence=min(confidence, 1.0),
                source="fusion",
                source_detail=source_detail,
                task_id=tid,
                graph_entities=graph_entities,
                chroma_distance=distance,
                provenance=f"ChromaDB (dist={distance:.3f}) → graph:{'+'.join(related.keys())}"
            ))

        return fused

    # ==================== graph → ChromaDB 反向扩展 ====================

    def _graph_to_chroma_expand(self,
                                 fused_results: List[FusedResult],
                                 graph_results: Dict[str, List[Dict]],
                                 chroma_store,
                                 embedder,
                                 question: str) -> List[FusedResult]:
        """graph 结果 → ChromaDB 反向扩展：为纯 graph 结果补充语义上下文"""
        for fr in fused_results:
            if fr.source != "graph":
                continue
            if not fr.graph_entities:
                continue

            # 收集 graph 实体的 task_id
            task_ids = set()
            for e in fr.graph_entities:
                tid = e.get("properties", {}).get("source_task", "")
                if tid:
                    task_ids.add(tid)

            if not task_ids:
                continue

            # 用 graph 实体的关键信息作为查询词去 ChromaDB 搜索
            search_text = fr.content
            if not search_text or len(search_text) < 10:
                continue

            try:
                q_emb = embedder.embed_text(search_text[:200])
                if not q_emb:
                    continue
                chroma_hits = chroma_store.query(q_emb, n_results=3)
            except Exception:
                continue

            # 只保留匹配 task_id 的 chroma 结果
            matched_chroma = [c for c in chroma_hits
                              if c.get("metadata", {}).get("task_id") in task_ids]
            if not matched_chroma:
                continue

            best_chroma = matched_chroma[0]
            chroma_dist = best_chroma.get("distance", 1.0)
            chroma_sim = 1.0 - min(chroma_dist, 1.0)

            fr.chroma_distance = chroma_dist
            fr.source_detail = f"graph:{fr.source_detail.split(':',1)[-1]}|chroma:expanded(d={chroma_dist:.3f})"
            fr.confidence = min(1.0, fr.confidence + chroma_sim * 0.05)
            fr.provenance += f" ← ChromaDB 反向验证 (sim={chroma_sim:.2f})"

        return fused_results

    # ==================== 双向融合（增强版） ====================

    def _bidirectional_fuse(self,
                            chroma_results: List[Dict],
                            graph_results: Dict[str, List[Dict]],
                            question: str,
                            keywords: List[str] = None) -> List[FusedResult]:
        """两边同时查 → task_id 去重 → 交叉补全 → 加权评分"""
        # 1. ChromaDB → graph 验证
        fused = self._fuse_chroma_to_graph(chroma_results, graph_results, question, keywords)

        # 2. 对每条 graph 精确结果，尝试交叉补全
        graph_task_ids = set()
        for r in graph_results.values():
            for e in r:
                tid = e.get("properties", {}).get("source_task", "")
                if tid:
                    graph_task_ids.add(tid)

        for fr in fused:
            if fr.source == "graph" and fr.task_id and fr.task_id in graph_task_ids:
                has_chroma_backup = any(
                    cr.get("metadata", {}).get("task_id") == fr.task_id
                    for cr in chroma_results
                )
                if has_chroma_backup:
                    fr.confidence = min(1.0, fr.confidence + 0.05)
                    fr.provenance += " (+ChromaDB交叉验证)"
                else:
                    fr.provenance += " (仅有Graph精确匹配)"

        # 3. 加权评分重排序
        self._apply_fusion_weights(fused, question, graph_results, chroma_results)

        return fused

    def _apply_fusion_weights(self,
                               fused_results: List[FusedResult],
                               question: str,
                               graph_results: Dict[str, List[Dict]],
                               chroma_results: List[Dict]):
        """对融合结果应用加权评分"""
        keywords = self._extract_keywords(question)
        chroma_task_ids = set()
        for cr in chroma_results:
            tid = cr.get("metadata", {}).get("task_id", "")
            if tid:
                chroma_task_ids.add(tid)

        for fr in fused_results:
            base = fr.confidence

            # 来源权重: graph=0.30, fusion=0.28, chroma=0.22
            source_weight = {"graph": 0.30, "fusion": 0.28, "chroma": 0.22}.get(fr.source, 0.20)

            # 关键词命中权重
            keyword_hit = 0.0
            if keywords:
                hits = sum(1 for kw in keywords if kw in fr.content)
                keyword_hit = min(hits / max(len(keywords), 1), 1.0) * 0.20

            # 交叉验证权重：graph 结果有 chroma 背书 → +0.15
            cross_verify = 0.0
            if fr.source == "graph" and fr.task_id and fr.task_id in chroma_task_ids:
                cross_verify = 0.15
            elif fr.source == "fusion":
                cross_verify = 0.10

            # 实体优先级权重
            entity_bonus = 0.0
            for e in fr.graph_entities:
                etype = e.get("type", "")
                if etype in ("FunctionalModule", "DataFlow"):
                    entity_bonus = max(entity_bonus, 0.10)
                elif etype in ("WebPage", "DataEntity"):
                    entity_bonus = max(entity_bonus, 0.05)

            fr.confidence = min(0.98, base + source_weight + keyword_hit + cross_verify + entity_bonus)
            fr.provenance += f" [权重: src={source_weight:.2f} kw={keyword_hit:.2f} xv={cross_verify:.2f} ent={entity_bonus:.2f}]"

    # ==================== 辅助方法 ====================

    def _keyword_match_score(self, related: Dict[str, List[Dict]],
                             keywords: List[str]) -> float:
        """计算 keywords 在 graph 关联实体中的命中率"""
        if not keywords or not related:
            return 0.0

        matched = 0
        for elist in related.values():
            for e in elist:
                props = e.get("properties", {})
                searchable = " ".join(str(v) for v in props.values()).lower()
                for kw in keywords:
                    if kw.lower() in searchable:
                        matched += 1
                        break

        return min(matched / len(keywords), 1.0)

    def _content_overlap(self, text1: str, text2: str) -> float:
        """计算两个文本的重叠比例"""
        if not text1 or not text2:
            return 0.0
        words1 = set(self._extract_keywords(text1))
        words2 = set(self._extract_keywords(text2))
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        return len(intersection) / min(len(words1), len(words2))

    def _extract_keywords(self, text: str) -> List[str]:
        return re.findall(r'[\u4e00-\u9fa5]{2,}', text) + \
               re.findall(r'[a-zA-Z]{3,}', text.lower())

    def _synthesize_final_answer(self, question: str,
                                  results: List[FusedResult],
                                  strategy: str) -> Tuple[str, float]:
        """综合生成最终回答"""
        if not results:
            return "未找到相关信息", 0.0

        lines = []
        total_conf = 0.0
        graph_sources = 0
        chroma_sources = 0

        for i, r in enumerate(results[:5]):
            src_label = {
                "graph": "📊 精确",
                "fusion": "🔗 融合",
                "chroma": "🔍 语义"
            }.get(r.source, r.source)
            lines.append(f"[{i+1}] {src_label} (置信度: {r.confidence:.2f})\n"
                         f"    {r.content[:180]}")
            total_conf += r.confidence
            if r.source == "graph":
                graph_sources += 1
            else:
                chroma_sources += 1

        avg_conf = total_conf / len(results[:5])
        strategy_label = {
            "graph_only": "精确查询",
            "chroma_graph": "语义搜索 + 图谱验证",
            "bidirectional": "双向融合"
        }.get(strategy, strategy)

        answer = (
            f"策略: {strategy_label}\n"
            f"置信度: {avg_conf:.2f} | "
            f"来源: {graph_sources} 精确 + {chroma_sources} 语义/融合\n"
            f"\n{chr(10).join(lines)}"
        )

        return answer, avg_conf

    def get_stats(self) -> Dict:
        self._load_graph()
        return {
            "graph_entities": len(self._entities),
            "graph_types": len(self._by_type),
            "type_breakdown": {t: len(v) for t, v in self._by_type.items()}
        }
