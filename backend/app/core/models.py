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

# 「自动」伪模型：前端可选，但不是真实模型 ID。
# 选它时后端按问题复杂度路由到 lite 或主模型（见 route_model）。
AUTO_MODEL = "auto"
_AUTO_META = {
    "id": AUTO_MODEL,
    "name": "自动",
    "description": "简单问题用轻量模型省钱，复杂问题用强模型",
    "supports_thinking": True,  # 思考是否真正生效由后端按实际路由到的模型再判定
}

# 寒暄 / 元问题关键词：命中且消息很短时判为「简单」，走 lite 模型。
# 偏保守：除明显闲聊外一律按复杂处理，避免把真实询价降级到弱模型。
_CHITCHAT_KEYWORDS = (
    "你好", "您好", "哈喽", "嗨", "谢谢", "多谢", "感谢", "辛苦", "再见", "拜拜",
    "你是谁", "你叫什么", "你能做什么", "你会什么", "怎么用", "在吗", "在不在",
    "hello", "hi", "hey", "thanks", "thank you",
)

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
    """默认模型 = 「自动」档（前端默认选中它，按问题复杂度路由）。

    注意：route_model 的 auto 分支直接用 settings.dashscope_model 作为强模型，
    不依赖本函数，因此这里返回 auto 不会造成循环。
    """
    return AUTO_MODEL


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
    """供前端展示的可选模型列表（含友好名称/描述/能力）。

    首位插入「自动」伪模型，供用户选择由系统按复杂度路由。
    """
    return [_AUTO_META] + [_model_meta(mid) for mid in get_available_model_ids()]


def resolve_model(requested: str | None) -> str:
    """把前端请求的模型 ID 收敛为合法值：

    - "auto" → 原样返回（由 route_model 在请求时解析为具体模型）。
    - None / 空 / 不在白名单 → 回退默认模型（安全闸门）。
    - 合法 → 原样返回。
    """
    if requested == AUTO_MODEL:
        return AUTO_MODEL
    available = set(get_available_model_ids())
    if requested and requested in available:
        return requested
    return get_default_model()


def _is_simple_query(message: str) -> bool:
    """轻量启发式判断是否为「简单」问题（寒暄/元问题）。

    偏保守：仅当消息很短且命中寒暄词时判为简单，其余一律视为复杂，
    避免把真实询价请求降级到弱模型。
    """
    m = (message or "").strip().lower().rstrip("?？!！。.~ ")
    if not m:
        return True
    if len(m) <= 12 and any(k in m for k in _CHITCHAT_KEYWORDS):
        return True
    return False


def route_model(requested: str | None, message: str) -> str:
    """把请求模型（含 auto）解析为实际调用的具体模型 ID（永不返回 "auto"）。

    - requested == "auto"：简单问题 → lite 模型，复杂问题 → 主模型。
    - 其他：尊重用户显式选择（经 resolve_model 校验）。
    """
    resolved = resolve_model(requested)
    if resolved == AUTO_MODEL:
        settings = get_settings()
        return settings.dashscope_lite_model if _is_simple_query(message) else settings.dashscope_model
    return resolved


def model_supports_thinking(model_id: str) -> bool:
    """该模型是否支持深度思考（决定是否向其发送 enable_thinking）。"""
    return _model_meta(model_id)["supports_thinking"]
