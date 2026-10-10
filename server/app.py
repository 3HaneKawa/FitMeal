"""FitMeal 本地数据服务（方案 B）。

把 `scripts/handler.py` 的筛选 / 评分 / 过敏过滤 / 营养计算包装成 HTTP 接口，
供 Dify Chatflow 的「HTTP 请求」节点调用，替代在 Dify 代码节点里内联约 5.5 万字符的数据表。

同时提供一整套**数据录入接口**（/data/*），用于快速补数据：
菜谱、食材营养成分、外食条目、食材别名、单位换算。这样"数据量不够"有了兜底手段——
不用手改 CSV，直接 POST 一行数据即可，营养由 Python 现算、格式由写入层保证。

设计约束（与 docs/architecture.md 一致）：
- 本服务是**唯一的计算与筛选来源**，LLM 不得改写其输出。
- 只做参数分发 + 结构化，不做自然语言生成。
- 写接口不接受"营养数值"作为食谱输入：食谱只给食材与克重，营养必须现算。
- 依赖 Python 标准库 + fastapi / uvicorn，不需要数据库。

启动（项目根目录下，完整命令见 README.md）：

    uv run --python 3.12 --with fastapi --with uvicorn \
        uvicorn app:app --app-dir server --host 0.0.0.0 --port 8765

接口一览：
- GET  /health                服务与数据表状态（Dify 探活 / 排查用）
- GET  /chat/status           Dify 代理配置状态
- POST /chat                  前端自然语言入口：代理调用 Dify Chatflow
- POST /recommend             Dify HTTP 节点内部数据接口，不由前端直接调用
- POST /feedback              记录采纳、不喜欢、太麻烦和换一批事件
- GET  /data/schema           数据表的列名、行数、id 前缀（录入端先看这个）
- GET  /data/rows             只读查询一张数据表（关键词搜索 + 分页）
- POST /data/nutrition        新增 / 更新一条食材营养（每 100g）
- POST /data/recipes/preview  食谱营养试算（不落库，含目标区间判定）
- POST /data/recipes          新增一条食谱（营养现算，不接受手填）
- POST /data/eat_out          新增一条外食条目
- POST /data/aliases          新增 / 更新一条食材别名
- POST /data/units            新增 / 更新一条单位换算
- POST /data/import           批量导入（数组，逐条返回成功 / 失败）
- POST /data/regen            按当前营养库重算所有食谱营养缓存

录入示例（先加食材，再加食谱，营养由服务算）：

    curl -X POST http://127.0.0.1:8765/data/nutrition \
      -H "Content-Type: application/json" \
      -d '{"name":"秋葵","category":"vegetable","calories":33,"protein_g":2,"fat_g":0.2,"carbs_g":7.5,"fiber_g":3.9}'

    curl -X POST http://127.0.0.1:8765/data/recipes \
      -H "Content-Type: application/json" \
      -d '{"name":"秋葵炒鸡胸","goal":"fat_loss","region":"上海","cooking_time":15,
           "ingredients":"鸡胸肉:150g;秋葵:200g","tags":["高蛋白","快手菜"]}'

    curl -X POST http://127.0.0.1:8765/recommend \
      -H "Content-Type: application/json" \
      -d '{"intent":"cook","ingredients":["鸡胸肉","西兰花"],"goal":"fat_loss","time_limit":20,"region":"成都"}'
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import data_entry  # noqa: E402
from data_store import DataError  # noqa: E402
from handler import handle  # noqa: E402  （必须先补 sys.path 才能 import）
from feedback_store import FeedbackError, record_feedback  # noqa: E402

WEB_DIR = ROOT / "web"
ENV_PATH = ROOT / ".env"


def _load_local_env(path: Path) -> None:
    """读取项目根目录 .env；真实环境变量优先，不让文件覆盖部署配置。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env(ENV_PATH)

DIFY_CHAT_URL = os.environ.get(
    "DIFY_API_URL", "http://127.0.0.1/v1/chat-messages"
).strip()
DIFY_API_KEY = os.environ.get("DIFY_API_KEY", "").strip()
try:
    DIFY_TIMEOUT_SECONDS = float(os.environ.get("DIFY_TIMEOUT_SECONDS", "180"))
except ValueError:
    DIFY_TIMEOUT_SECONDS = 180.0
DIFY_TIMEOUT_SECONDS = min(max(DIFY_TIMEOUT_SECONDS, 10.0), 300.0)

SERVICE_NAME = "fitmeal-data"
SERVICE_VERSION = "0.4.0"
DATA_TABLES = (
    "recipes.csv",
    "nutrition.csv",
    "eat_out_foods.csv",
    "goal_rules.csv",
    "substitutions.csv",
    "ingredient_aliases.csv",
    "unit_conversions.csv",
)

