# -*- coding: utf-8 -*-
"""LLM 输出 → 确定性引擎 的校验适配层 (数值溯源校验)

VERO 红线: LLM 只做翻译器/检索器/建议器, **零数值计算权**、**不碰控制回路**。
本模块是这条红线的**执行器**:

    核心不变量 —— 回复文本中出现的每一个"数量"数值, 都必须能在
    确定性引擎 tool_call 的返回值里找到出处 (provenance)。
    找不到的数值一律拦截 (raise UnverifiableNumberError), 绝不外发。

注意区分: "V2O5"、"CF-007"、"v0.8" 这类**标识符中的数字**不是数量, 不参与校验。

依赖: 仅标准库 + pydantic (已安装)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class UnverifiableNumberError(Exception):
    """回复中存在无法溯源到 tool_call 返回的数值。

    attributes:
        unverified: 无法溯源的数值 token 列表
        report:     完整校验报告
    """

    def __init__(self, message: str, unverified: Optional[List["NumberToken"]] = None,
                 report: Optional["VerifyReport"] = None):
        super().__init__(message)
        self.unverified = unverified or []
        self.report = report


# ---------------------------------------------------------------------------
# 数值抽取
# ---------------------------------------------------------------------------

# 数值: 支持负号 / 小数 / 科学计数法
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# 标识符前缀: V2O5 / CO2 / CF-007 / v0.8 / Fe2O3 / SD_M12 —— 其中的数字不是"数量"
_ID_PREFIX_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*$")
# 序数/编号语境前缀: 第2炉 / 表3 / 图5 / §4 / 2026年
_ORDINAL_PREFIX_RE = re.compile(r"(?:第|炉|号|页|表|图|§|共|第)\s*$")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年")


@dataclass
class NumberToken:
    raw: str
    value: float
    start: int
    end: int
    skipped_as: str = ""     # ""=参与校验; "identifier"/"ordinal"=已豁免

    @property
    def verified(self) -> bool:
        return self.skipped_as == ""


@dataclass
class VerifyReport:
    text: str
    tokens: List[NumberToken] = field(default_factory=list)
    traced: List[Tuple[NumberToken, float]] = field(default_factory=list)
    unverified: List[NumberToken] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverified

    def summary(self) -> str:
        return (f"数值 {len(self.tokens)} 个 (参与校验 {len(self.traced) + len(self.unverified)}), "
                f"已溯源 {len(self.traced)}, 未溯源 {len(self.unverified)}")


def extract_numbers(text: str) -> List[NumberToken]:
    """抽取文本中的数值 token, 并标记标识符/序数类豁免项"""
    tokens: List[NumberToken] = []
    for m in _NUM_RE.finditer(text or ""):
        raw, s, e = m.group(0), m.start(), m.end()
        try:
            val = float(raw)
        except ValueError:
            continue
        before = (text or "")[:s]
        skipped = ""
        if _ID_PREFIX_RE.search(before):
            skipped = "identifier"
        elif _ORDINAL_PREFIX_RE.search(before):
            skipped = "ordinal"
        elif _YEAR_RE.search((text or "")[max(0, s - 2):e + 1]):
            skipped = "ordinal"
        tokens.append(NumberToken(raw=raw, value=val, start=s, end=e, skipped_as=skipped))
    return tokens


# ---------------------------------------------------------------------------
# 溯源比对
# ---------------------------------------------------------------------------

def _flatten_numbers(obj: Any, out: Set[float]) -> None:
    """把 tool_call 返回值(嵌套 dict/list) 里的所有数值摊平成一集合"""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _flatten_numbers(v, out)
    elif isinstance(obj, str):
        for t in _NUM_RE.finditer(obj):     # 工具返回的"带单位字符串"也认
            try:
                out.add(float(t.group(0)))
            except ValueError:
                pass


def collect_sources(tool_results: Optional[Iterable[Any]]) -> Set[float]:
    """收集所有可溯源的数值出处"""
    src: Set[float] = set()
    if not tool_results:
        return src
    for r in tool_results:
        _flatten_numbers(r, src)
    return src


def _match(value: float, sources: Sequence[float], rel: float, abs_floor: float) -> Optional[float]:
    """在出处集合中匹配: 直接相等 / 百分比换算 (×100, ÷100) 均视为同源"""
    best: Optional[float] = None
    best_err = float("inf")
    for s in sources:
        for cand in (value, value / 100.0, value * 100.0):
            err = abs(cand - s) / max(abs(s), abs_floor)
            if err <= rel and err < best_err:
                best, best_err = s, err
    return best


def verify_numbers(
    text: str,
    tool_results: Optional[Iterable[Any]],
    *,
    rel: float = 1e-6,
    abs_floor: float = 1e-9,
    raise_on_unverified: bool = True,
) -> VerifyReport:
    """校验回复文本中的数值是否全部可溯源到 tool_call 返回。

    Args:
        text: LLM 生成的回复文本
        tool_results: 本次会话中确定性引擎 tool_call 的返回(可多个)
        rel: 相对容差
        abs_floor: 绝对误差下限(防除零)
        raise_on_unverified: True(默认) 时无法溯源即 raise UnverifiableNumberError

    Returns:
        VerifyReport —— 含 traced / unverified 明细

    Raises:
        UnverifiableNumberError: 存在无法溯源的数值 (默认行为)
    """
    sources = collect_sources(tool_results)
    report = VerifyReport(text=text)

    for tok in extract_numbers(text):
        report.tokens.append(tok)
        if tok.skipped_as:
            continue                                   # 标识符/序数, 不校验
        hit = _match(tok.value, tuple(sources), rel, abs_floor)
        if hit is None:
            report.unverified.append(tok)
        else:
            report.traced.append((tok, hit))

    if raise_on_unverified and report.unverified:
        bad = ", ".join(f"'{t.raw}'@{t.start}" for t in report.unverified)
        raise UnverifiableNumberError(
            f"回复含 {len(report.unverified)} 个无法溯源到 tool_call 返回的数值: {bad}。"
            f"VERO 红线: LLM 零数值计算权, 所有数值必须来自确定性引擎。",
            unverified=report.unverified, report=report)

    return report


# ---------------------------------------------------------------------------
# pydantic 二次校验入口
# ---------------------------------------------------------------------------


def validate_with_model(payload: Any, model: type, *, strict: bool = True) -> Any:
    """pydantic 二次校验: 把 LLM 产出的 JSON 强转成引擎入参/出参模型。

    Args:
        payload: LLM 产出的 dict / JSON 字符串
        model:   pydantic BaseModel 子类 (如 app.schemas.InitialChargeInputs)
        strict:  True 时禁止隐式类型转换

    Raises:
        pydantic.ValidationError: 字段缺失或类型不合法 —— 交由调用方转为用户可懂的报错
    """
    import json

    from pydantic import BaseModel

    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError(f"model 必须是 pydantic BaseModel 子类, 收到: {model!r}")
    if isinstance(payload, str):
        payload = json.loads(payload)

    # pydantic v2
    if hasattr(model, "model_validate"):
        return model.model_validate(payload, strict=strict)
    return model.parse_obj(payload)     # pragma: no cover  (pydantic v1 兼容)
