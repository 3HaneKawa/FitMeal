from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

DATA_FILES = [
    "recipes.csv",
    "nutrition.csv",
    "eat_out_foods.csv",
    "ingredient_aliases.csv",
    "unit_conversions.csv",
    "target_ingredients.csv",
]
RULE_FILES = [
    "goal_rules.csv",
    "substitutions.csv",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_files(filenames: list[str]) -> tuple[str, dict[str, str]]:
    per_file = {name: _sha256(DATA_DIR / name) for name in filenames}
    payload = "\n".join(f"{name}:{per_file[name]}" for name in filenames)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), per_file


def version_info() -> dict:
    data_hash, data_files = _hash_files(DATA_FILES)
    rules_hash, rule_files = _hash_files(RULE_FILES)
    bundle_hash = hashlib.sha256(
        f"data:{data_hash}\nrules:{rules_hash}".encode("utf-8")
    ).hexdigest()
    return {
        "data_version": "dv-" + data_hash[:12],
        "rules_version": "rv-" + rules_hash[:12],
        "bundle_version": "bv-" + bundle_hash[:12],
        "data_files": data_files,
        "rule_files": rule_files,
    }


def main() -> None:
    info = version_info()
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
