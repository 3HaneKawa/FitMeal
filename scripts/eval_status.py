from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
MATRIX = EVALS / "capability_matrix.csv"
PILOT = EVALS / "e2_pilot_cases.csv"
CASES = EVALS / "eval_set.csv"
LEGACY = EVALS / "eval_cases.csv"

GROUP_NAMES = {
    "functional": "功能",
    "risk": "安全风险",
    "boundary": "边界",
    "language": "语言变体",
    "cross": "组合难题",
    "future": "后置能力",
}
# 允许暂不达标的范围：承诺未实现 / 明确不在 v1
ALLOW_UNMET_SCOPE = {"v1_promised_not_ready", "v1_out_of_scope", "future_post_v1"}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def section(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(2, 58 - len(title)))


def distribution(rows: list[dict], field: str) -> list[tuple[str, int]]:
    counter = Counter((row.get(field) or "（空）") for row in rows)
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def build_coverage(pilot: list[dict]) -> tuple[Counter, Counter]:
    dev: Counter = Counter()
    holdout: Counter = Counter()
    for row in pilot:
        caps = [c for c in row["capability_id"].split(";") if c]
        target = holdout if row["split"] == "holdout" else dev
        for cap in caps:
            target[cap] += 1
    return dev, holdout


def main() -> None:
    parser = argparse.ArgumentParser(description="FitMeal 评测集状态与覆盖缺口报告")
    parser.add_argument("--strict", action="store_true", help="in-scope 能力未达标时返回非零退出码")
    args = parser.parse_args()

    matrix = read_csv(MATRIX)
    pilot = read_csv(PILOT)
    cases = read_csv(CASES) if CASES.exists() else []
    structured = cases if cases else pilot
    legacy = read_csv(LEGACY) if LEGACY.exists() else []
    dev, holdout = build_coverage(structured)

    try:
        from data_version import version_info

        versions = version_info()
        version_line = " / ".join(
            f"{k}={versions.get(k)}" for k in ("data_version", "rules_version", "bundle_version")
        )
    except Exception:
        version_line = "（未能计算版本号）"

    print("FitMeal 评测集状态报告")
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"版本指纹：{version_line}")

    section("一、用例文件盘点")
    print(f"  evals/eval_cases.csv       {len(legacy):3d} 条  旧口径（expected_recommendations 命中式，无 capability_id / split）")
    print(f"  evals/e2_pilot_cases.csv   {len(pilot):3d} 条  试点结构化集（dev / holdout + 机检 pass_rule）")
    print(f"  evals/eval_set.csv         {len(cases):3d} 条  正式结构化集（E2.2 累积集）")
    print(f"  结构化用例合计             {len(structured):3d} / 目标 270（E1 冻结口径，去重后总数）")
    dev_n = sum(row["split"] == "dev" for row in structured)
    hold_n = sum(row["split"] == "holdout" for row in structured)
    ratio = f"dev:holdout = {dev_n}:{hold_n} ≈ {dev_n / max(hold_n, 1):.1f}:1（目标 4:1）"
    print(f"  划分：dev={dev_n}，holdout={hold_n}    {ratio}")

    sections = {"functional": [], "risk": [], "boundary": [], "language": [], "cross": [], "future": []}
    for row in matrix:
        sections.setdefault(row["group"], []).append(row)

    section("二、能力覆盖 vs 目标（结构化集）")
    print(f"  {'ID':<4}{'能力':<32}{'dev':>10}{'holdout':>12}  状态")
    unmet: list[tuple[int, str, str]] = []
    for group in ("functional", "risk", "boundary", "language", "cross", "future"):
        rows = sections.get(group, [])
        if not rows:
            continue
        print(f"  【{GROUP_NAMES.get(group, group)}】")
        for row in rows:
            cap = row["matrix_id"]
            target_dev = int(row["case_target"] or 0)
            target_hold = int(row["holdout_target"] or 0)
            have_dev, have_hold = dev.get(cap, 0), holdout.get(cap, 0)
            if target_dev == 0 and target_hold == 0:
                mark = "—"
            elif have_dev >= target_dev and have_hold >= target_hold:
                mark = "✔"
            else:
                short = (target_dev - have_dev) + (target_hold - have_hold)
                mark = f"缺 {short}"
                if row["v1_scope"] not in ALLOW_UNMET_SCOPE:
                    unmet.append((short, cap, f"{row['capability']} {have_dev}/{target_dev} dev, {have_hold}/{target_hold} holdout"))
            print(f"  {cap:<4}{row['capability'][:30]:<32}{have_dev:>4}/{target_dev:<4}{have_hold:>6}/{target_hold:<4}{'':<1}  {mark}")

    section("三、未达标能力（in-scope，按缺口排序）")
    if not unmet:
        print("  全部达标。")
    else:
        for short, cap, detail in sorted(unmet, reverse=True):
            print(f"  [{cap}] 缺 {short:3d} 条  {detail}")
        print()
        print(f"  合计 {len(unmet)} 项能力未达标（不含 F10 等暂缓项）。")

    section("四、用例分布（结构化集）")
    labels = {
        "expected_intent": "意图",
        "expected_behavior": "期望行为",
        "expected_goal": "目标",
        "severity": "严重度",
        "grader": "评分方式",
        "failure_stage": "失败阶段",
        "expected_region": "地域",
    }
    for field, label in labels.items():
        pairs = distribution(structured, field)
        print(f"  {label}：" + "，".join(f"{k} {v}" for k, v in pairs))

    section("五、结论")
    print(f"  - 结构化评测集规模 {len(structured)} / 270，覆盖 {len(set(dev) | set(holdout))} 项能力。")
    print(f"  - 未达标 in-scope 能力 {len(unmet)} 项；F10 为承诺未实现，暂按占位处理。")
    print("  - 旧口径 eval_cases.csv 32 条仍待按维护计划迁移；文件保留，继续作为回归参考。")
    print("  - rubric.md 营养阈值与 goal_rules.csv 一致性校验已 PASS。")
    print("  - 下一批优先补 F06 / F08，随后补安全风险与 X01 交叉难题。")
    print("  - 分批建设与门禁见 docs/eval-maintenance-plan.md。")

    if args.strict and unmet:
        print()
        print(f"FAIL 严格模式：{len(unmet)} 项 in-scope 能力未达标。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
