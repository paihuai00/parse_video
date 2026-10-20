"""Domain errors and their stable public contract."""

from __future__ import annotations

from dataclasses import dataclass

MESSAGES = {
    "INVALID_REQUEST": "请求内容不符合接口要求。",
    "INVALID_URL": "链接不是受支持的小红书笔记地址。",
    "UNAUTHORIZED": "API Key 缺失或无效。",
    "NOTE_NOT_FOUND": "小红书笔记不存在或已不可见。",
    "ROUTE_NOT_FOUND": "请求的接口不存在。",
    "METHOD_NOT_ALLOWED": "该接口不支持此请求方法。",
    "INPUT_TOO_LARGE": "请求体超过允许的大小。",
    "UNSUPPORTED_CONTENT": "该笔记包含当前版本不支持的媒体类型。",
    "RATE_LIMITED": "请求过于频繁，请稍后重试。",
    "INTERNAL_ERROR": "服务发生未预期错误。",
    "UPSTREAM_BAD_RESPONSE": "小红书返回了无法处理的响应。",
    "PARSE_FAILED": "页面结构暂时无法解析。",
    "MEDIA_NOT_FOUND": "笔记中没有找到受支持的媒体。",
    "BUSY": "服务当前繁忙，请稍后重试。",
    "UPSTREAM_LOGIN_REQUIRED": "小红书当前要求登录，无法匿名获取该笔记。",
    "UPSTREAM_ACCESS_RESTRICTED": "小红书要求完成访问验证。",
    "UPSTREAM_RATE_LIMITED": "小红书暂时限制了访问频率。",
    "UPSTREAM_TIMEOUT": "获取或解析小红书页面超时。",
}

UNIFIED_MESSAGES = {
    **MESSAGES,
    "INVALID_URL": "链接不是受支持的小红书或抖音作品地址。",
    "NOTE_NOT_FOUND": "目标作品不存在或已不可见。",
    "UNSUPPORTED_CONTENT": "该作品包含当前版本不支持的媒体类型。",
    "UPSTREAM_BAD_RESPONSE": "内容平台返回了无法处理的响应。",
    "MEDIA_NOT_FOUND": "作品中没有找到受支持的媒体。",
    "UPSTREAM_LOGIN_REQUIRED": "内容平台当前要求登录，无法匿名获取该作品。",
    "UPSTREAM_ACCESS_RESTRICTED": "内容平台要求完成访问验证。",
    "UPSTREAM_RATE_LIMITED": "内容平台暂时限制了访问频率。",
    "UPSTREAM_TIMEOUT": "获取或解析作品页面超时。",
}


@dataclass
class AppError(Exception):
    code: str
    status_code: int
    retryable: bool = False
    detail: str = ""
    retry_after: int | None = None

    @property
    def public_message(self) -> str:
        return MESSAGES[self.code]


def invalid_url(detail: str) -> AppError:
    return AppError("INVALID_URL", 400, detail=detail)
