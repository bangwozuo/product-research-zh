# -*- coding: utf-8 -*-
"""
关键词机会评分 —— 确定性脚本：维度归一 + 加权总分 + 分层 + 产物落盘。

职责边界：
  本脚本只做**确定性计算**：解析关键词记录（搜索量 / 竞争度）、按声明的维度
  公式与权重计算维度分与总分、按阈值分层并落盘。口径解释与建议文案由模型
  按 prompt.txt 完成。

输入（examples/input.json 或 --input）：
  records    : 关键词记录文本（[n] 关键词 搜索量X/周 竞争度Y）
  dimensions : 维度与权重（缺省：维度A=min(100,搜索量/700) 权重0.6；
               维度B=100-竞争度 权重0.4）
  thresholds : 分层阈值（缺省：≥60 A层；45～60 B层；<45 C层）

用法：
  python keyword-opportunity-score.py --input input.json --outdir out
  python keyword-opportunity-score.py --demo

产物（out/）：
  score_detail.csv   评分明细
  score_summary.json 机器可读结果（含分层汇总）
  score_report.md    评分报告（Markdown 表格）
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

RE_RECORD = re.compile(
    r"\[(\d+)\]\s*([^\s：:，,；;]+)\s*搜索量([\d,]+)/周\s*竞争度(\d+)")


def parse_weights(dimensions: str) -> tuple:
    """从 dimensions 文本解析权重，缺省 (0.6, 0.4)。"""
    ws = re.findall(r"权重\s*(0\.\d+)", dimensions or "")
    if len(ws) >= 2:
        w_a = float(ws[0])
        if w_a <= 1.0 and sum(float(x) for x in ws[:2]) <= 1.0001:
            return w_a, round(1.0 - w_a, 4)
    return 0.6, 0.4


def parse_thresholds(thresholds: str) -> tuple:
    """解析 A/C 层阈值，缺省 (60.0, 45.0)。"""
    t = thresholds or ""
    m = re.search(r"[≥>]=?\s*(\d+(?:\.\d+)?)\s*为\s*A", t)
    a = float(m.group(1)) if m else 60.0
    m = re.search(r"<\s*(\d+(?:\.\d+)?)\s*为\s*C", t)
    c = float(m.group(1)) if m else 45.0
    return a, c


def layer_of(total: float, a_th: float, c_th: float) -> str:
    if total >= a_th:
        return "A层"
    if total >= c_th:
        return "B层"
    return "C层"


def score(records: str, dimensions: str, thresholds: str) -> dict:
    if not records:
        print("[错误] records 为空：不猜测数据，请提供关键词记录。", file=sys.stderr)
        sys.exit(3)
    w_a, w_b = parse_weights(dimensions)
    a_th, c_th = parse_thresholds(thresholds)
    rows = []
    for m in RE_RECORD.finditer(records):
        no, kw = m.group(1), m.group(2)
        vol = int(m.group(3).replace(",", ""))
        comp = int(m.group(4))
        d_a = round(min(100.0, vol / 700.0), 1)      # 搜索热度分：线性归一，封顶 100
        d_b = round(100.0 - comp, 1)                  # 低竞争分
        total = round(d_a * w_a + d_b * w_b, 1)
        rows.append({
            "#": no, "对象": kw, "搜索量/周": vol, "竞争度": comp,
            "维度A": d_a, "维度B": d_b, "总分": total,
            "分层": layer_of(total, a_th, c_th),
        })
    rows.sort(key=lambda r: -r["总分"])
    for i, r in enumerate(rows, 1):
        r["#"] = str(i)

    segs = {}
    for r in rows:
        segs.setdefault(r["分层"], []).append(r)
    seg_rows = []
    for name, a_label in (("A层", f"A层（≥{a_th:g}）"), ("B层", f"B层（{c_th:g}~{a_th:g}）"),
                          ("C层", f"C层（<{c_th:g}）")):
        lst = segs.get(name, [])
        seg_rows.append({
            "层级": a_label, "数量": len(lst),
            "占比": f"{len(lst) * 100 / len(rows):.1f}%" if rows else "0%",
            "关键词": "、".join(r["对象"] for r in lst) or "无",
        })
    stats = {
        "记录数": len(rows),
        "权重": {"维度A": w_a, "维度B": w_b},
        "阈值": {"A层下限": a_th, "C层上限": c_th},
        "A层数": len(segs.get("A层", [])),
        "B层数": len(segs.get("B层", [])),
        "C层数": len(segs.get("C层", [])),
        "最高分": rows[0]["对象"] if rows else "",
        "最高分值": rows[0]["总分"] if rows else None,
    }
    return {"scores": rows, "segments": seg_rows, "stats": stats}


def write_outputs(result: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    rows, segs, stats = result["scores"], result["segments"], result["stats"]

    p = os.path.join(outdir, "score_detail.csv")
    cols = ["#", "对象", "搜索量/周", "竞争度", "维度A", "维度B", "总分", "分层"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    files.append(p)

    p = os.path.join(outdir, "score_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "scores": rows, "segments": segs,
                   "note": "评分与分层由本脚本计算；口径假设与建议由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 评分明细", "",
        "| # | 对象 | 维度A | 维度B | 总分 | 分层 |", "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['#']} | {r['对象']} | {r['维度A']} | {r['维度B']} | "
                     f"{r['总分']} | {r['分层']} |")
    lines += [
        "", f"计算口径：总分 = 维度A×{stats['权重']['维度A']} + 维度B×{stats['权重']['维度B']}；"
            f"维度A = min(100, 搜索量/700)，维度B = 100 - 竞争度。", "",
        "## 分层汇总", "",
        "| 层级 | 数量 | 占比 | 关键词 |", "|---|---|---|---|",
    ]
    for s in segs:
        lines.append(f"| {s['层级']} | {s['数量']} | {s['占比']} | {s['关键词']} |")
    lines += [
        "", "（口径假设与逐层建议由模型按 prompt.txt 在本表基础上撰写）",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用", "",
    ]
    p = os.path.join(outdir, "score_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="关键词机会评分（加权评分 + 分层）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)

    result = score(cur.get("records", ""), cur.get("dimensions", ""),
                   cur.get("thresholds", ""))
    files = write_outputs(result, a.outdir)
    s = result["stats"]
    print(f"记录 {s['记录数']} 条｜A层 {s['A层数']} / B层 {s['B层数']} / C层 {s['C层数']}"
          f"｜最高 {s['最高分']} {s['最高分值']} 分")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