app = FastAPI(
    title="FitMeal 本地数据服务",
    version=SERVICE_VERSION,
    description=(
        "前端通过 /chat 代理调用 Dify Chatflow；筛选、评分、营养计算由 Dify "
        "HTTP 节点调用本服务完成。另提供 /data/* 数据录入接口。"
    ),
)


# ---------------------------------------------------------------- 通用工具

def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": code, "message": message, **extra},
    )


def _run(action, payload: Any) -> JSONResponse:
    """统一跑一个录入动作：DataError -> 400，其他异常 -> 500。"""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _error(400, "bad_request", "请求体必须是 JSON 对象")
    try:
        result = action(payload)
    except DataError as exc:
        return _error(400, "invalid_data", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))
    return JSONResponse(content={"ok": True, "result": result})


def _table_counts() -> dict[str, int]:
    """读一遍数据表行数，用于健康检查与「服务读到的是不是最新数据」核对。"""
    from recommend import load_csv

    return {name: len(load_csv(name)) for name in DATA_TABLES}


# ---------------------------------------------------------------- Dify 代理

def _dify_status() -> dict[str, Any]:
    """只报告配置状态，不向前端暴露 API Key 或上游完整错误。"""
    return {
        "configured": bool(DIFY_CHAT_URL and DIFY_API_KEY),
        "provider": "Dify Chatflow",
        "timeout_seconds": DIFY_TIMEOUT_SECONDS,
    }


def _upstream_message(body: bytes) -> str:
    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        return "上游没有返回可读信息"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:300]
    if isinstance(parsed, dict):
        for key in ("message", "error", "detail"):
            value = parsed.get(key)
            if value:
                return str(value)[:300]
    return raw[:300]


def _call_dify_chat(
    query: str,
    conversation_id: str,
    user: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """由服务端持有密钥调用 Dify，浏览器永远拿不到 Dify API Key。"""
    if not DIFY_CHAT_URL or not DIFY_API_KEY:
        raise RuntimeError("Dify 未配置：请在项目根目录 .env 中设置 DIFY_API_KEY")

    request_payload = {
        "inputs": inputs,
        "query": query,
        "response_mode": "blocking",
        "conversation_id": conversation_id,
        "user": user,
    }
    request = urllib.request.Request(
        DIFY_CHAT_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=DIFY_TIMEOUT_SECONDS) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        detail = _upstream_message(exc.read())
        raise RuntimeError(f"Dify 返回异常（HTTP {exc.code}）：{detail}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or "连接失败"
        raise RuntimeError(f"无法连接 Dify：{reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Dify 响应超过 {DIFY_TIMEOUT_SECONDS:.0f} 秒") from exc

    try:
        data = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Dify 返回了无法解析的响应") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Dify 返回格式不正确")
    return data


@app.get("/chat/status")
def chat_status() -> JSONResponse:
    """前端探活用：确认服务已配置 Dify 代理。"""
    return JSONResponse(content={"ok": True, **_dify_status()})


@app.post("/chat")
def chat_endpoint(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """前端唯一聊天入口：自然语言 -> Dify Chatflow -> 回答。"""
    if not isinstance(payload, dict):
        return _error(400, "bad_request", "请求体必须是 JSON 对象")

    query = str(payload.get("query") or "").strip()
    if not query:
        return _error(400, "empty_query", "请先输入你的饮食需求")
    if len(query) > 4000:
        return _error(400, "query_too_long", "输入内容过长，请控制在 4000 字以内")

    conversation_id = str(payload.get("conversation_id") or "").strip()[:128]
    user = str(payload.get("user") or "fitmeal-web").strip()[:128] or "fitmeal-web"
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    started = time.perf_counter()
    try:
        upstream = _call_dify_chat(query, conversation_id, user, inputs)
    except RuntimeError as exc:
        return _error(502, "dify_error", str(exc))

    answer = str(upstream.get("answer") or "").strip()
    if not answer:
        return _error(502, "empty_answer", "Dify 没有返回可展示的回答")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return JSONResponse(
        content={
            "ok": True,
            "answer": answer,
            "conversation_id": upstream.get("conversation_id") or conversation_id,
            "message_id": upstream.get("message_id") or upstream.get("id") or "",
            "request_id": uuid.uuid4().hex,
            "elapsed_ms": elapsed_ms,
            "metadata": upstream.get("metadata") or {},
        }
    )


# ---------------------------------------------------------------- 查询 / 推荐

@app.get("/health")
def health() -> JSONResponse:
    """Dify / 运维探活。返回 ok 且行数与最新数据一致时，才说明服务可以接流量。"""
    try:
        counts = _table_counts()
    except Exception as exc:  # 数据表被删/改坏时也要给出可读原因
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "message": str(exc),
            },
        )
    return JSONResponse(
        content={
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "data": counts,
            "chat": _dify_status(),
        }
    )


