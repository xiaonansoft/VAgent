# -*- coding: utf-8 -*-
"""VERO 叙述器（Narrator）—— 智能体的语言生成层

职责边界（红线友好）：只把规则引擎的结构化结论织成自然语言，**零数值计算权**——
数字全部由引擎算好传入，叙述器只选词、组句、加缓和语。双通道：配置
VERO_LLM_BASE_URL 走内网 LLM 润色（禁止改数），未配置走模板合成（离线可用）。
"""

from __future__ import annotations

import os
from typing import Any, Dict

LLM_BASE_URL = os.environ.get("VERO_LLM_BASE_URL", "")


def narrate_coolant(f: Dict[str, Any]) -> str:
    seg = []
    if f.get("mins_to_cross") is not None:
        seg.append(f"按现在的升温势头，大约 {f['mins_to_cross']:.1f} 分钟后熔池就会冲过碳钒转化温度（{f['now_tc']:.0f}℃）")
    else:
        seg.append(f"熔池已经站上碳钒转化温度（{f['now_tc']:.0f}℃）")
    seg.append(f"这会儿余钒还有 {f['est_v']:.3f}%，正是钒最经不起烧的时候")
    w = f.get("window_s")
    if w:
        seg.append(f"留给我们的窗口大约 {w:.0f} 秒")
    return f"{'，'.join(seg)}。建议马上从称量斗补 {f['kg']:.0f} 公斤球团压一压——采不采，炉长定。"


def narrate_replan(reason: str, action: str) -> str:
    return f"情况有变（{reason}），我把计划调整了一下：{action}。"


def narrate_reject(title: str, reason: str) -> str:
    r = f"（理由：{reason}）" if reason else ""
    return f"炉长否决了「{title}」{r}——记下了，我按这个口径调整后面的判断。"


def narrate_takeover(f: Dict[str, Any]) -> str:
    return (f"余钒 {f['est_v']:.3f}%，进入收口区；温度 {f['est_T']:.0f}℃ 在窗内、"
            f"碳也守得住——提枪参考窗已经挂上，什么时候提枪听炉长的。")


def llm_polish(text: str) -> str:
    """预留内网 LLM 润色：未配置原样返回；异常回退模板句——不阻塞、不编造。"""
    if not LLM_BASE_URL:
        return text
    try:
        import json as _json
        from urllib import request as _rq
        req = _rq.Request(
            LLM_BASE_URL.rstrip("/") + "/chat/completions",
            data=_json.dumps({"messages": [
                {"role": "system", "content": "你是提钒炉前智能体的文案层。只改写表达使其更口语，"
                                              "禁止修改任何数字、结论与建议方向，禁止添加新事实。"},
                {"role": "user", "content": text}]}).encode(),
            headers={"Content-Type": "application/json"})
        with _rq.urlopen(req, timeout=3) as resp:
            return _json.loads(resp.read())["choices"][0]["message"]["content"]
    except Exception:
        return text
