# -*- coding: utf-8 -*-
"""
周度机会简报工作流 —— 确定性编排脚本。

步骤链路（与 SKILL.md 步骤明细一致，每步读上一步产物）：
  S1 机会简报生成（de_ecom_06_sk05）：指标解析 + 环比/pp 变化计算；
  S2 简报装配（本流脚本节点）：对 S1 产物按固定规则排 TOP2 机会
     （最大正变化）与风险清单（负变化），组装简报骨架。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物（out/）：
  flow_brief.csv      关键指标表（本期/上期/变化）
  flow_result.json    全链路机器可读结果
  flow_report.md      周度简报骨架（Markdown，模型据此成稿）
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

RE_METRIC = re.compile(
    r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]*?)\s*"
    r"(?:本期)?\s*([\d.,]+)(万元|万|%|元|单)?\s*/\s*(?:上期)?\s*([\d.,]+)(万元|万|%|元|单)?")
RE_NEW_ORDERS = re.compile(r"贡献订单约?([\d,]+)\s*单")
RE_PERIOD = re.compile(r"(\d{4}-\d{2}-\d{2})\s*[～~至]\s*(\d{4}-\d{2}-\d{2})")


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


def s1_metrics(metrics_text: str) -> list:
    """S1 指标解析与变化计算（口径与原子技能脚本一致）。"""
    rows = []
    for m in RE_METRIC.finditer(metrics_text):
        name, cur_s, cu, prev_s, pu = m.groups()
        if name in ("本期", "对比", "备注"):
            continue
        cu = cu or pu or ""
        pu = pu or cu
        cur, prev = to_num(cur_s, cu), to_num(prev_s, pu)
        unit = cu
        if unit == "%":
            chg, disp = round(cur - prev, 2), f"{round(cur - prev, 2):+g}pp"
        else:
            pct = round((cur - prev) / prev * 100, 1) if prev else 0.0
            chg, disp = pct, f"{pct:+.1f}%"
        rows.append({"指标": name, "本期": fmt(cur, unit), "上期": fmt(prev, unit),
                     "变化": disp, "_chg": chg})
    if not rows:
        print("[错误] 未能解析出指标（格式：指标 本期X / 上期Y）。", file=sys.stderr)
        sys.exit(3)
    return rows


def s2_assemble(rows: list, metrics_text: str) -> dict:
    """S2 简报装配：TOP2 机会 + 风险清单 + 锚点结论（逆向指标：升即风险）。"""
    INVERTED = ("退货率", "退款率", "投诉率", "差评率")   # 上升为坏
    def good(r):
        return r["_chg"] < 0 if r["指标"].endswith(INVERTED) else r["_chg"] > 0
    pos = sorted((r for r in rows if good(r)), key=lambda r: -abs(r["_chg"]))
    neg = sorted((r for r in rows if not good(r)), key=lambda r: -abs(r["_chg"]))
    anchor = next((r for r in rows if "GMV" in r["指标"]), rows[0])
    new_m = RE_NEW_ORDERS.search(metrics_text)
    period_m = RE_PERIOD.search(metrics_text)
    stats = {
        "指标数": len(rows),
        "周期": f"{period_m.group(1)} ~ {period_m.group(2)}" if period_m else "",
        "锚点指标": anchor["指标"], "锚点变化": anchor["变化"],
        "TOP机会": [{"指标": r["指标"], "变化": r["变化"]} for r in pos[:2]],
        "风险清单": [{"指标": r["指标"], "变化": r["变化"]} for r in neg],
        "新品贡献订单": int(new_m.group(1).replace(",", "")) if new_m else None,
    }
    return {"stats": stats, "pos": pos, "neg": neg, "anchor": anchor}


def write_outputs(rows: list, s2: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    st = s2["stats"]
    p = os.path.join(outdir, "flow_brief.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["指标", "本期", "上期", "变化"])
        for r in rows:
            w.writerow([r["指标"], r["本期"], r["上期"], r["变化"]])
    files.append(p)

    p = os.path.join(outdir, "flow_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"steps": {"S1_机会简报生成": {"指标数": st["指标数"],
                                          "锚点": f"{st['锚点指标']} {st['锚点变化']}"},
                             "S2_简报装配": {"TOP机会": st["TOP机会"],
                                          "风险清单": st["风险清单"]}},
                   "metrics": [{k: v for k, v in r.items() if not k.startswith("_")}
                               for r in rows],
                   "note": "数值由本脚本编排计算；结论与建议由模型按 prompt.txt 撰写"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 执行摘要", "",
        f"本周（{st['周期'] or '周期见输入'}）{st['锚点指标']} {st['锚点变化']}；"
        f"识别 TOP2 机会与 {len(st['风险清单'])} 项风险，简报骨架如下（成稿由模型完成）。",
        "",
        "## 关键指标", "",
        "| 指标 | 本期 | 上期 | 变化 |", "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['指标']} | {r['本期']} | {r['上期']} | {r['变化']} |")
    lines += ["", "## TOP 机会", ""]
    for i, r in enumerate(s2["pos"][:2], 1):
        lines.append(f"{i}. {r['指标']}（{r['变化']}）")
    if st["新品贡献订单"]:
        lines.append(f"备注：新品贡献订单约 {st['新品贡献订单']:,} 单。")
    lines += ["", "## 风险清单", ""]
    for i, r in enumerate(s2["neg"], 1):
        lines.append(f"{i}. {r['指标']}（{r['变化']}）")
    lines += [
        "", "## 分步结果", "",
        f"1. 步骤 1（指标计算）：{st['指标数']} 项，锚点 {st['锚点指标']} {st['锚点变化']}",
        f"2. 步骤 2（简报装配）：TOP2 机会 + {len(st['风险清单'])} 项风险",
        "", "（驱动解释与行动建议由模型按 prompt.txt 在本骨架上撰写；"
            "每条建议须带量化验收点）",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用 · 不构成投资或经营决策依据", "",
    ]
    p = os.path.join(outdir, "flow_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="周度机会简报工作流（S1 指标计算 + S2 装配）")
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

    rows = s1_metrics(raw)       # S1：指标计算
    s2 = s2_assemble(rows, raw)  # S2：简报装配（读 S1 产物）
    files = write_outputs(rows, s2, a.outdir)
    st = s2["stats"]
    print(f"指标 {st['指标数']} 项｜锚点 {st['锚点指标']} {st['锚点变化']}"
          f"｜TOP机会 {len(st['TOP机会'])}｜风险 {len(st['风险清单'])} 项")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
