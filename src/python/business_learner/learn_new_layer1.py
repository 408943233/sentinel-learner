#!/usr/bin/env python3
"""
Business Learner - 三层架构新入口

Layer 1: 工程化页面重建 (rrweb → HTML)
Layer 2: 因果链提取 (manifest lineage → causal graph)
Layer 3: LLM 系统理解 (rerender + causal → system model)
"""

import json, sys, os, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def events_ts_from_filename(stem: str) -> int:
    """从文件名提取时间戳: evt_1779255728809_001_xxx"""
    try:
        parts = stem.split('_')
        if len(parts) >= 2:
            return int(parts[1])
    except Exception:
        pass
    return 0


def run_layer1(task_path: Path, output_dir: Path) -> dict:
    """Layer 1: 工程化页面重建"""
    print_section("Layer 1: 工程化页面重建")

    manifest_path = task_path / 'training_manifest.jsonl'
    if not manifest_path.exists():
        print("  ❌ training_manifest.jsonl 不存在")
        return {'pages': {}}

    lines = manifest_path.read_text(encoding='utf-8').strip().split('\n')
    events = [json.loads(line) for line in lines if line.strip()]

    pages_output = {}
    page_nodes = {}
    assembler = PageAssembler(task_path)

    dom_dir = task_path / 'dom'
    if not dom_dir.exists():
        print("  ❌ dom/ 目录不存在")
        return {'pages': {}}

    # 收集所有 DOM 完整快照（type=2），不依赖 manifest 关联
    snap_files = []
    for fn in dom_dir.iterdir():
        if fn.suffix != '.json':
            continue
        try:
            with open(fn, 'r') as f:
                snap = json.load(f)
        except Exception:
            continue
        rrweb = snap.get('rrwebEvent', {})
        if rrweb.get('type') != 2:
            continue
        node_count = len(rrweb.get('data', {}).get('nodes', []))
        if node_count < 5:
            continue
        snap_ts = snap.get('timestamp', 0) or events_ts_from_filename(fn.stem)
        snap_files.append((snap_ts, fn.name, node_count))

    if not snap_files:
        print("  ❌ 无可用的完整快照 (type=2)")
        return {'pages': {}}

    snap_files.sort()
    print(f"  找到 {len(snap_files)} 个可用快照，从 {len(events)} 个事件中提取 URL")

    # 从所有事件中提取唯一 URL，按时间戳排序
    url_events = []
    seen_urls = set()
    for e in events:
        url = (e.get('url') or e.get('to') or '').strip()
        if not url:
            continue
        if url.startswith('chrome-error://') or url.startswith('about:'):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        url_events.append((e.get('timestamp', 0), url))

    print(f"  提取到 {len(url_events)} 个唯一 URL")

    for url_ts, url in url_events:
        page_name = _make_page_name(url)
        if not page_name or page_name == '/':
            continue
        if page_name in pages_output:
            continue

        # 时间戳最接近的完整快照（10s 窗口）
        best_fn = None
        best_nodes = 0
        best_diff = float('inf')
        for snap_ts, fn, nc in snap_files:
            diff = abs(snap_ts - url_ts)
            if diff < best_diff and diff < 10000:
                best_diff = diff
                best_fn = fn
                best_nodes = nc

        if not best_fn:
            print(f"  ⏭️ {page_name} → 无匹配快照")
            continue

        dom_path = dom_dir / best_fn
        if not dom_path.exists():
            continue

        print(f"  Building: {page_name} ({url[:60]})")
        page_dir = output_dir / 'pages' / page_name
        html_path = assembler.build_page(best_fn, page_dir)

        if html_path and html_path.stat().st_size > 0:
            pages_output[page_name] = str(html_path)
            page_nodes[page_name] = best_nodes
            print(f"    ✅ {html_path.name} ({html_path.stat().st_size/1024:.0f}KB, {best_nodes} nodes)")
        else:
            print(f"    ⚠️ 重建失败")

    summary = {
        'total_pages': len(pages_output),
        'pages': pages_output,
        'page_nodes': page_nodes
    }
    summary_path = output_dir / 'layer1_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n  ✅ Layer 1 完成: {len(pages_output)} 个页面")
    return summary
