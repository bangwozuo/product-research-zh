# -*- coding: utf-8 -*-
"""
类目趋势采集 —— 确定性脚本：结构化 + 阈值筛选 + 产物落盘。

职责边界：
  本脚本只做**确定性计算**：从用户粘贴的原始材料里抽取结构化条目（热词榜 /
  Reddit 热帖 / 抖音话题）、按环比阈值与条数上限筛选、汇总统计并落盘。
  业务解读、机会判断与建议撰写由模型按 prompt.txt 完成。

输入（examples/input.json 或 --input）：
  source : 用户粘贴的原始材料文本
  scope  : 采集范围（时间窗口 / 条数上限 / 环比筛选阈值）

用法：
  python category-trend-collect.py --input input.json --outdir out
  python category-trend-collect.py --demo

产物（out/）：
  collect_items.csv     结构化条目清单
  collect_summary.json  采集统计（机器可读）
  collect_report.md     采集结果报告（Markdown 表格）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DEFAULT_INPUT = os.path.join(SKILL_DIR, "examples", "input.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 解析口径（与 prompt.txt 一致）：
#   热词榜条目：序号) 关键词 周搜索X 环比+Y%
RE_HOTWORD = re.compile(
    r"(\d+)\)\s*([^\s：:，,；;]+)\s*周搜索([\d,]+)\s*环比([+-][\d.]+)%")
# Reddit 热帖：《标题》Xk 赞
RE_REDDIT = re.compile(r"r/([A-Za-z0-9_]+)\s*热帖《([^》]+)》\s*([\d.]+)\s*k?\s*赞")
# 抖音话题：#话题 周播放量环比+Y%
RE_DOUYIN = re.compile(r"#([^\s（(，,；;]+)\s*周播放量环比([+-][\d.]+)%")


def parse_scope(scope: str) -> dict:
    """从 scope 文本解析时间窗口 / 条数上限 / 环比阈值（缺省 19.0 / 8 条）。"""
    out = {"top_n": 8, "min_wow_pct": 19.0, "window": ""}
    if not scope:
        return out
    m = re.search(r"条数上限\s*(\d+)", scope)
    if m:
        out["top_n"] = int(m.group(1))
    m = re.search(r"环比[≥>]=?\+?\s*([\d.]+)\s*%", scope)
    if m:
        out["min_wow_pct"] = float(m.group(1))
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:至|～|~|-)\s*(\d{4}-\d{2}-\d{2})", scope)
    if m:
        out["window"] = f"{m.group(1)} ~ {m.group(2)}"
    return out


def collect(source: str, scope: str) -> dict:
    """结构化抽取 + 阈值筛选，返回 items 与统计。"""
    cfg = parse_scope(scope)
    items = []
    for m in RE_HOTWORD.finditer(source):
        items.append({
            "类型": "类目热词榜",
            "标题/摘要": m.group(2),
            "来源": "平台类目热词榜（用户粘贴）",
            "时间": cfg["window"] or "（以粘贴材料标注为准）",
            "关键信息": f"周搜索 {m.group(3)}，环比 {m.group(4)}%",
            "环比%": float(m.group(4)),
        })
    for m in RE_REDDIT.finditer(source):
        items.append({
            "类型": "海外社区热帖",
            "标题/摘要": f"{m.group(2)}（r/{m.group(1)}）",
            "来源": f"r/{m.group(1)} 热帖（用户粘贴）",
            "时间": "",
            "关键信息": f"{m.group(3)}k 赞",
            "环比%": None,
        })
    for m in RE_DOUYIN.finditer(source):
        items.append({
            "类型": "短视频话题",
            "标题/摘要": f"#{m.group(1)} 话题",
            "来源": "抖音话题榜（用户粘贴）",
            "时间": "",
            "关键信息": f"周播放量环比 {m.group(2)}%",
            "环比%": float(m.group(2)),
        })

    kept, blocked = [], []
    for it in items:
        wow = it["环比%"]
        if wow is None or wow >= cfg["min_wow_pct"]:
            kept.append(it)
        else:
            blocked.append(it)
    kept.sort(key=lambda x: (x["环比%"] if x["环比%"] is not None else -999), reverse=True)
    for i, it in enumerate(kept, 1):
        it["#"] = str(i)
    top = kept[: cfg["top_n"]]
    overflow = kept[cfg["top_n"]:]

    stats = {
        "抓取条目数": len(items),
        "过阈值条目数": len(kept),
        "阈值外拦截数": len(blocked),
        "超额截断数": len(overflow),
        "交付条数": len(top),
        "环比阈值%": cfg["min_wow_pct"],
        "条数上限": cfg["top_n"],
        "时间窗口": cfg["window"],
        "类型分布": {
            t: len([x for x in top if x["类型"] == t])
            for t in sorted({x["类型"] for x in top})
        },
        "峰值条目": (top[0]["标题/摘要"] if top else ""),
        "峰值环比%": (top[0]["环比%"] if top and top[0]["环比%"] is not None else None),
    }
    return {"items": top, "stats": stats,
            "blocked": [{"标题/摘要": b["标题/摘要"], "环比%": b["环比%"]} for b in blocked]}


def write_outputs(result: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    items, stats = result["items"], result["stats"]

    p_csv = os.path.join(outdir, "collect_items.csv")
    cols = ["#", "类型", "标题/摘要", "来源", "时间", "关键信息", "环比%"]
    with open(p_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for it in items:
            w.writerow([it.get(c, "") for c in cols])
    files.append(p_csv)

    p_json = os.path.join(outdir, "collect_summary.json")
    with open(p_json, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "items": items, "blocked": result["blocked"],
                   "note": "数值均由本脚本结构化与筛选；业务解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p_json)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 采集结果", "",
        "| # | 类型 | 标题/摘要 | 来源 | 时间 | 关键信息 |",
        "|---|---|---|---|---|---|",
    ]
    for it in items:
        lines.append(f"| {it['#']} | {it['类型']} | {it['标题/摘要']} | "
                     f"{it['来源']} | {it['时间'] or '—'} | {it['关键信息']} |")
    lines += [
        "", "## 采集统计", "",
        "| 项 | 值 |", "|---|---|",
        f"| 抓取条目 | {stats['抓取条目数']} 条 |",
        f"| 过阈值交付 | {stats['过阈值条目数']} 条（实际交付 {stats['交付条数']} 条，上限 {stats['条数上限']}） |",
        f"| 阈值外拦截 | {stats['阈值外拦截数']} 条（环比 < {stats['环比阈值%']}%） |",
        f"| 峰值条目 | {stats['峰值条目'] or '—'} |",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用", "",
    ]
    p_md = os.path.join(outdir, "collect_report.md")
    with open(p_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p_md)
    return files


def main():
    ap = argparse.ArgumentParser(description="类目趋势采集（结构化 + 阈值筛选）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)
    if not cur.get("source"):
        print("[错误] source 为空：材料缺失不估算，请提供粘贴原文。", file=sys.stderr)
        sys.exit(3)

    result = collect(cur["source"], cur.get("scope", ""))
    files = write_outputs(result, a.outdir)
    s = result["stats"]
    print(f"抓取 {s['抓取条目数']} 条｜过阈值 {s['过阈值条目数']} 条｜"
          f"交付 {s['交付条数']} 条（阈值 {s['环比阈值%']}%，上限 {s['条数上限']} 条）")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
