# -*- coding: utf-8 -*-
"""
竞品上架与价格监控工作流 —— 确定性编排脚本。

步骤链路（与 SKILL.md 步骤明细一致，每步读上一步产物）：
  S1 竞品动态摘要（de_ecom_06_sk02）：条目结构化 + 五类归类 + 频次统计；
  S2 竞品价格巡检（本流脚本节点）：抽取价格事件（降价 / 回升 / 新品定价 /
     低开），计算变化幅度，跌幅 ≤ -8% 标「预警」，并按商品汇总观测价格带。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物（out/）：
  flow_price_events.csv  价格事件明细（含预警标记）
  flow_clusters.csv      S1 分组结果
  flow_result.json       全链路机器可读结果
  flow_report.md         工作流报告（Markdown 表格）
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

RE_SEG = re.compile(r"\[(\d+)\]\s*([^\[]{3,})")
RE_BODY = re.compile(r"(\d{2}-\d{2})\s*(店铺[A-Za-z0-9]+)\s*(.*)")
RE_PROD = re.compile(r"「([^」]+)」")
PRICE_KEYS = ("到手价", "定价", "预售价", "开售价", "价格回升")
NEW_KEYS = ("上新", "上架", "开售")
PROMO_KEYS = ("满减", "满", "赠品", "直播")
TRAFFIC_KEYS = ("销量榜", "广告位", "排名")
# 价格事件
RE_CUT = re.compile(r"到手价\s*([\d.]+)元\s*[→→-]+\s*([\d.]+)元")
RE_REBOUND = re.compile(r"价格回升至([\d.]+)元")
RE_SET = re.compile(r"(定价|预售价|开售价)\s*([\d.]+)元")
RE_LOWER = re.compile(r"比预售价低([\d.]+)元")


def classify(desc: str) -> str:
    if any(k in desc for k in PRICE_KEYS) and "元" in desc:
        return "价格调整"
    if any(k in desc for k in TRAFFIC_KEYS):
        return "流量投放"
    if any(k in desc for k in NEW_KEYS):
        return "新品上架"
    if any(k in desc for k in PROMO_KEYS):
        return "促销活动"
    return "其他"


def s1_digest(items_text: str) -> dict:
    """S1 竞品动态摘要：结构化 + 归类（口径与原子技能脚本一致）。"""
    rows = []
    for m in RE_SEG.finditer(items_text):
        no, body = m.group(1), m.group(2).strip().rstrip("；;。")
        dm = RE_BODY.match(body)
        if not dm:
            continue
        pm = RE_PROD.search(body)
        rows.append({"编号": no, "日期": dm.group(1), "店铺": dm.group(2),
                     "商品": pm.group(1) if pm else "", "描述": body,
                     "主题": classify(body)})
    clusters = {}
    for r in rows:
        clusters.setdefault(r["主题"], []).append(r)
    cluster_rows = [{"#": str(i), "主题": t, "频次": f"{len(l)} 条"}
                    for i, (t, l) in enumerate(
                        sorted(clusters.items(), key=lambda kv: -len(kv[1])), 1)]
    return {"rows": rows, "clusters": cluster_rows}


def s2_inspect(s1: dict) -> dict:
    """S2 竞品价格巡检：价格事件 + 预警标记（跌幅 ≤ -8%）+ 价格带汇总。"""
    presale = {}          # 商品 -> 预售价（用于低开判定）
    events = []
    for r in s1["rows"]:
        desc, shop, date, no = r["描述"], r["店铺"], r["日期"], r["编号"]
        product = r["商品"]
        m = RE_CUT.search(desc)
        if m:
            old, new = float(m.group(1)), float(m.group(2))
            pct = round((new - old) / old * 100, 1)
            events.append(_ev(no, date, shop, product, "降价",
                              f"{old:g}→{new:g}元", pct))
            continue
        m = RE_REBOUND.search(desc)
        if m:
            new = float(m.group(1))
            events.append(_ev(no, date, shop, product, "价格回升",
                              f"回升至 {new:g}元", None))
            continue
        m = RE_SET.search(desc)
        if m:
            kind, val = m.group(1), float(m.group(2))
            if kind == "预售价":
                presale[product] = val
                events.append(_ev(no, date, shop, product, "新品预售定价",
                                  f"预售价 {val:g}元", None))
            elif kind == "定价":
                events.append(_ev(no, date, shop, product, "新品定价",
                                  f"定价 {val:g}元", None))
            else:  # 开售价
                low = RE_LOWER.search(desc)
                vs = presale.get(product)
                pct = None
                note = f"开售价 {val:g}元"
                if low:
                    low_v = float(low.group(1))
                    pct = round(-low_v / (val + low_v) * 100, 1)
                    note += f"，比预售价低 {low_v:g} 元"
                elif vs:
                    pct = round((val - vs) / vs * 100, 1)
                events.append(_ev(no, date, shop, product, "新品开售（低开）" if pct else "新品开售",
                                  note, pct))
    for e in events:
        e["预警"] = "🔴 预警" if (e["变化%"] is not None and e["变化%"] <= -8.0) else "—"
    bands = {}
    for e in events:
        nums = [float(x) for x in re.findall(r"([\d.]+)元", e["价格明细"])]
        if nums:
            b = bands.setdefault(e["商品"], {"最低": min(nums), "最高": max(nums), "事件数": 0})
            b["最低"] = min(b["最低"], min(nums))
            b["最高"] = max(b["最高"], max(nums))
            b["事件数"] += 1
    band_rows = [{"商品": k, "观测价格带": f"{v['最低']:g}~{v['最高']:g}元",
                  "价格事件数": v["事件数"]} for k, v in sorted(bands.items())]
    stats = {"价格事件数": len(events),
             "预警数": len([e for e in events if e["预警"] != "—"]),
             "覆盖商品数": len(bands)}
    return {"events": events, "bands": band_rows, "stats": stats}


def _ev(no, date, shop, product, etype, note, pct) -> dict:
    return {"编号": no, "日期": date, "店铺": shop, "商品": product,
            "事件类型": etype, "价格明细": note,
            "变化%": pct if pct is not None else None, "预警": "—"}


def write_outputs(s1: dict, s2: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    p = os.path.join(outdir, "flow_clusters.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["#", "主题", "频次"])
        w.writeheader()
        w.writerows(s1["clusters"])
    files.append(p)

    p = os.path.join(outdir, "flow_price_events.csv")
    cols = ["编号", "日期", "店铺", "商品", "事件类型", "价格明细", "变化%", "预警"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for e in s2["events"]:
            w.writerow({**e, "变化%": "—" if e["变化%"] is None else e["变化%"]})
    files.append(p)

    p = os.path.join(outdir, "flow_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"steps": {"S1_竞品动态摘要": {"条目数": len(s1["rows"]),
                                          "主题数": len(s1["clusters"])},
                             "S2_竞品价格巡检": s2["stats"]},
                   "clusters": s1["clusters"], "events": s2["events"],
                   "bands": s2["bands"],
                   "note": "数值由本脚本编排计算；解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 执行摘要", "",
        f"S1 归类 {s2['stats']['价格事件数'] and len(s1['rows'])} 条监控条目；"
        f"S2 识别价格事件 {s2['stats']['价格事件数']} 起，其中跌幅 ≤ -8% 的预警 "
        f"{s2['stats']['预警数']} 起，覆盖 {s2['stats']['覆盖商品数']} 个商品。", "",
        "## 价格事件明细", "",
        "| 编号 | 日期 | 店铺 | 商品 | 事件类型 | 价格明细 | 变化% | 预警 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in s2["events"]:
        lines.append(f"| {e['编号']} | {e['日期']} | {e['店铺']} | {e['商品']} | "
                     f"{e['事件类型']} | {e['价格明细']} | "
                     f"{'—' if e['变化%'] is None else e['变化%']} | {e['预警']} |")
    lines += ["", "## 商品观测价格带", "",
              "| 商品 | 观测价格带 | 价格事件数 |", "|---|---|---|"]
    for b in s2["bands"]:
        lines.append(f"| {b['商品']} | {b['观测价格带']} | {b['价格事件数']} |")
    lines += ["", "## 分步结果", "",
              f"1. 步骤 1（动态摘要）：{len(s1['rows'])} 条归入 {len(s1['clusters'])} 类",
              f"2. 步骤 2（价格巡检）：价格事件 {s2['stats']['价格事件数']} 起，预警 {s2['stats']['预警数']} 起",
              "", "---", "AI 生成内容 · 需人工复核后方可对外使用", ""]
    p = os.path.join(outdir, "flow_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="竞品上架与价格监控工作流（S1 摘要 + S2 巡检）")
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

    s1 = s1_digest(raw)          # S1：动态摘要
    s2 = s2_inspect(s1)          # S2：价格巡检（读 S1 产物）
    files = write_outputs(s1, s2, a.outdir)
    print(f"S1 条目 {len(s1['rows'])} 条 / {len(s1['clusters'])} 类｜"
          f"S2 价格事件 {s2['stats']['价格事件数']} 起（预警 {s2['stats']['预警数']} 起）")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
