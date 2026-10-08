# -*- coding: utf-8 -*-
"""
蓝海关键词挖掘工作流 —— 确定性编排脚本。

步骤链路（与 SKILL.md 步骤明细一致，每步读上一步产物）：
  S1 关键词机会评分（de_ecom_06_sk03）：维度归一 + 加权总分 + A/B/C 分层；
  S2 蓝海挖掘（本流脚本节点）：对 S1 产物按「竞争度 < 40 且总分 ≥ 45」标
     「蓝海候选」，输出 TOP3 与逐条挖掘建议依据。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物（out/）：
  flow_scores.csv     S1 评分明细（含蓝海标记）
  flow_result.json    全链路机器可读结果
  flow_report.md      工作流报告（Markdown 表格）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WF_DIR = os.path.dirname(HERE)
DEFAULT_INPUT = os.path.join(WF_DIR, "examples", "input.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RE_RECORD = re.compile(
    r"(?:\[\d+\]\s*)?([^\s：:，,；;]+?)\s*搜索量([\d,]+)/周\s*竞争度(\d+)")


def s1_score(records: str) -> list:
    """S1 关键词机会评分（口径与原子技能脚本一致：0.6/0.4，阈值 60/45）。"""
    rows = []
    for m in RE_RECORD.finditer(records):
        kw = m.group(1)
        vol = int(m.group(2).replace(",", ""))
        comp = int(m.group(3))
        d_a = round(min(100.0, vol / 700.0), 1)
        d_b = round(100.0 - comp, 1)
        total = round(d_a * 0.6 + d_b * 0.4, 1)
        layer = "A层" if total >= 60.0 else ("B层" if total >= 45.0 else "C层")
        rows.append({"对象": kw, "搜索量/周": vol, "竞争度": comp,
                     "维度A": d_a, "维度B": d_b, "总分": total, "分层": layer})
    rows.sort(key=lambda r: -r["总分"])
    for i, r in enumerate(rows, 1):
        r["#"] = str(i)
    return rows


def s2_mine(rows: list) -> dict:
    """S2 蓝海挖掘：竞争度 < 40 且总分 ≥ 45 → 蓝海候选。"""
    for r in rows:
        r["蓝海标记"] = "蓝海候选" if (r["竞争度"] < 40 and r["总分"] >= 45.0) else "—"
    blues = [r for r in rows if r["蓝海标记"] == "蓝海候选"]
    hot = [r for r in rows if r["搜索量/周"] >= 40000]
    stats = {"记录数": len(rows), "蓝海候选数": len(blues),
             "高热词数（搜索量≥40,000/周）": len(hot),
             "TOP1": rows[0]["对象"] if rows else "",
             "TOP1总分": rows[0]["总分"] if rows else None,
             "蓝海均值竞争度": round(sum(r["竞争度"] for r in blues) / len(blues), 1) if blues else None}
    return {"stats": stats, "top3": rows[:3]}


def write_outputs(rows: list, s2: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    p = os.path.join(outdir, "flow_scores.csv")
    cols = ["#", "对象", "搜索量/周", "竞争度", "维度A", "维度B", "总分", "分层", "蓝海标记"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    files.append(p)

    p = os.path.join(outdir, "flow_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"steps": {"S1_关键词机会评分": {"记录数": len(rows),
                                            "口径": "总分=维度A×0.6+维度B×0.4，阈值 60/45"},
                             "S2_蓝海挖掘": s2["stats"]},
                   "scores": rows, "top3": s2["top3"],
                   "note": "数值由本脚本编排计算；解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 执行摘要", "",
        f"S1 完成 {s2['stats']['记录数']} 个关键词评分（口径：维度A×0.6 + 维度B×0.4，"
        f"阈值 60/45）；S2 标记蓝海候选 {s2['stats']['蓝海候选数']} 个"
        f"（竞争度 < 40 且总分 ≥ 45），TOP1 为「{s2['stats']['TOP1']}」"
        f"（{s2['stats']['TOP1总分']} 分）。", "",
        "## 评分明细（含蓝海标记）", "",
        "| # | 对象 | 维度A | 维度B | 总分 | 分层 | 蓝海标记 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['#']} | {r['对象']} | {r['维度A']} | {r['维度B']} | "
                     f"{r['总分']} | {r['分层']} | {r['蓝海标记']} |")
    lines += ["", "## TOP3 与挖掘依据", "",
              "| 排名 | 关键词 | 总分 | 依据 |", "|---|---|---|---|"]
    for i, r in enumerate(s2["top3"], 1):
        lines.append(f"| {i} | {r['对象']} | {r['总分']} | "
                     f"搜索量 {r['搜索量/周']:,}/周，竞争度 {r['竞争度']}（{r['蓝海标记']}） |")
    lines += ["", "## 分步结果", "",
              f"1. 步骤 1（机会评分）：{s2['stats']['记录数']} 条，"
              f"A层 {len([r for r in rows if r['分层'] == 'A层'])} 条",
              f"2. 步骤 2（蓝海挖掘）：蓝海候选 {s2['stats']['蓝海候选数']} 个",
              "", "（蓝海标记 = 竞争度 < 40 且总分 ≥ 45，为声明口径非唯一正解；"
                  "入场决策转「利润测算」与人工确认）",
              "", "---", "AI 生成内容 · 需人工复核后方可对外使用", ""]
    p = os.path.join(outdir, "flow_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="蓝海关键词挖掘工作流（S1 评分 + S2 挖掘）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)
    raw = cur.get("input", "")
    if not raw:
        print("[错误] input 为空：不猜测数据，请提供工作流初始输入。", file=sys.stderr)
        sys.exit(3)

    rows = s1_score(raw)         # S1：机会评分
    if not rows:
        print("[错误] 未能解析出关键词记录（格式：关键词 搜索量X/周 竞争度Y）。",
              file=sys.stderr)
        sys.exit(3)
    s2 = s2_mine(rows)           # S2：蓝海挖掘（读 S1 产物）
    files = write_outputs(rows, s2, a.outdir)
    print(f"S1 记录 {s2['stats']['记录数']} 条｜TOP1 {s2['stats']['TOP1']} "
          f"{s2['stats']['TOP1总分']} 分｜S2 蓝海候选 {s2['stats']['蓝海候选数']} 个")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
