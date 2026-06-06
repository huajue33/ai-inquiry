"""可选模型注册表。

前端的模型下拉来自这里，后端同时用它做请求校验（服务端为权威，前端不能传任意
模型字符串直达 LLM）。

可选模型集合由环境变量 DASHSCOPE_MODELS（逗号分隔的模型 ID）决定；未配置时默认
使用 DASHSCOPE_MODEL（主模型）+ DASHSCOPE_LITE_MODEL（轻量模型）。

KNOWN_MODELS 只是给已知模型补充友好名称/描述/是否支持深度思考，用于前端展示；
不在表里的模型 ID 仍可用，名称回退为 ID 本身、supports_thinking 默认 False（保守，
避免对不支持的模型发送 enable_thinking 而报错）。这些元信息为经验值，可按你实际
开通的 DashScope 模型自行调整。
"""
from app.config import get_settings

# id -> 展示元信息
# supports_thinking 依据百炼「深度思考」官方文档（2026-06）：
# Qwen3.5/3.6/3.7 的 plus/max/flash 系列支持思考；qwen-plus 支持；
# qwen-max/qwen-turbo 为非思考模型。可按你实际开通情况调整。
KNOWN_MODELS: dict[str, dict] = {
    # ── Qwen3.7 系列 ──
    "qwen3.7-max":         {"name": "Qwen3.7 Max",  "description": "旗舰，复杂推理最强",   "supports_thinking": True},
    "qwen3.7-plus":        {"name": "Qwen3.7 Plus", "description": "综合能力强",          "supports_thinking": True},
    # ── Qwen3.6 系列 ──
    "qwen3.6-max-preview": {"name": "Qwen3.6 Max",  "description": "复杂推理",            "supports_thinking": True},
    "qwen3.6-plus":        {"name": "Qwen3.6 Plus", "description": "综合能力强",          "supports_thinking": True},
    # ── Qwen3.5 系列 ──
    "qwen3.5-plus":        {"name": "Qwen3.5 Plus", "description": "综合能力强",          "supports_thinking": True},
    "qwen3.5-flash":       {"name": "Qwen3.5 Flash","description": "快速、低成本",         "supports_thinking": True},
    # ── 通用滚动别名（指向最新快照）──
    "qwen-plus":           {"name": "Qwen Plus",    "description": "均衡，支持思考",       "supports_thinking": True},
    "qwen-max":            {"name": "Qwen Max",     "description": "旗舰（不支持思考）",    "supports_thinking": False},
    "qwen-flash":          {"name": "Qwen Flash",   "description": "极速、低成本",         "supports_thinking": True},
    "qwen-turbo":          {"name": "Qwen Turbo",   "description": "快速、低成本",         "supports_thinking": False},
}


def _model_meta(model_id: str) -> dict:
    """返回某模型 ID 的展示元信息，未知模型回退到以 ID 为名、不支持思考。"""
    meta = KNOWN_MODELS.get(model_id)
    if meta:
        return {
            "id": model_id,
            "name": meta.get("name", model_id),
            "description": meta.get("description", ""),
            "supports_thinking": bool(meta.get("supports_thinking", False)),
        }
    return {"id": model_id, "name": model_id, "description": "", "supports_thinking": False}


def get_default_model() -> str:
    """默认模型 = 配置的主模型。"""
    return get_settings().dashscope_model


def get_available_model_ids() -> list[str]:
    """可选模型 ID 列表（去重、保序）。"""
    settings = get_settings()
    raw = (settings.dashscope_models or "").strip()
    if raw:
        ids = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        ids = [settings.dashscope_model, settings.dashscope_lite_model]

    # 去重保序，并确保默认模型一定在列表里且排第一
    default = settings.dashscope_model
    ordered = [default] + [i for i in ids if i != default]
    seen, result = set(), []
    for i in ordered:
        if i and i not in seen:
            seen.add(i)
            result.append(i)
    return result


def get_available_models() -> list[dict]:
    """供前端展示的可选模型列表（含友好名称/描述/能力）。"""
    return [_model_meta(mid) for mid in get_available_model_ids()]


def resolve_model(requested: str | None) -> str:
    """把前端请求的模型 ID 收敛为合法值：

    - None / 空 / 不在白名单 → 回退默认模型（安全闸门）。
    - 合法 → 原样返回。
    """
    available = set(get_available_model_ids())
    if requested and requested in available:
        return requested
    return get_default_model()


def model_supports_thinking(model_id: str) -> bool:
    """该模型是否支持深度思考（决定是否向其发送 enable_thinking）。"""
    return _model_meta(model_id)["supports_thinking"]
