# -*- coding: utf-8 -*-
"""
选品打分卡工作流 —— 确定性编排脚本。

步骤链路（与 SKILL.md 步骤明细一致，每步读上一步产物）：
  S1 利润测算（de_ecom_06_sk04）：单件成本拆解 + 净利/净利率 + 月净利；
  S2 打分卡生成（本流脚本节点）：按声明映射把净利率折算为利润维度分
     （≥25%→90；20~25%→80；15~20%→70；<15%→60），给出打分卡与结论档位。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物（out/）：
  flow_card.csv       打分卡（维度 / 得分 / 依据）
  flow_result.json    全链路机器可读结果（含利润明细与敏感性）
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

RE_PROD = re.compile(r"「([^」]+)」")


def grab(text: str, pat: str, default=None):
    m = re.search(pat, text or "")
    return float(m.group(1).replace(",", "")) if m else default


def s1_profit(raw: str) -> dict:
    """S1 利润测算（口径与原子技能脚本一致）。"""
    cost = {
        "采购价": grab(raw, r"出厂采购价([\d.]+)元"),
        "头程物流": grab(raw, r"头程物流([\d.]+)元"),
        "尾程快递": grab(raw, r"尾程快递([\d.]+)元"),
        "包装耗材": grab(raw, r"包装耗材([\d.]+)元"),
        "售价": grab(raw, r"售价([\d.]+)元"),
        "月销量": grab(raw, r"月销量按?([\d,]+)件", 3000.0),
    }
    missing = [k for k, v in cost.items() if v is None]
    if missing:
        print(f"[错误] 参数缺失：{missing}。缺失参数不估算，请补齐后重测。",
              file=sys.stderr)
        sys.exit(3)
    rates = {
        "佣金率": grab(raw, r"佣金[按率]?售价的?([\d.]+)%", 5.5) / 100,
        "广告率": grab(raw, r"广告费?[按率]?售价的?([\d.]+)%", 12.0) / 100,
        "退货率": grab(raw, r"退货损耗?[按率]?售价的?([\d.]+)%", 3.0) / 100,
    }
    price = cost["售价"]
    fulfill = cost["采购价"] + cost["头程物流"] + cost["尾程快递"] + cost["包装耗材"]
    commission = price * rates["佣金率"]
    ads = price * rates["广告率"]
    refund = price * rates["退货率"]
    total_cost = fulfill + commission + ads + refund
    net = price - total_cost
    margin = net / price * 100
    monthly = net * cost["月销量"]
    detail = [
        ("履约成本小计", f"{fulfill:.2f} 元/件", "货值+物流+包装"),
        ("平台佣金", f"{commission:.2f} 元/件", f"售价 × {rates['佣金率']*100:g}%"),
        ("广告费", f"{ads:.2f} 元/件", f"售价 × {rates['广告率']*100:g}%"),
        ("退货损耗", f"{refund:.2f} 元/件", f"售价 × {rates['退货率']*100:g}%"),
        ("单件净利", f"{net:.2f} 元/件", f"净利率 {margin:.1f}%"),
        ("月净利", f"{monthly:,.0f} 元/月", f"按月销 {int(cost['月销量']):,} 件"),
    ]
    return {"cost": cost, "rates": rates, "net": net, "margin": margin,
            "monthly": monthly, "detail": detail}


def s2_card(s1: dict, product: str) -> dict:
    """S2 打分卡：净利率 → 利润维度分（声明映射）+ 结论档位。"""
    margin = s1["margin"]
    if margin >= 25.0:
        score, basis = 90, f"净利率 {margin:.1f}% ≥ 25%"
    elif margin >= 20.0:
        score, basis = 80, f"净利率 {margin:.1f}% 在 20%~25%"
    elif margin >= 15.0:
        score, basis = 70, f"净利率 {margin:.1f}% 在 15%~20%"
    else:
        score, basis = 60, f"净利率 {margin:.1f}% < 15%"
    if score >= 80:
        verdict = "建议推进试单（人工确认后执行）"
    elif score >= 60:
        verdict = "谨慎推进：先补齐竞争与供应链维度再决策"
    else:
        verdict = "暂缓：利润维度不达标"
    rows = [
        {"维度": "利润", "得分": score, "权重": "0.5（声明口径）", "依据": basis},
        {"维度": "竞争", "得分": "待补", "权重": "0.3（声明口径）",
         "依据": "本流未覆盖，可转「蓝海关键词挖掘」获取竞争度"},
        {"维度": "供应链", "得分": "待补", "权重": "0.2（声明口径）",
         "依据": "本流未覆盖，需人工补充货源与交期数据"},
    ]
    stats = {"商品": product, "利润维度分": score,
             "单件净利_元件": round(s1["net"], 2), "净利率%": round(margin, 1),
             "月净利_元": round(s1["monthly"]), "结论": verdict,
             "口径": "利润分映射：≥25%→90；20~25%→80；15~20%→70；<15%→60"}
    return {"rows": rows, "stats": stats}


def write_outputs(s1: dict, s2: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    st = s2["stats"]
    p = os.path.join(outdir, "flow_card.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["维度", "得分", "权重", "依据"])
        w.writeheader()
        w.writerows(s2["rows"])
    files.append(p)

    p = os.path.join(outdir, "flow_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"steps": {"S1_利润测算": {"单件净利_元件": st["单件净利_元件"],
                                       "净利率%": st["净利率%"],
                                       "月净利_元": st["月净利_元"]},
                             "S2_打分卡生成": st},
                   "card": s2["rows"], "profit_detail": s1["detail"],
                   "note": "数值由本脚本编排计算；解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 执行摘要", "",
        f"候选品「{st['商品']}」利润维度得分 {st['利润维度分']} 分"
        f"（单件净利 {st['单件净利_元件']:.2f} 元、净利率 {st['净利率%']:.1f}%、"
        f"月净利约 {st['月净利_元']:,} 元），结论：{st['结论']}。", "",
        "## S1 利润测算明细", "",
        "| 项目 | 结果 | 说明 |", "|---|---|---|",
    ]
    for row in s1["detail"]:
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## 选品打分卡", "",
              "| 维度 | 得分 | 权重 | 依据 |", "|---|---|---|---|"]
    for r in s2["rows"]:
        lines.append(f"| {r['维度']} | {r['得分']} | {r['权重']} | {r['依据']} |")
    lines += [
        "", "## 分步结果", "",
        f"1. 步骤 1（利润测算）：单件净利 {st['单件净利_元件']:.2f} 元，"
        f"净利率 {st['净利率%']:.1f}%",
        f"2. 步骤 2（打分卡）：利润维度 {st['利润维度分']} 分，{st['结论']}",
        "", f"打分口径：{st['口径']}；竞争与供应链维度待补，总评以人工确认为准。",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用 · 不构成资金决策依据", "",
    ]
    p = os.path.join(outdir, "flow_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="选品打分卡工作流（S1 利润测算 + S2 打分卡）")
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

    pm = RE_PROD.search(raw)
    product = pm.group(1) if pm else "候选品"
    s1 = s1_profit(raw)                      # S1：利润测算
    s2 = s2_card(s1, product)                # S2：打分卡（读 S1 产物）
    files = write_outputs(s1, s2, a.outdir)
    st = s2["stats"]
    print(f"「{st['商品']}」单件净利 {st['单件净利_元件']:.2f} 元"
          f"（{st['净利率%']:.1f}%）｜利润维度 {st['利润维度分']} 分｜{st['结论']}")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
