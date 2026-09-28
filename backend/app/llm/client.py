# -*- coding: utf-8 -*-
"""DeepSeek / OpenAI 兼容 LLM 客户端封装 (离线可运行)

VERO 红线: LLM 只做翻译器/检索器/建议器, **零数值计算权**、**不碰控制回路**。
本模块只负责"发请求 / 收文本 / 记 token", 不做任何业务计算; 且当环境没有
API Key 时, 所有调用自动走 `dry_run` 返回结构化占位, **不抛异常**, 保证工程
可完全离线运行。

环境变量 (不写死任何 Key):
    DEEPSEEK_API_KEY    API Key; 为空则 LLM 关闭 (dry_run)
    VERO_LLM_BASE_URL  兼容端点, 默认 https://api.deepseek.com/v1
    VERO_LLM_MODEL     模型名, 默认 deepseek-chat
    VERO_LLM_TIMEOUT   单次请求超时秒, 默认 15
    VERO_LLM_MAX_RETRIES  最大重试次数, 默认 2 (指数退避)

依赖: 仅标准库 (urllib)。未引入 openai / httpx —— 如需更强的流式/异步能力,
      TODO(待安装): `pip install openai httpx` 后替换 `_http_post` 实现即可,
      接口签名不变。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """LLM 调用失败 (网络/协议/超时)。LLM 关闭时不会抛此异常。"""


class LLMDisabled(Exception):
    """LLM 功能关闭标记。

    语义: 环境无 API Key 时, 客户端处于 dry_run 模式。对外**不会**抛出,
    仅在显式要求"必须有真模型"的场景 (如 `require_real=True`) 下抛出。
    """


# ---------------------------------------------------------------------------
# 配置与数据结构
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_RETRIES = 2


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    temperature: float = 0.2
    max_tokens: int = 1024

    @classmethod
    def from_env(cls) -> "LLMConfig":
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, "") or default)
            except ValueError:
                return default

        return cls(
            api_key=(os.getenv("DEEPSEEK_API_KEY") or "").strip(),
            base_url=(os.getenv("VERO_LLM_BASE_URL") or DEFAULT_BASE_URL).strip(),
            model=(os.getenv("VERO_LLM_MODEL") or DEFAULT_MODEL).strip(),
            timeout_s=_f("VERO_LLM_TIMEOUT", DEFAULT_TIMEOUT_S),
            max_retries=int(_f("VERO_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"


@dataclass
class ChatMessage:
    role: str = "user"          # system | user | assistant | tool
    content: str = ""
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ChatResponse:
    content: str
    model: str
    dry_run: bool = False
    finish_reason: str = "stop"
    raw: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Token 计量桩
# ---------------------------------------------------------------------------


class UsageMeter:
    """token 计量桩。

    真实用量优先取响应 `usage` 字段; 缺失时按字符数启发式估算
    (中文 ~1.5 char/token, 英文 ~4 char/token), 仅用于成本核算的粗略量级,
    不作为结算依据。
    TODO(接真 Key 后): 换成 tokenizer 精确计数 (待安装 tiktoken)。
    """

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.calls = 0
        self.dry_run_calls = 0
        self.errors = 0

    def add(self, usage: Optional[Dict[str, int]] = None) -> None:
        u = usage or {}
        self.prompt_tokens += int(u.get("prompt_tokens", 0))
        self.completion_tokens += int(u.get("completion_tokens", 0))
        self.total_tokens += int(u.get("total_tokens", 0)
                                 or self.prompt_tokens + self.completion_tokens)

    @staticmethod
    def estimate(text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        ascii_len = len(text) - cjk
        return int(cjk / 1.5 + ascii_len / 4) + 1

    def snapshot(self) -> Dict[str, int]:
        return {
            "calls": self.calls,
            "dry_run_calls": self.dry_run_calls,
            "errors": self.errors,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

DRY_RUN_TEMPLATE = (
    "[dry_run · LLM 未启用: 未配置 DEEPSEEK_API_KEY]\n"
    "本回复为结构化占位, 未产生任何数值。真实上线后由 tool_call 返回权威数值。\n"
    "用户问题: {question}\n"
    "建议动作: 调用确定性引擎工具获取数值后再作答 (见 app.llm.router)。"
)


class LLMClient:
    """DeepSeek/OpenAI 兼容 Chat Completions 客户端。

    * 无 Key → `enabled=False`, 所有调用返回 dry_run 占位, 不抛异常。
    * 超时默认 15s, 失败重试最多 2 次, 退避 0.5s → 1.0s → 2.0s。
    * 只做传输层, 不做任何计算。
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.usage = UsageMeter()

    # -- 状态 ---------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def require_real(self) -> None:
        """显式要求真模型 (生产链路用)。关闭时抛 LLMDisabled。"""
        if not self.enabled:
            raise LLMDisabled(
                "LLM 未启用: 未配置 DEEPSEEK_API_KEY。请配置后重试, "
                "或接受 dry_run 占位回复。"
            )

    # -- 主入口 -------------------------------------------------------------
    def chat(
        self,
        messages: Iterable[ChatMessage] | Iterable[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        msgs = [m if isinstance(m, dict) else m.to_dict() for m in messages]
        if not self.enabled:
            return self._dry_run(msgs)

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": msgs,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        t0 = time.time()
        last_err: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                raw = self._http_post(payload)
                self.usage.calls += 1
                self.usage.add(raw.get("usage"))
                return self._parse(raw, int((time.time() - t0) * 1000))
            except Exception as e:                       # 网络/超时/协议
                last_err = e
                self.usage.errors += 1
                if attempt < self.config.max_retries:
                    time.sleep(0.5 * (2 ** attempt))     # 指数退避
                continue

        # 全部重试失败: 降级为 dry_run 占位, 保证工程不中断
        self.usage.dry_run_calls += 1
        return ChatResponse(
            content=("[dry_run · LLM 调用失败已降级] " + str(last_err) + "\n"
                     + DRY_RUN_TEMPLATE.format(question=self._last_user(msgs))),
            model=self.config.model, dry_run=True, finish_reason="error",
        )

    def complete(self, prompt: str, **kw) -> ChatResponse:
        return self.chat([ChatMessage(role="user", content=prompt)], **kw)

    # -- 内部 ---------------------------------------------------------------
    def _dry_run(self, msgs: List[Dict[str, Any]]) -> ChatResponse:
        self.usage.calls += 1
        self.usage.dry_run_calls += 1
        q = self._last_user(msgs)
        est = UsageMeter.estimate(q)
        self.usage.add({"prompt_tokens": est, "completion_tokens": 0, "total_tokens": est})
        return ChatResponse(
            content=DRY_RUN_TEMPLATE.format(question=q),
            model=self.config.model, dry_run=True, finish_reason="dry_run",
        )

    @staticmethod
    def _last_user(msgs: List[Dict[str, Any]]) -> str:
        for m in reversed(msgs):
            if m.get("role") == "user":
                return str(m.get("content", ""))[:500]
        return ""

    def _http_post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.config.chat_url(),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"网络错误: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise LLMError(f"响应非 JSON: {e}") from e

    def _parse(self, raw: Dict[str, Any], latency_ms: int) -> ChatResponse:
        try:
            choice = (raw.get("choices") or [{}])[0]
        except IndexError:
            raise LLMError(f"响应缺少 choices: {str(raw)[:300]}")
        msg = choice.get("message") or {}
        return ChatResponse(
            content=msg.get("content") or "",
            model=raw.get("model", self.config.model),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=raw,
            tool_calls=msg.get("tool_calls") or [],
            usage=raw.get("usage") or {},
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------

_CLIENT: Optional[LLMClient] = None


def get_client(config: Optional[LLMConfig] = None, *, reload: bool = False) -> LLMClient:
    """获取进程内默认客户端 (离线场景下为 dry_run 客户端)"""
    global _CLIENT
    if _CLIENT is None or reload or config is not None:
        _CLIENT = LLMClient(config or LLMConfig.from_env())
    return _CLIENT


def is_enabled() -> bool:
    return get_client().enabled
