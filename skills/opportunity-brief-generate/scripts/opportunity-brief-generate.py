# -*- coding: utf-8 -*-
"""
机会简报生成 —— 确定性脚本：指标解析 + 环比/pp 变化计算 + 产物落盘。

职责边界：
  本脚本只做**确定性计算**：解析「指标 本期X / 上期Y」格式的周度指标文本、
  计算百分比类指标的 pp 变化与数值类指标的环比变化、按固定规则抽取驱动因素
  并落盘。结论文案与行动建议由模型按 prompt.txt 在脚本数值之上撰写。

输入（examples/input.json 或 --input）：
  metrics : 周度指标文本（指标 本期X / 上期Y；支持 万/%/元/单 单位与备注）
  period  : 报告周期（选填）

用法：
  python opportunity-brief-generate.py --input input.json --outdir out
  python opportunity-brief-generate.py --demo

产物（out/）：
  brief_metrics.csv   关键指标表（本期/上期/变化）
  brief_summary.json  机器可读结果
  brief_report.md     简报底稿（Markdown 表格，模型据此成稿）
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

# 指标模式：名称 本期X / 上期Y（X/Y 可带 万 / % / 元 / 单 / 万元）
RE_METRIC = re.compile(
    r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]*?)\s*"
    r"本期([\d.,]+)(万元|万|%|元|单)?\s*/\s*上期([\d.,]+)(万元|万|%|元|单)?")
RE_NEW_ORDERS = re.compile(r"贡献订单约?([\d,]+)\s*单")


def to_num(s: str, unit: str) -> float:
    v = float(s.replace(",", ""))
    if unit in ("万", "万元"):
        v *= 10000
    return v


def fmt(v: float, unit: str) -> str:
    if unit == "%":
        return f"{v:g}%"
    if unit in ("万", "万元"):
        return f"{v / 10000:g}{unit}"
    if unit == "单":
        return f"{int(v):,}单"
    if unit == "元":
        return f"{v:g}元"
    return f"{v:g}"


def parse(metrics_text: str) -> list:
    rows = []
    for m in RE_METRIC.finditer(metrics_text):
        name, cur_s, cu, prev_s, pu = m.groups()
        if name in ("本期", "对比", "备注"):      # 误切分保护
            continue
        cu = cu or pu or ""
        pu = pu or cu
        cur, prev = to_num(cur_s, cu), to_num(prev_s, pu)
        unit = cu if cu else ""
        if unit == "%":
            change = round(cur - prev, 2)          # 百分比指标：pp 变化
            change_disp = f"{change:+g}pp"
        else:
            pct = (cur - prev) / prev * 100 if prev else 0.0
            change, change_disp = round(pct, 1), f"{pct:+.1f}%"
        rows.append({
            "指标": name, "本期": fmt(cur, unit), "上期": fmt(prev, unit),
            "变化": change_disp, "_unit": unit, "_cur": cur, "_prev": prev,
            "_chg": change,
        })
    return rows


def build(rows: list, metrics_text: str, period: str) -> dict:
    if not rows:
        print("[错误] 未能解析出任何指标：格式应为「指标 本期X / 上期Y」。", file=sys.stderr)
        sys.exit(3)
    stats = {"指标数": len(rows)}
    new_orders = RE_NEW_ORDERS.search(metrics_text)
    if new_orders:
        stats["新品贡献订单"] = int(new_orders.group(1).replace(",", ""))
    # 关键行：GMV/订单优先作为结论锚点
    anchor = next((r for r in rows if "GMV" in r["指标"]), rows[0])
    worst = min((r for r in rows if r["_chg"] < 0), key=lambda r: r["_chg"], default=None)
    best = max((r for r in rows if r["_chg"] > 0), key=lambda r: r["_chg"], default=None)
    stats.update({
        "锚点指标": anchor["指标"], "锚点变化": anchor["变化"],
        "最大正变化": best["指标"] if best else "", "最大正变化值": best["变化"] if best else "",
        "最大负变化": worst["指标"] if worst else "", "最大负变化值": worst["变化"] if worst else "",
        "周期": period,
    })
    return {"metrics": rows, "stats": stats}


def write_outputs(result: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    rows, stats = result["metrics"], result["stats"]

    p = os.path.join(outdir, "brief_metrics.csv")
    cols = ["指标", "本期", "上期", "变化"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    files.append(p)

    p = os.path.join(outdir, "brief_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "metrics": [{k: v for k, v in r.items()
                                                if not k.startswith("_")} for r in rows],
                   "note": "变化值由本脚本计算；结论与建议由模型按 prompt.txt 撰写"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    anchor = stats["锚点指标"]
    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        f"## 核心结论（底稿）", "",
        f"本期（{stats['周期'] or '周期见输入'}）{anchor}变化 {stats['锚点变化']}；"
        f"最大正向变化 {stats['最大正变化']} {stats['最大正变化值']}，"
        f"最大负向变化 {stats['最大负变化']} {stats['最大负变化值']}。"
        f"（成稿时由模型补足驱动解释与行动建议）", "",
        "## 关键指标", "",
        "| 指标 | 本期 | 上期 | 变化 |", "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['指标']} | {r['本期']} | {r['上期']} | {r['变化']} |")
    if "新品贡献订单" in stats:
        lines += ["", f"备注提取：新品贡献订单约 {stats['新品贡献订单']:,} 单。"]
    lines += [
        "", "（驱动因素与行动建议由模型按 prompt.txt 在本表基础上撰写）",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用 · 不构成投资或经营决策依据", "",
    ]
    p = os.path.join(outdir, "brief_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="机会简报生成（指标解析 + 环比/pp 计算）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)

    rows = parse(cur.get("metrics", ""))
    result = build(rows, cur.get("metrics", ""), cur.get("period", ""))
    files = write_outputs(result, a.outdir)
    s = result["stats"]
    print(f"指标 {s['指标数']} 项｜锚点 {s['锚点指标']} {s['锚点变化']}"
          f"｜最大负向 {s['最大负变化']} {s['最大负变化值']}")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
