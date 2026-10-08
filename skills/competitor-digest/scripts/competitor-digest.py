# -*- coding: utf-8 -*-
"""
竞品动态摘要 —— 确定性脚本：条目结构化 + 归类聚类 + 频次统计 + 产物落盘。

职责边界：
  本脚本只做**确定性计算**：解析竞品监控原始条目（[n] 日期 店铺 描述）、
  按「价格调整 / 新品上架 / 促销活动 / 流量投放 / 其他」归类、统计每家店铺的
  动作频次并落盘。洞察文案与共性结论由模型按 prompt.txt 完成。

输入（examples/input.json 或 --input）：
  items : 竞品监控原始条目文本（含 [序号] 日期 店铺 描述）

用法：
  python competitor-digest.py --input input.json --outdir out
  python competitor-digest.py --demo

产物（out/）：
  digest_clusters.csv   分组结果（主题 / 包含条目 / 频次）
  digest_shop_stats.csv 店铺维度动作频次
  digest_summary.json   机器可读结果
  digest_report.md      摘要报告（Markdown 表格）
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

# 条目模式：[n] MM-DD 店铺X 描述
RE_ITEM = re.compile(
    r"\[(\d+)\]\s*(\d{2}-\d{2})\s*(店铺[A-Za-z0-9]+)\s*[「]?([^」\n]*?)[」]?\s*(?=[，,；;。]|$)")
# 单条目的完整描述需重新切分：[n] 之后的整段
RE_SEG = re.compile(r"\[(\d+)\]\s*([^\[]{3,})")

PRICE_KEYS = ("到手价", "定价", "预售价", "开售价", "价格回升", "元→", "元→")
NEW_KEYS = ("上新", "上架", "开售", "新品")
PROMO_KEYS = ("满减", "满", "赠品", "优惠券", "直播")
TRAFFIC_KEYS = ("销量榜", "广告位", "排名", "搜索广告")


def classify(text: str) -> str:
    if any(k in text for k in PRICE_KEYS) and "元" in text:
        return "价格调整"
    if any(k in text for k in TRAFFIC_KEYS):
        return "流量投放"
    if any(k in text for k in NEW_KEYS):
        return "新品上架"
    if any(k in text for k in PROMO_KEYS):
        return "促销活动"
    return "其他"


def parse(items_text) -> list:
    if isinstance(items_text, list):        # 兼容数组式输入
        items_text = "；".join(str(x) for x in items_text)
    if not isinstance(items_text, str):
        return []
    rows = []
    for m in RE_SEG.finditer(items_text):
        no, body = m.group(1), m.group(2).strip().rstrip("；;。")
        dm = re.match(r"(\d{2}-\d{2})\s*(店铺[A-Za-z0-9]+)\s*(.*)", body)
        if not dm:
            continue
        date, shop, desc = dm.group(1), dm.group(2), dm.group(3).strip()
        rows.append({"编号": no, "日期": date, "店铺": shop,
                     "描述": desc, "主题": classify(desc)})
    return rows


def digest(rows: list) -> dict:
    clusters = {}
    for r in rows:
        clusters.setdefault(r["主题"], []).append(r)
    cluster_rows = []
    for i, (topic, lst) in enumerate(
            sorted(clusters.items(), key=lambda kv: -len(kv[1])), 1):
        cluster_rows.append({
            "#": str(i),
            "主题": topic,
            "包含条目": "；".join(f"[{r['编号']}] {r['店铺']} {r['描述']}" for r in lst),
            "频次": f"{len(lst)} 条",
            "_n": len(lst),
        })
    shops = {}
    for r in rows:
        shops.setdefault(r["店铺"], []).append(r)
    shop_rows = []
    for shop in sorted(shops):
        lst = shops[shop]
        shop_rows.append({
            "店铺": shop, "动作数": len(lst),
            "动作类型": "、".join(sorted({r["主题"] for r in lst})),
            "日期跨度": f"{min(r['日期'] for r in lst)} ~ {max(r['日期'] for r in lst)}",
        })
    stats = {
        "条目总数": len(rows),
        "店铺数": len(shops),
        "主题数": len(clusters),
        "最大簇主题": cluster_rows[0]["主题"] if cluster_rows else "",
        "最大簇频次": cluster_rows[0]["_n"] if cluster_rows else 0,
        "动作最多店铺": max(shop_rows, key=lambda x: x["动作数"])["店铺"] if shop_rows else "",
        "分类占比%": {c["主题"]: round(c["_n"] * 100 / len(rows), 1)
                     for c in cluster_rows} if rows else {},
    }
    for c in cluster_rows:
        c.pop("_n")
    return {"clusters": cluster_rows, "shop_stats": shop_rows,
            "stats": stats, "items": rows}


def write_outputs(result: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    clusters, shop_rows, stats, items = (
        result["clusters"], result["shop_stats"], result["stats"], result["items"])

    p = os.path.join(outdir, "digest_clusters.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["#", "主题", "包含条目", "频次"])
        w.writeheader()
        w.writerows(clusters)
    files.append(p)

    p = os.path.join(outdir, "digest_shop_stats.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["店铺", "动作数", "动作类型", "日期跨度"])
        w.writeheader()
        w.writerows(shop_rows)
    files.append(p)

    p = os.path.join(outdir, "digest_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "clusters": clusters, "shop_stats": shop_rows,
                   "items": items,
                   "note": "聚类与频次由本脚本计算；共性洞察由模型按 prompt.txt 撰写"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 分组结果", "",
        "| # | 主题 | 包含条目 | 频次 |", "|---|---|---|---|",
    ]
    for c in clusters:
        lines.append(f"| {c['#']} | {c['主题']} | {c['包含条目']} | {c['频次']} |")
    lines += [
        "", "## 店铺动作频次", "",
        "| 店铺 | 动作数 | 动作类型 | 日期跨度 |", "|---|---|---|---|",
    ]
    for s in shop_rows:
        lines.append(f"| {s['店铺']} | {s['动作数']} | {s['动作类型']} | {s['日期跨度']} |")
    lines += [
        "", "## 统计", "",
        "| 项 | 值 |", "|---|---|",
        f"| 条目总数 | {stats['条目总数']} 条 |",
        f"| 店铺数 / 主题数 | {stats['店铺数']} 家 / {stats['主题数']} 类 |",
        f"| 最大簇 | {stats['最大簇主题']}（{stats['最大簇频次']} 条） |",
        f"| 动作最多店铺 | {stats['动作最多店铺']} |",
        "", "（共性洞察与证据索引由模型按 prompt.txt 在本表基础上撰写）",
        "", "---", "AI 生成内容 · 需人工复核后方可对外使用", "",
    ]
    p = os.path.join(outdir, "digest_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="竞品动态摘要（结构化 + 聚类 + 频次）")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="用 examples/input.json 演示")
    a = ap.parse_args()

    src = a.input or (DEFAULT_INPUT if a.demo else None)
    if not src:
        ap.error("需提供 --input 或 --demo")
    with open(src, encoding="utf-8") as f:
        cur = json.load(f)
    rows = parse(cur.get("items", ""))
    if not rows:
        print("[错误] 未能解析出任何 [n] 日期 店铺 描述 条目：不猜测格式，请检查条目写法。",
              file=sys.stderr)
        sys.exit(3)

    result = digest(rows)
    files = write_outputs(result, a.outdir)
    s = result["stats"]
    print(f"条目 {s['条目总数']} 条｜店铺 {s['店铺数']} 家｜主题 {s['主题数']} 类｜"
          f"最大簇 {s['最大簇主题']} {s['最大簇频次']} 条")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
