# -*- coding: utf-8 -*-
"""数据写入层：新增 / 更新数据行，并保证文件格式不变。

设计约束：
- **只走这里写 CSV**。任何脚本或接口都不要自己 open(..., "w") 写 data/*.csv。
- 保持原有格式：BOM 有无、行尾（CRLF / LF）、列顺序、列名全部原样保留。
- 原子写入：先写同目录临时文件，再 os.replace 覆盖，中途失败不会留下半个文件。
- 本模块只负责「格式安全的读写 + 主键生成」，业务校验在 data_entry.py。
"""

import csv
import io
import os
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# 表名 -> (文件名, id 前缀或 None)
TABLES = {
    "nutrition": ("nutrition.csv", "I"),
    "recipes": ("recipes.csv", "R"),
    "eat_out": ("eat_out_foods.csv", "E"),
    "substitutions": ("substitutions.csv", "S"),
    "aliases": ("ingredient_aliases.csv", None),
    "units": ("unit_conversions.csv", None),
    # 只读配置表，仅用于读取与列出结构，不提供 data_entry 写接口
    "goal_rules": ("goal_rules.csv", None),
    # 施工单：current_recipes 为派生列，改食谱后用 scripts/refresh_target_ingredients.py 刷新
    "target_ingredients": ("target_ingredients.csv", None),
}


class DataError(ValueError):
    """入参不合法。接口层会把它翻译成 HTTP 400。"""


def table_path(table):
    if table not in TABLES:
        raise DataError(f"未知数据表: {table}；可用: {', '.join(TABLES)}")
    return DATA_DIR / TABLES[table][0]


def read_table(table):
    """返回 (fieldnames, rows)。文件不存在时返回 (None, [])。"""
    path = table_path(table)
    if not path.exists():
        return None, []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_table(table, fieldnames, rows):
    """原子写回，保持 BOM 与行尾风格。"""
    path = table_path(table)
    raw = path.read_bytes() if path.exists() else b""
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    crlf = b"\r\n" in raw

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\r\n" if crlf else "\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        # 缺失列补空串，避免 DictWriter 报错
        writer.writerow({key: row.get(key, "") for key in fieldnames})

    data = buffer.getvalue().encode("utf-8")
    if had_bom:
        data = b"\xef\xbb\xbf" + data

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def next_id(table, rows):
    """按已有 id 递增生成下一个主键，如 R001 -> R002。"""
    _, prefix = TABLES.get(table, (None, None))
    if not prefix:
        raise DataError(f"{table} 没有 id 列")
    pattern = re.compile(rf"^{prefix}(\d+)$")
    biggest = 0
    width = 3
    for row in rows:
        match = pattern.match(str(row.get("id", "")).strip())
        if match:
            digits = match.group(1)
            width = max(width, len(digits))
            biggest = max(biggest, int(digits))
    return f"{prefix}{biggest + 1:0{width}d}"


def append_row(table, row):
    """追加一行；缺列留空。返回落库后的完整行。"""
    fieldnames, rows = read_table(table)
    if fieldnames is None:
        raise DataError(f"数据表不存在: {TABLES[table][0]}")
    unknown = [key for key in row if key not in fieldnames]
    if unknown:
        raise DataError(
            f"{TABLES[table][0]} 不认识的列: {', '.join(unknown)}；"
            f"可用列: {', '.join(fieldnames)}"
        )
    merged = {key: "" for key in fieldnames}
    merged.update({k: ("" if v is None else str(v)) for k, v in row.items()})
    rows.append(merged)
    write_table(table, fieldnames, rows)
    return merged


def replace_row(table, index, row):
    """按行号整体替换（用于更新）。"""
    fieldnames, rows = read_table(table)
    merged = {key: "" for key in fieldnames}
    merged.update({k: ("" if v is None else str(v)) for k, v in row.items()})
    rows[index] = merged
    write_table(table, fieldnames, rows)
    return merged


def find_index(table, predicate):
    """返回第一个满足条件的行号，找不到返回 -1。"""
    _, rows = read_table(table)
    for i, row in enumerate(rows):
        if predicate(row):
            return i
    return -1


def ensure_columns(table, required):
    """确认表的列名齐全，缺列直接报错（防止写坏结构）。"""
    fieldnames, _ = read_table(table)
    if not fieldnames:
        raise DataError(f"数据表不存在或为空: {TABLES[table][0]}")
    missing = [col for col in required if col not in fieldnames]
    if missing:
        raise DataError(f"{TABLES[table][0]} 缺列: {', '.join(missing)}")
    return fieldnames


def commit():
    """占位：当前每次写入都是立即落盘，保留这个函数方便日后改成批量事务。"""
    return None
