# -*- coding: utf-8 -*-
"""
类目热词与趋势采集工作流 —— 确定性编排脚本。

步骤链路（与 SKILL.md 步骤明细一致，每步读上一步产物）：
  S1 类目趋势采集（de_ecom_06_sk01）：从粘贴材料结构化抽取条目，
     按环比阈值（缺省 +19%）与条数上限（缺省 8 条）筛选；
  S2 趋势标记（本流脚本）：对 S1 产物按固定档位标记机会等级——
     环比 ≥ +30% 重点机会；+19%～+30% 观察池；其余拦截不入清单。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物（out/）：
  flow_hotword.csv    S1+S2 机会清单（含趋势标记）
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

RE_HOTWORD = re.compile(
    r"(?:\d+\)\s*)?([^\s：:，,；;()（）]+?)\s*周搜索([\d,]+)\s*环比([+-][\d.]+)%")
RE_REDDIT = re.compile(r"r/([A-Za-z0-9_]+)\s*热帖《([^》]+)》\s*([\d.]+)\s*k?\s*赞")
RE_DOUYIN = re.compile(r"#([^\s（(，,；;]+)\s*周播放量环比([+-][\d.]+)%")


def s1_collect(source: str, scope: str) -> dict:
    """S1 类目趋势采集：结构化 + 阈值筛选（口径与原子技能脚本一致）。"""
    top_n, min_wow = 8, 19.0
    if scope:
        m = re.search(r"条数上限\s*(\d+)", scope)
        if m:
            top_n = int(m.group(1))
        m = re.search(r"环比[≥>]=?\+?\s*([\d.]+)\s*%", scope)
        if m:
            min_wow = float(m.group(1))
    items = []
    for m in RE_HOTWORD.finditer(source):
        items.append({"类型": "类目热词榜", "标题/摘要": m.group(1),
                      "来源": "平台热词榜（用户粘贴）", "关键信息": f"周搜索 {m.group(2)}",
                      "环比%": float(m.group(3))})
    for m in RE_REDDIT.finditer(source):
        items.append({"类型": "海外社区热帖", "标题/摘要": m.group(2),
                      "来源": f"r/{m.group(1)}（用户粘贴）", "关键信息": f"{m.group(3)}k 赞",
                      "环比%": None})
    for m in RE_DOUYIN.finditer(source):
        items.append({"类型": "短视频话题", "标题/摘要": f"#{m.group(1)}",
                      "来源": "抖音话题榜（用户粘贴）", "关键信息": "",
                      "环比%": float(m.group(2))})
    kept = [x for x in items if x["环比%"] is None or x["环比%"] >= min_wow]
    kept.sort(key=lambda x: x["环比%"] if x["环比%"] is not None else -999, reverse=True)
    s1 = {"抓取": len(items), "过阈值": len(kept), "交付": kept[:top_n],
          "阈值": min_wow, "上限": top_n}
    return s1


def s2_mark(s1: dict) -> dict:
    """S2 趋势标记：≥+30% 重点机会；+19%~+30% 观察；无量级环比不标记。"""
    for x in s1["交付"]:
        wow = x["环比%"]
        if wow is None:
            x["趋势标记"] = "无量级环比，不参与分级"
        elif wow >= 30.0:
            x["趋势标记"] = "重点机会"
        elif wow >= s1["阈值"]:
            x["趋势标记"] = "观察池"
        else:
            x["趋势标记"] = "拦截"
    hot = [x for x in s1["交付"] if x["趋势标记"] == "重点机会"]
    s2 = {"重点机会数": len(hot),
          "观察池数": len([x for x in s1["交付"] if x["趋势标记"] == "观察池"]),
          "峰值": hot[0]["标题/摘要"] if hot else ""}
    return s2


def write_outputs(s1: dict, s2: dict, cur: dict, outdir: str) -> list:
    os.makedirs(outdir, exist_ok=True)
    files = []
    rows = s1["交付"]
    for i, x in enumerate(rows, 1):
        x["#"] = str(i)

    p = os.path.join(outdir, "flow_hotword.csv")
    cols = ["#", "类型", "标题/摘要", "来源", "关键信息", "环比%", "趋势标记"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    files.append(p)

    p = os.path.join(outdir, "flow_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"steps": {
            "S1_类目趋势采集": {"抓取": s1["抓取"], "过阈值": s1["过阈值"],
                             "阈值%": s1["阈值"], "条数上限": s1["上限"]},
            "S2_趋势标记": s2},
            "items": rows,
            "note": "数值由本脚本编排计算；业务解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(p)

    lines = [
        "<!-- AI 生成内容，发布前需人工复核 -->", "",
        "## 执行摘要", "",
        f"S1 采集 {s1['抓取']} 条、过阈值 {s1['过阈值']} 条（阈值 +{s1['阈值']:g}%，"
        f"上限 {s1['上限']} 条）；S2 标记重点机会 {s2['重点机会数']} 条、"
        f"观察池 {s2['观察池数']} 条，峰值为「{s2['峰值']}」。", "",
        "## 机会清单（含趋势标记）", "",
        "| # | 类型 | 标题/摘要 | 来源 | 关键信息 | 环比% | 趋势标记 |",
        "|---|---|---|---|---|---|---|",
    ]
    for x in rows:
        lines.append(f"| {x['#']} | {x['类型']} | {x['标题/摘要']} | {x['来源']} | "
                     f"{x['关键信息'] or '—'} | "
                     f"{'—' if x['环比%'] is None else x['环比%']} | {x['趋势标记']} |")
    lines += ["", "---", "AI 生成内容 · 需人工复核后方可对外使用", ""]
    p = os.path.join(outdir, "flow_report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="类目热词与趋势采集工作流（S1 采集 + S2 标记）")
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

    # S1：采集（结构化 + 阈值筛选），产物流入 S2
    scope_m = re.search(r"采集范围[：:](.*)$", raw, re.S)
    s1 = s1_collect(raw, scope_m.group(1) if scope_m else "")
    # S2：趋势标记（读 S1 产物）
    s2 = s2_mark(s1)
    files = write_outputs(s1, s2, cur, a.outdir)
    print(f"S1 采集 {s1['抓取']} 条｜过阈值 {s1['过阈值']} 条｜"
          f"S2 重点机会 {s2['重点机会数']} / 观察 {s2['观察池数']}")
    for p in files:
        print(" 产物:", p, f"({os.path.getsize(p) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
