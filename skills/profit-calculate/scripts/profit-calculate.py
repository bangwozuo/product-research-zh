# -*- coding: utf-8 -*-
"""
利润测算 —— 确定性脚本：单件成本拆解 + 净利/净利率 + 月度测算 + 敏感性。

职责边界：
  本脚本只做**确定性计算**：解析测算参数（成本项 / 售价 / 月销）与计算规则
  （佣金 / 广告 / 退货等按售价计提的费率），逐项算出单件成本、净利、净利率与
  月净利，并做固定三档敏感性测算。假设说明与建议由模型按 prompt.txt 撰写。

输入（examples/input.json 或 --input）：
  params : 测算参数文本（采购价 / 物流 / 包装 / 售价 / 月销量，单位 元/件、件）
  rules  : 计算规则文本（佣金按售价 X%；广告费按售价 Y%；退货损耗按售价 Z%）

用法：
  python profit-calculate.py --input input.json --outdir out
  python profit-calculate.py --demo

产物（out/）：
  profit_breakdown.csv  测算明细（项目 / 计算式 / 结果 / 说明）
  profit_summary.json   机器可读结果（含敏感性）
  profit_report.md      测算报告（Markdown 表格）
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


def grab(text: str, pat: str, default=None):
    m = re.search(pat, text or "")
    return float(m.group(1).replace(",", "")) if m else default


def parse_params(params: str) -> dict:
    p = {
        "采购价": grab(params, r"出厂采购价([\d.]+)元"),
        "头程物流": grab(params, r"头程物流([\d.]+)元"),
        "尾程快递": grab(params, r"尾程快递([\d.]+)元"),
        "包装耗材": grab(params, r"包装耗材([\d.]+)元"),
        "售价": grab(params, r"售价([\d.]+)元"),
        "月销量": grab(params, r"月销量按?([\d,]+)件", 3000.0),
    }
    missing = [k for k, v in p.items() if v is None]
    if missing:
        print(f"[错误] 参数缺失：{missing}。缺失参数不估算，请补齐后重测。",
              file=sys.stderr)
        sys.exit(3)
    return p


def parse_rules(rules: str) -> dict:
    return {
        "佣金率": grab(rules, r"佣金[按率]?售价的?([\d.]+)%", 5.5) / 100,
        "广告率": grab(rules, r"广告费?[按率]?售价的?([\d.]+)%", 12.0) / 100,
        "退货率": grab(rules, r"退货损耗?[按率]?售价的?([\d.]+)%", 3.0) / 100,
    }


def calc(p: dict, r: dict) -> dict:
    price = p["售价"]
    fulfill = p["采购价"] + p["头程物流"] + p["尾程快递"] + p["包装耗材"]
    commission = price * r["佣金率"]
    ads = price * r["广告率"]
    refund = price * r["退货率"]
    total_cost = fulfill + commission + ads + refund
    net = price - total_cost
    margin = net / price * 100 if price else 0.0
    monthly = net * p["月销量"]

    def alt(ad_rate=None, price_delta=None, refund_rate=None):
        pr = price + (price_delta or 0)
        c = pr * (r["佣金率"])
        a = pr * ((ad_rate if ad_rate is not None else r["广告率"]))
        f = pr * ((refund_rate if refund_rate is not None else r["退货率"]))
        n = pr - (fulfill + c + a + f)
        return n, (n / pr * 100 if pr else 0.0)

    net_ad5, margin_ad5 = alt(ad_rate=r["广告率"] + 0.05)
    net_p5, margin_p5 = alt(price_delta=-5.0)
    net_rf1, margin_rf1 = alt(refund_rate=r["退货率"] + 0.01)
    breakdown = [
        ("售价", "输入参数", f"{price:.2f} 元/件", "计划售价"),
        ("货值成本", "输入参数", f"{p['采购价']:.2f} 元/件", "出厂采购价"),
        ("头程物流", "输入参数", f"{p['头程物流']:.2f} 元/件", "—"),
        ("尾程快递", "输入参数", f"{p['尾程快递']:.2f} 元/件", "—"),
        ("包装耗材", "输入参数", f"{p['包装耗材']:.2f} 元/件", "—"),
        ("履约成本小计", f"{p['采购价']:.2f}+{p['头程物流']:.2f}+{p['尾程快递']:.2f}+{p['包装耗材']:.2f}",
         f"{fulfill:.2f} 元/件", "货值+物流+包装"),
        ("平台佣金", f"{price:.2f} × {r['佣金率']*100:g}%", f"{commission:.2f} 元/件", "按售价计提"),
        ("广告费", f"{price:.2f} × {r['广告率']*100:g}%", f"{ads:.2f} 元/件", "按售价计提"),
        ("退货损耗", f"{price:.2f} × {r['退货率']*100:g}%", f"{refund:.2f} 元/件", "按售价计提"),
        ("单件总成本", f"{fulfill:.2f}+{commission:.2f}+{ads:.2f}+{refund:.2f}",
         f"{total_cost:.2f} 元/件", "履约+按售价计提三项"),
        ("单件净利", f"{price:.2f} - {total_cost:.2f}", f"{net:.2f} 元/件",
         f"净利率 {net:.2f}/{price:.2f} = {margin:.1f}%"),
        ("月净利", f"{net:.2f} × {int(p['月销量']):,} 件", f"{monthly:,.0f} 元/月",
         f"按月销 {int(p['月销量']):,} 件"),
    ]
    result = (f"单件净利 {net:.2f} 元/件，净利率 {margin:.1f}%"
              f"（售价 {price:g} 元/件口径）；按月销 {int(p['月销量']):,} 件测算，"
              f"月净利约 {monthly:,.0f} 元")
    stats = {
        "售价_元件": price, "履约成本_元件": round(fulfill, 2),
        "单件总成本_元件": round(total_cost, 2), "单件净利_元件": round(net, 2),
        "净利率%": round(margin, 1), "月销量_件": int(p["月销量"]),
        "月净利_元": round(monthly, 0),
        "敏感性": {
            "广告占比+5pp": {"单件净利_元件": round(net_ad5, 2),
                          "净利率%": round(margin_ad5, 1)},
            "售价-5元": {"单件净利_元件": round(net_p5, 2),
                      "净利率%": round(margin_p5, 1),
                      "净利变化_元件": round(net_p5 - net, 2)},
            "退货率+1pp": {"单件净利_元件": round(net_rf1, 2),
                        "净利率%": round(margin_rf1, 1)},
        },
        "费率": {k: f"{v*100:g}%" for k, v in r.items()},
    }
    return {"result": result, "breakdown": breakdown, "stats": stats}


def write_outputs(result: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    bd, stats = result["breakdown"], result["stats"]

    p = os.path.join(outdir, "profit_breakdown.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["项目", "计算式", "结果", "说明"])
        w.writerows(bd)
    files.append(p)

    p = os.path.join(outdir, "profit_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"result": result["result"], "stats": stats,
                   "note": "数值由本脚本计算；假设说明与建议由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 结果", "",
        result["result"], "",
        "## 测算明细", "",
        "| 项目 | 计算式 | 结果 | 说明 |", "|---|---|---|---|",
    ]
    for row in bd:
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "", "## 敏感性（脚本口径）", "",
        "| 情景 | 单件净利（元/件） | 净利率 |", "|---|---|---|",
        f"| 基准 | {stats['单件净利_元件']:.2f} | {stats['净利率%']:.1f}% |",
    ]
    for k, v in stats["敏感性"].items():
        lines.append(f"| {k} | {v['单件净利_元件']:.2f} | {v['净利率%']:.1f}% |")
    lines += [
        "", "（假设说明与风险提示由模型按 prompt.txt 在本表基础上撰写）",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用 · 不构成资金决策依据", "",
    ]
    p = os.path.join(outdir, "profit_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="利润测算（成本拆解 + 净利模型 + 敏感性）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)

    p = parse_params(cur.get("params", ""))
    r = parse_rules(cur.get("rules", ""))
    result = calc(p, r)
    files = write_outputs(result, a.outdir)
    s = result["stats"]
    print(f"售价 {s['售价_元件']:g} 元/件｜单件净利 {s['单件净利_元件']:.2f} 元"
          f"（{s['净利率%']:.1f}%）｜月净利约 {s['月净利_元']:,.0f} 元")
    for fp in files:
        print(" 产物:", fp, f"({os.path.getsize(fp) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