def _unwrap_payload(body: Any) -> dict[str, Any]:
    """兼容 Dify HTTP 节点两种 Body 写法。

    Dify 的 JSON Body 有时只能写成 `{"payload": <变量>}`，所以这里同时接受：
    - 直接把合并后的 payload 当整个 Body（推荐）
    - 外面包一层 `{"payload": {...}}`
    """
    if not isinstance(body, dict):
        return {}
    inner = body.get("payload")
    if len(body) == 1 and isinstance(inner, dict):
        return inner
    return body


@app.post("/recommend")
def recommend_endpoint(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """接收合并后的 payload，返回 api-contract §4 的响应结构。

    出参固定为 `{"result": {...}, "elapsed_ms": n}`：
    Dify HTTP 节点里用 `body.result` 取结果，与原来代码节点绑 `result` 的习惯一致。
    """
    started = time.perf_counter()
    payload = _unwrap_payload(payload)
    try:
        result = handle(payload)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": str(exc),
                "payload": payload or {},
            },
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    request_id = uuid.uuid4().hex
    return JSONResponse(
        content={"result": result, "elapsed_ms": elapsed_ms, "request_id": request_id}
    )


@app.post("/feedback")
def feedback_endpoint(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """记录用户对单次推荐的最小反馈，不读取或改写推荐排序。"""
    if not isinstance(payload, dict):
        return _error(400, "bad_request", "请求体必须是 JSON 对象")
    try:
        event = record_feedback(payload)
    except FeedbackError as exc:
        return _error(400, "invalid_feedback", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))
    return JSONResponse(content={"ok": True, "event": event})


# ---------------------------------------------------------------- 数据录入

@app.get("/data/rows")
def data_rows(
    table: str = Query(..., min_length=1, description="数据表名，例如 nutrition / recipes"),
    q: str = Query("", description="跨字段关键词搜索"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    """只读查询已有数据，供数据总览页使用。"""
    try:
        result = data_entry.query_rows(table=table, query=q, limit=limit, offset=offset)
        return JSONResponse(content={"ok": True, "result": result})
    except DataError as exc:
        return _error(400, "invalid_query", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))


@app.get("/data/schema")
def data_schema() -> JSONResponse:
    """六张表的列名 / 行数 / id 前缀。写数据前先看这里，避免字段名猜错。"""
    try:
        return JSONResponse(content={"ok": True, "result": data_entry.describe_tables()})
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))


@app.post("/data/nutrition")
def data_nutrition(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """新增 / 更新一条食材营养。默认同名覆盖（upsert），可传 mode=append 改成同名报错。"""
    return _run(data_entry.add_nutrition, payload)


@app.post("/data/recipes/preview")
def data_recipes_preview(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """食谱营养试算，不落库。落库前用它确认营养是否落在目标区间。"""
    return _run(data_entry.preview_recipe, payload)


@app.post("/data/recipes")
def data_recipes(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """新增一条食谱。营养由服务按 nutrition.csv 现算，调用方只需给食材与克重。"""
    return _run(data_entry.add_recipe, payload)


@app.post("/data/eat_out")
def data_eat_out(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """新增一条外食条目。"""
    return _run(data_entry.add_eat_out, payload)


@app.post("/data/aliases")
def data_aliases(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """新增 / 更新食材别名，例如 大虾 -> 虾仁。标准名必须已存在于营养库。"""
    return _run(data_entry.add_alias, payload)


@app.post("/data/units")
def data_units(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """新增 / 更新单位换算，例如 瓣 / 蒜 = 5g；不填 ingredient 表示通用默认值。"""
    return _run(data_entry.add_unit, payload)


@app.post("/data/import")
def data_import(payload: Any = Body(default=None)) -> JSONResponse:
    """批量导入。Body 可以是数组，也可以是 `{"items": [...]}`。

    每条形如 `{"table": "nutrition", "name": "秋葵", ...}`，
    逐条返回成功 / 失败，一条出错不会中断整批。
    """
    items = payload
    if isinstance(payload, dict):
        items = payload.get("items")
    if not isinstance(items, list):
        return _error(400, "bad_request", "批量导入需要一个数组，或 {'items': [...]}")
    try:
        return JSONResponse(content={"ok": True, "result": data_entry.import_batch(items)})
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))


@app.post("/data/regen")
def data_regen(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    """按当前营养库重算所有食谱的营养缓存。改过营养库 / 别名 / 单位后必须调用。"""
    return _run(lambda _payload: data_entry.regen_recipes(), payload)


# ---------------------------------------------------------------- 产品 Demo
# 前端与 API 同源，避免浏览器 CORS，也避免 Demo 依赖外部 CDN。

@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/app/")


app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")


def main() -> None:
    """`uv run --python 3.12 --with fastapi --with uvicorn python server/app.py` 也能起服务。"""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)


if __name__ == "__main__":
    main()
