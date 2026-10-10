"""Offline regression checks for the deterministic nutrition calculator.

The checks use the same data_entry function as the HTTP endpoint, but do not
start FastAPI, Dify, or the embedding service.
"""

from __future__ import annotations

from data_entry import calculate_nutrition
from data_store import DataError


def expect_close(actual: float, expected: float, label: str) -> None:
    if abs(float(actual) - float(expected)) > 0.05:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def expect_error(payload: dict, expected_text: str) -> None:
    try:
        calculate_nutrition(payload)
    except DataError as exc:
        if expected_text not in str(exc):
            raise AssertionError(
                f"unexpected error for {payload!r}: {exc}"
            ) from exc
        return
    raise AssertionError(f"expected DataError containing {expected_text!r}")


def check_standard_and_servings() -> None:
    result = calculate_nutrition(
        {
            "items": [
                {"name": "鸡胸肉", "amount_g": 150},
                {"name": "西兰花", "amount_g": 200},
            ],
            "servings": 2,
        }
    )
    expected_total = {
        "calories": 248.0,
        "protein_g": 39.4,
        "fat_g": 4.7,
        "carbs_g": 13.2,
        "fiber_g": 5.2,
    }
    expected_per_serving = {
        "calories": 124.0,
        "protein_g": 19.7,
        "fat_g": 2.4,
        "carbs_g": 6.6,
        "fiber_g": 2.6,
    }
    if result["complete"] is not True or result["unresolved"]:
        raise AssertionError("standard ingredients should be fully resolved")
    expect_close(result["total_weight_g"], 350.0, "total_weight_g")
    expect_close(result["serving_weight_g"], 175.0, "serving_weight_g")
    for key, expected in expected_total.items():
        expect_close(result["total_nutrition"][key], expected, f"total.{key}")
    for key, expected in expected_per_serving.items():
        expect_close(
            result["per_serving_nutrition"][key],
            expected,
            f"per_serving.{key}",
        )
    if len(result["ingredient_breakdown"]) != 2:
        raise AssertionError("expected two ingredient breakdown rows")
    if abs(sum(item["calorie_share"] for item in result["ingredient_breakdown"]) - 1.0) > 0.01:
        raise AssertionError("ingredient calorie shares should add up to 1")


def check_alias_and_source() -> None:
    result = calculate_nutrition(
        {"items": [{"name": "西红柿", "amount_g": 100}]}
    )
    item = result["ingredient_breakdown"][0]
    if item["name"] != "番茄" or item["raw_name"] != "西红柿":
        raise AssertionError("alias should be normalized while preserving raw input")
    expect_close(result["total_nutrition"]["calories"], 18.0, "alias calories")
    if not item.get("source_ref") or not item.get("source_name"):
        raise AssertionError("source metadata should be preserved")


def check_unresolved_items() -> None:
    partial = calculate_nutrition(
        {
            "items": [
                {"name": "火星蔬菜", "amount_g": 100},
                {"name": "鸡胸肉", "amount_g": 50},
            ]
        }
    )
    if partial["complete"] is not False:
        raise AssertionError("partial input must not be marked complete")
    if [item["name"] for item in partial["unresolved"]] != ["火星蔬菜"]:
        raise AssertionError("unresolved item was not exposed")
    expect_close(partial["total_nutrition"]["calories"], 60.0, "partial calories")
    expect_close(partial["total_weight_g"], 50.0, "partial total weight")

    all_unresolved = calculate_nutrition(
        {"items": [{"name": "火星蔬菜", "amount_g": 100}]}
    )
    if all_unresolved["complete"] is not False:
        raise AssertionError("all-unresolved input must not be marked complete")
    if all_unresolved["ingredient_breakdown"]:
        raise AssertionError("all-unresolved input should have no breakdown")
    if all_unresolved["total_nutrition"]["calories"] != 0.0:
        raise AssertionError("all-unresolved input should return zero calories")


def check_invalid_input() -> None:
    expect_error({}, "items 至少")
    expect_error({"items": []}, "items 至少")
    expect_error({"items": [{"amount_g": 100}]}, "第 1 项食材名")
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": 0}]},
        "第 1 项重量",
    )
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": -1}]},
        "第 1 项重量",
    )
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": "heavy"}]},
        "第 1 项重量",
    )
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": 100}], "servings": 0},
        "1 到 100",
    )
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": 100}], "servings": 1.5},
        "整数",
    )
    expect_error(
        {"items": [{"name": "鸡胸肉", "amount_g": 100}], "servings": 101},
        "1 到 100",
    )


def main() -> None:
    check_standard_and_servings()
    check_alias_and_source()
    check_unresolved_items()
    check_invalid_input()
    print("PASS nutrition calculator: standard, alias, servings, unresolved, invalid input")


if __name__ == "__main__":
    main()
