#!/usr/bin/env python3
"""
Business Learner - 三层架构新入口

Layer 1: 工程化页面重建 (rrweb → HTML)
Layer 2: 因果链提取 (manifest → causal triples)
Layer 3: LLM 系统理解 (pages + causal → PM 认知)

使用方法:
    python learn.py <task_path>                  # 运行完整三层流水线
    python learn.py <task_path> --layer 1        # 仅运行 Layer 1 (页面重建)
    python learn.py <task_path> --layer 2        # 仅运行 Layer 2 (因果提取)
    python learn.py <task_path> --layer 1,2      # 运行 Layer 1 + 2 (不含 LLM)
    python learn.py <task_path> --no-store       # 运行但不存储到知识图谱
"""

import os
import sys
import json
import re
import hashlib
import logging
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

def _get_commit_hash() -> str:
    """获取当前代码仓库的 commit 版本号"""
    try:
        script_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(script_dir), timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

_APP_VERSION = _get_commit_hash()

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from layer1_reconstruct.page_assembler import PageAssembler
from layer2_causal.causal_extractor import CausalExtractor
from layer3_understand.system_analyzer import SystemAnalyzer


def print_section(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


_skip_log: list = []


def _log_skip(reason: str, detail: str = ""):
    msg = f"  ⏭️ {reason}"
    if detail:
        msg += f": {detail}"
    logger.warning(msg)
    print(msg)
    _skip_log.append(msg)


def _report_skips():
    if _skip_log:
        print_section(f"跳过汇总 ({len(_skip_log)} 项)")
        for entry in _skip_log:
            print(entry)
    else:
        print("\n  ✅ 无跳过项")


def _backup_graph():
    """录制前备份 graph.jsonl，用于快速回滚"""
    graph_path = Path.home() / '.openclaw' / 'workspace' / 'memory' / 'ontology' / 'graph.jsonl'
    if not graph_path.exists():
        return None
    backup = graph_path.with_suffix('.jsonl.bak')
    shutil.copy2(graph_path, backup)
    return backup


def _report_governance(adapter):
    """录制结束后打印治理层汇总"""
    from datetime import datetime
    print_section("治理层汇总")
    graph_path = Path.home() / '.openclaw' / 'workspace' / 'memory' / 'ontology' / 'graph.jsonl'

    # graph 变化
    if graph_path.exists():
        lines = 0
        with open(graph_path) as f:
            for line in f:
                if line.strip():
                    lines += 1
        ents = adapter._load_entity_map_indexed()
        stale = sum(1 for e in ents.values()
                    if e.get('metadata', {}).get('stale') is True)
        type_counts = {}
        for e in ents.values():
            t = e['type']; type_counts[t] = type_counts.get(t, 0) + 1

        print(f"  graph.jsonl: {lines} 行, {len(ents)} 活实体")
        print(f"  stale 标记: {stale} 实体")
        print(f"  版本日志:   {_count_lines(Path.home() / '.openclaw' / 'workspace' / 'memory' / 'ontology' / 'version_log.jsonl')} 条")
        print(f"  实体类型 Top 10:")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {t:25s} x{c}")
    else:
        print(f"  (首次录制, graph.jsonl 尚未生成)")

    # 冲突/去重统计
    fc = getattr(adapter, '_fail_counts', {})
    if fc:
        print(f"  存储失败计数: {dict(fc)}")
    else:
        print(f"  存储失败: 0")

    version_log = Path.home() / '.openclaw' / 'workspace' / 'memory' / 'ontology' / 'version_log.jsonl'
    if version_log.exists():
        print(f"  版本追踪: {_count_lines(version_log)} 条页面版本记录")

    contrib_log = Path.home() / '.openclaw' / 'workspace' / 'memory' / 'ontology' / 'contribution_map.jsonl'
    if contrib_log.exists():
        print(f"  贡献溯源: {_count_lines(contrib_log)} 条 task 贡献记录")

    print(f"\n  💡 日志详情: LOG_LEVEL=DEBUG python learn.py ...")
    print(f"  💡 回滚命令: cp graph.jsonl.bak graph.jsonl  (恢复录制前状态)")


def _count_lines(path):
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _events_ts_from_filename(stem: str) -> int:
    try:
        parts = stem.split('_')
        if len(parts) >= 2:
            return int(parts[1])
    except Exception:
        pass
    return 0


_STATIC_RESOURCE_EXTENSIONS = frozenset({
    '.css', '.js', '.json', '.xml', '.map', '.txt', '.md',
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.mp4', '.webm', '.mp3', '.wav',
})


def _is_static_resource(url: str) -> bool:
    """判断 URL 是否为静态资源（不应作为页面重建）"""
    from urllib.parse import urlparse
    path = urlparse(url).path
    if not path or path == '/':
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in _STATIC_RESOURCE_EXTENSIONS


def _is_page_navigation(event_type: str) -> bool:
    """判断事件类型是否为页面导航（页面边界）"""
    return event_type in ('page-load-start', 'page-load-complete')


def run_layer1(task_path: Path, output_dir: Path) -> dict:
    """Layer 1: 工程化页面重建

    原则:
    - 一个页面 = 一次 page-load 导航事件，只有用户真正导航到的 URL 才重建
    - 静态资源（.css/.js/.png 等）不是页面，仅作为页面内资源引用
    - 每个页面必须有自己独立的 type=2 DOM 快照，绝不复用其他页面的快照
    - 缺少 type=2 快照的页面标记为 unreconstructed，不伪造内容
    """
    print_section("Layer 1: 工程化页面重建")

    manifest_path = task_path / 'training_manifest.jsonl'
    if not manifest_path.exists():
        print("  ❌ training_manifest.jsonl 不存在")
        return {'pages': {}}

    lines = manifest_path.read_text(encoding='utf-8').strip().split('\n')
    events = [json.loads(line) for line in lines if line.strip()]

    pages_output = {}
    page_nodes = {}
    unreconstructed = []
    assembler = PageAssembler(task_path)

    dom_dir = task_path / 'dom'
    if not dom_dir.exists():
        print("  ❌ dom/ 目录不存在")
        return {'pages': {}}

    dom_to_best = {}
    for e in events:
        meta = e.get('metadata') or {}
        df = meta.get('domSnapshotFileName')
        if not df:
            continue
        dp = dom_dir / df
        if not dp.exists():
            continue
        try:
            with open(dp, 'r') as fh:
                snap = json.load(fh)
        except Exception:
            continue
        if not isinstance(snap, dict):
            continue
        rrweb = snap.get('rrwebEvent', {})
        if rrweb.get('type') != 2:
            continue
        nc = len(rrweb.get('data', {}).get('nodes', []))
        if nc < 5:
            continue
        dom_to_best[df] = (rrweb, nc)

    page_events = [e for e in events if _is_page_navigation(e.get('type', ''))]
    page_urls = []
    for e in page_events:
        url = (e.get('url') or e.get('to') or '').strip()
        if not url or url.startswith(('chrome-error://', 'about:')):
            continue
        if _is_static_resource(url):
            continue
        pn = _make_page_name(url)
        if not pn:
            continue
        if any(p[0] == url for p in page_urls):
            continue
        meta = e.get('metadata') or {}
        df = meta.get('domSnapshotFileName', '')
        page_urls.append((url, pn, df, e.get('timestamp', 0)))

    print(f"  识别到 {len(page_urls)} 个页面导航 (从 {len(page_events)} 个 page-load 事件)")

    built = 0
    for url, pn, dom_file, evt_ts in page_urls:
        if pn in pages_output:
            continue

        if dom_file and dom_file in dom_to_best:
            rrweb, nc = dom_to_best[dom_file]
            print(f"  Building: {pn} ({url[:80]})")
            page_dir = output_dir / 'pages' / pn
            html_path = assembler.build_page(dom_file, page_dir)
            if html_path and html_path.stat().st_size > 0:
                pages_output[pn] = str(html_path)
                page_nodes[pn] = nc
                built += 1
                print(f"    ✅ {html_path.name} ({html_path.stat().st_size/1024:.0f}KB, {nc} nodes)")
            else:
                unreconstructed.append((pn, url, "PageAssembler 重建失败"))
        else:
            unreconstructed.append((pn, url, f"无 type=2 完整快照 (dom_file={dom_file or '未关联'})"))

    if unreconstructed:
        print(f"\n  ⚠️ {len(unreconstructed)} 个页面无法重建 (缺少 type=2 DOM 快照):")
        for pn, url, reason in unreconstructed:
            print(f"    - {pn:30s} {reason[:60]}")

    # CSS 去重：提取跨页面公共样式，减少冗余
    common_css = _deduplicate_page_css(pages_output, output_dir)

    summary = {
        'total_pages': len(pages_output),
        'pages': pages_output,
        'page_nodes': page_nodes,
        'unreconstructed': [{'page_name': pn, 'url': url, 'reason': r} for pn, url, r in unreconstructed],
    }
    summary_path = output_dir / 'layer1_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n  ✅ Layer 1 完成: {built} 个页面")
    return summary


def _css_content_hash(css_text: str) -> str:
    return hashlib.md5(css_text.encode('utf-8', errors='ignore')).hexdigest()


def _deduplicate_page_css(pages_output: dict, output_dir: Path) -> str:
    """跨页面 CSS 去重：提取公共样式到共享文件，页面引用之"""
    if len(pages_output) < 2:
        return ''

    page_css_map = {}
    for page_name, html_path_str in pages_output.items():
        html_path = Path(html_path_str)
        if not html_path.exists():
            continue
        content = html_path.read_text(encoding='utf-8')
        style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
        if style_match:
            page_css_map[page_name] = {
                'path': html_path,
                'css': style_match.group(1),
                'hash': _css_content_hash(style_match.group(1))
            }

    if not page_css_map:
        return ''

    css_blocks = {}
    for pn in page_css_map:
        css_text = page_css_map[pn]['css']
        blocks = re.split(r'\n/\*.*?\*/\n', css_text)
        if len(blocks) <= 1:
            blocks = [css_text]
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            bh = _css_content_hash(b)
            if bh not in css_blocks:
                css_blocks[bh] = {'css': b, 'size': len(b), 'pages': []}
            css_blocks[bh]['pages'].append(pn)

    common_css = []
    page_specific = {}
    for pn in page_css_map:
        page_specific[pn] = []

    for bh, info in css_blocks.items():
        if len(info['pages']) >= 2:
            common_css.append(f'/* shared css block (used by {len(info["pages"])} pages, {info["size"]//1024}KB) */\n{info["css"]}')
        else:
            for pn in info['pages']:
                page_specific[pn].append(info['css'])

    if not common_css:
        return ''

    common_dir = output_dir / 'pages' / 'shared'
    common_dir.mkdir(parents=True, exist_ok=True)
    common_css_path = common_dir / 'common.css'
    common_content = '\n\n'.join(common_css)

    total_shared = sum(b['size'] for b in css_blocks.values() if len(b['pages']) >= 2)
    shared_pages = set()
    for b in css_blocks.values():
        if len(b['pages']) >= 2:
            shared_pages.update(b['pages'])
    print(f"\n  🎨 CSS 去重: 提取 {len(common_css)} 个共享块 ({total_shared//1024}KB) → pages/shared/common.css")
    print(f"     覆盖 {len(shared_pages)} 个页面")

    with open(common_css_path, 'w', encoding='utf-8') as f:
        f.write(common_content)

    for pn, info in page_css_map.items():
        full_css = common_content + '\n\n' + '\n\n'.join(page_specific.get(pn, []))
        content = info['path'].read_text(encoding='utf-8')
        start = content.find('<style>')
        end = content.find('</style>', start)
        if start >= 0 and end > start:
            content = content[:start + 7] + '\n' + full_css + '\n' + content[end:]
        else:
            content = content.replace('<style></style>', f'<style>\n{full_css}\n</style>')
        info['path'].write_text(content, encoding='utf-8')
        new_size = info['path'].stat().st_size
        print(f"     {pn}: {new_size//1024}KB")

    return common_content


def _url_base(url: str) -> str:
    """提取 URL 基底（不含 #hash 部分），用于 SPA 路由复用"""
    return url.split('#')[0]


def _url_domain(url: str) -> str:
    """提取 URL 的域名部分"""
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc
    except Exception:
        return ''


def _make_page_name(url: str) -> str:
    """从 URL 生成页面名"""
    from urllib.parse import urlparse
    parsed_url = urlparse(url)
    url_path = parsed_url.path.strip('/')
    url_hash = parsed_url.fragment
    path_parts = url_path.split('/') if url_path else []

    if url_path:
        last_segment = path_parts[-1] if path_parts else 'index'
        if not last_segment or last_segment.endswith('.php') or last_segment.endswith('.aspx') or last_segment.endswith('.jsp'):
            last_segment = 'index'
    else:
        last_segment = 'index'

    base_name = last_segment.rsplit('.', 1)[0] if '.' in last_segment else last_segment
    if not base_name:
        base_name = 'index'
    if base_name.endswith('.html') or base_name.endswith('.htm'):
        base_name = base_name.rsplit('.', 1)[0]

    if url_hash:
        page_name = f"{base_name}_{url_hash.replace('/', '_').replace('?', '_').replace('%', '_')[:60]}"
    elif len(path_parts) > 1 and path_parts[-1] != 'index':
        parent = path_parts[-2] if len(path_parts) >= 2 else ''
        if parent and parent != base_name:
            page_name = f"{parent}/{base_name}"
        else:
            page_name = base_name
    else:
        page_name = base_name

    if not page_name or page_name == '/':
        page_name = 'index'
    return page_name


def run_layer2(task_path: Path, output_dir: Path) -> dict:
    """Layer 2: 因果链提取"""
    print_section("Layer 2: 因果链提取")

    extractor = CausalExtractor(task_path)
    graph = extractor.extract()

    print(f"  事件数: {len(graph.triples)}")
    print(f"  页面数: {len(graph.pages)}")
    print(f"  页面导航: {len(graph.navigations)}")

    # 统计 action 类型
    action_types = {}
    for t in graph.triples:
        tp = t.event_type
        action_types[tp] = action_types.get(tp, 0) + 1
    for tp, count in sorted(action_types.items(), key=lambda x: -x[1]):
        print(f"    {tp}: {count}")

    # 生成动作摘要
    summary = extractor.get_action_summary()

    summary_path = output_dir / 'layer2_causal.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    anchors = extractor.extract_anchor_events()
    alignment_path = output_dir / 'alignment.json'
    with open(alignment_path, 'w', encoding='utf-8') as f:
        json.dump(anchors, f, ensure_ascii=False, indent=2)

    print(f"\n  ✅ Layer 2 完成: {summary_path} (锚点: {anchors.get('total_anchors', 0)} 个)")
    return summary


def run_layer3(pages: dict, causal_graph: dict, output_dir: Path,
               llm_api_key: str = None) -> dict:
    """Layer 3: LLM 系统理解"""
    print_section("Layer 3: LLM 系统理解")

    if not llm_api_key:
        raise SystemExit("❌ Layer 3 需要 LLM_API_KEY 环境变量，请设置后重试")

    analyzer = SystemAnalyzer(llm_api_key=llm_api_key)
    result = analyzer.analyze(
        pages=pages,
        causal_graph=causal_graph,
        output_dir=output_dir
    )

    if result:
        print(f"  ✅ Layer 3 完成: {output_dir / 'system_analysis.json'}")
    else:
        print("  ⚠️ Layer 3 未得到有效结果")

    return result


def main():
    logger.info(f"Sentinel-learner v{_APP_VERSION} starting")
    if len(sys.argv) < 2:
        print("用法: python learn.py <task_path> [--layer 1|2|3|1,2] [--no-store]")
        print("示例: python learn.py /path/to/task_folder")
        sys.exit(1)

    task_path = Path(sys.argv[1])
    if not task_path.exists():
        print(f"错误: 路径不存在: {task_path}")
        sys.exit(1)

    # 解析参数
    layers_to_run = {'1', '2', '3'}
    no_store = False
    for arg in sys.argv[2:]:
        if arg == '--no-store':
            no_store = True
        elif arg.startswith('--layer'):
            val = arg.split('=', 1)[-1] if '=' in arg else (sys.argv[sys.argv.index(arg) + 1] if sys.argv.index(arg) + 1 < len(sys.argv) else '')
            if val:
                layers_to_run = set(val.replace(' ', '').split(','))

    output_dir = task_path / 'analysis'
    output_dir.mkdir(parents=True, exist_ok=True)

    print_section(f"Business Learner - {task_path.name}")

    # LLM API 密钥 (可通过环境变量覆盖)
    llm_api_key = os.environ.get('LLM_API_KEY', '')

    layer1_result = {'pages': {}}
    layer2_result = {}
    layer3_result = {}

    if '1' in layers_to_run:
        layer1_result = run_layer1(task_path, output_dir)

    if '2' in layers_to_run:
        layer2_result = run_layer2(task_path, output_dir)

    if '3' in layers_to_run:
        if not layer1_result.get('pages'):
            layer1_result = run_layer1(task_path, output_dir)
        if not layer2_result:
            layer2_result = run_layer2(task_path, output_dir)

        layer3_result = run_layer3(
            pages=layer1_result.get('pages', {}),
            causal_graph=layer2_result,
            output_dir=output_dir,
            llm_api_key=llm_api_key
        )

    # 存储到知识图谱
    if not no_store:
        _backup_graph()
        store_to_knowledge_pipeline(task_path, output_dir, layer1_result,
                                    layer2_result, layer3_result)

    print_section("完成")
    _report_skips()
    print(f"""
  输出目录: {output_dir}
   - Layer 1: pages/ 目录 (重建的 HTML 页面)
   - Layer 2: layer2_causal.json (因果链)
   - Layer 3: system_analysis.json (系统分析)
""")


def store_to_knowledge_pipeline(task_path: Path, output_dir: Path,
                                layer1_result: dict, layer2_result: dict,
                                layer3_result: dict):
    print_section("存储到知识图谱")

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from business_learner.storage.unified_memory_adapter import UnifiedMemoryAdapter
    from business_learner.utils.task_metadata import TaskMetadataManager, TaskMetadata

    metadata_manager = TaskMetadataManager(str(task_path))

    meta_path = task_path / 'metadata.json'
    if not meta_path.exists():
        task_name = task_path.name
        url = ""
        manifest_path = task_path / 'training_manifest.jsonl'
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                first_event = json.loads(f.readline())
                url = first_event.get('url', '')
    
            domain = url.split('/')[2] if '://' in url else 'unknown'
    
            basic_meta = {
                "task_id": task_name,
                "task_name": task_name.replace(f'_{domain}', '').replace('_', ' '),
                "task_description": f"Task recorded from {domain}",
                "recorder": {
                    "user_id": "anonymous",
                    "operator_name": "",
                    "recorded_at": ""
                },
                "target_system": {
                    "name": "未知系统",
                    "domain": domain,
                    "system_type": "web_application"
                }
            }
    
            # 尝试从 Layer3 结果获取系统名称
            if layer3_result and isinstance(layer3_result, dict):
                system_name = layer3_result.get('system_name', '')
                if system_name:
                    basic_meta['target_system']['name'] = system_name
    
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(basic_meta, f, ensure_ascii=False, indent=2)
    
    adapter = UnifiedMemoryAdapter(mode='local')

    # 强制 task_id 使用完整目录名（metadata.json 里的是缩写）
    metadata = metadata_manager.load_or_create()
    full_task_id = task_path.name
    metadata.task_id = full_task_id
    metadata_manager._metadata = metadata  # 回写

    # 构建简化的 TaskUnderstanding
    from business_learner.utils.models import TaskUnderstanding, PageUnderstanding, PageInfo

    task_id = task_path.name

    pages = []
    if layer1_result and isinstance(layer1_result, dict):
        for page_name, page_path in layer1_result.get('pages', {}).items():
            pages.append(PageUnderstanding(
                overall_confidence=0.9,
                page_info=PageInfo(
                    url=page_name,
                    title=None,
                    page_type="page",
                    business_domain=""
                )
            ))

    task = TaskUnderstanding(
        task_id=task_id,
        business_system=(layer3_result or {}).get('system_name', '未知系统'),
        business_domain='web_application',
        pages=pages,
        processes=[],
        entities=(layer3_result or {}).get('data_entities', [])
    )

    adapter.store_task_knowledge(
        task_result=task,
        metadata_manager=metadata_manager
    )

    # 存储 Layer 3 LLM 分析
    system_analysis_path = output_dir / 'system_analysis.json'
    if system_analysis_path.exists():
        system_name = (layer3_result or {}).get('system_name', '未知系统')
        system_entity = adapter._query_existing_system(system_name)
        if system_entity:
            adapter.store_layer3_analysis(
                task_id=task_id,
                system_id=system_entity["id"],
                analysis_file=str(system_analysis_path)
            )

    # 生成 site model（不依赖 Layer3 成功）
    system_name = (layer3_result or {}).get('system_name', '')
    if not system_name:
        system_name = getattr(metadata.target_system, 'name', '') if metadata and hasattr(metadata, 'target_system') else ''
    if not system_name:
        try:
            sys_entity = adapter._query_existing_system('')
            if sys_entity:
                system_name = sys_entity.get('properties', {}).get('name', '')
        except Exception:
            pass
    if not system_name:
        system_name = task.business_system or '未知系统'
    adapter.save_site_model(system_name)

    # ChromaDB 向量索引
    index_task_to_chromadb(str(task_path))

    # 知识生命周期维护（每次存储后执行）
    _run_memory_maintenance(adapter)

    print("  ✅ 存储完成")

    # 治理层汇总
    _report_governance(adapter)


def index_task_to_chromadb(task_path: str):
    """将 task 的文本和图像索引入 ChromaDB 向量数据库"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from enhanced_memory.core.enhanced_memory_system import EnhancedMemorySystem

        llm_api_key = os.environ.get('LLM_API_KEY', '') or os.environ.get('OPENAI_API_KEY', '')
        if not llm_api_key:
            raise SystemExit("❌ ChromaDB 向量索引需要 LLM_API_KEY 环境变量，请设置后重试")

        memory = EnhancedMemorySystem(
            api_key=llm_api_key,
            collection_name="sentinel_knowledge"
        )
        memory.index_task(task_path)
    except ImportError as e:
        raise SystemExit(f"❌ ChromaDB 模块未就绪: {e}")
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"❌ ChromaDB 索引失败: {e}")


def _run_memory_maintenance(adapter):
    """知识生命周期维护：衰减 + 压缩（非阻塞，静默降级）"""
    from datetime import datetime, timedelta

    try:
        _run_memory_decay(adapter, datetime, timedelta)
    except Exception as e:
        print(f"  ⚠️ 记忆衰减失败: {e}")

    try:
        _run_knowledge_compression(adapter, datetime)
    except Exception as e:
        print(f"  ⚠️ 知识压缩失败: {e}")


def _run_memory_decay(adapter, datetime, timedelta):
    """记忆衰减：降低长时间未查询实体的活跃度"""
    decay_threshold_days = 60
    decay_min_active = 0.1
    tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz)
    threshold = now - timedelta(days=decay_threshold_days)

    entities = adapter._load_all_entities()
    decayed_count = 0

    for entity in entities:
        last_used_str = entity.get("metadata", {}).get("last_used", "")
        if not last_used_str:
            last_used_str = entity.get("created_at", "")
        if not last_used_str:
            continue
        try:
            last_used = datetime.fromisoformat(last_used_str)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=tz)
        except (ValueError, TypeError):
            continue

        if last_used < threshold:
            decay_record = {
                "op": "update",
                "id": entity["id"],
                "properties": {"active": True, "decay_applied": now.isoformat()},
                "metadata": {
                    "source": "sentinel-learner",
                    "authority_level": "observation",
                    "last_used": now.isoformat()
                },
                "timestamp": now.isoformat()
            }
            with open(adapter.graph_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(decay_record, ensure_ascii=False) + '\n')
            decayed_count += 1

    if decayed_count > 0:
        print(f"  ✅ 记忆衰减: {decayed_count} 个实体标记 (>{decay_threshold_days}天未访问)")


def _run_knowledge_compression(adapter, datetime):
    """知识压缩：对同类型同名实体进行合并，减少冗余"""
    entities = adapter._load_all_entities()
    compressible_types = {"JSError", "TaskRecording"}
    compressed = 0

    groups = {}
    for entity in entities:
        etype = entity.get("type", "")
        if etype not in compressible_types:
            continue
        name = entity.get("properties", {}).get("name", "")
        if not name:
            continue
        key = f"{etype}:{name}"
        if key not in groups:
            groups[key] = []
        groups[key].append(entity)

    now = datetime.now().isoformat()
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        keeper = group[0]
        for entity in group[1:]:
            merge_record = {
                "op": "update",
                "id": entity["id"],
                "properties": {
                    "superseded_by": keeper["id"],
                    "active": False,
                    "compressed_at": now
                },
                "timestamp": now,
                "metadata": {
                    "source": "sentinel-learner",
                    "authority_level": "observation"
                }
            }
            with open(adapter.graph_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(merge_record, ensure_ascii=False) + '\n')
            compressed += 1

    if compressed > 0:
        print(f"  ✅ 知识压缩: {compressed} 个冗余实体已合并")


if __name__ == "__main__":
    main()
