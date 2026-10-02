# -*- coding: utf-8 -*-
"""一次性迁移：把存量 agent_memory.json 里 uuid 形态的 heat_id 规整为可读炉号。

背景：`session.py` 历史上用 `self.id`（uuid）作为 heat_id 写入记忆，导致
记忆条目形如 `heat_id: "03dd2c87ba11"`。这类标签在界面上无法被炉长识别，
"跨炉记忆"演示时无法回答"这是哪一炉的经验"，记忆沦为表演。

本脚本：
- 只重写 heat_id 字段，不触碰 content / confidence / kind / scenario（结论不可改）
- 无法推断真实炉号时，保守地标为 `第?炉`（保留 uuid 到 legacy_id 字段可溯）
- 默认 dry-run；加 --apply 才落盘；落盘前自动备份

用法：
    python3 scripts/migrate_memory_heatid.py            # 预演
    python3 scripts/migrate_memory_heatid.py --apply    # 落盘
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM_PATH = os.environ.get(
    "VERO_AGENT_MEMORY",
    os.path.join(REPO, "knowledge", "data", "private", "agent_memory.json"))

UUID_RE = re.compile(r"^[0-9a-f]{8,32}$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写盘（默认 dry-run）")
    args = ap.parse_args()

    if not os.path.exists(MEM_PATH):
        print(f"[skip] 记忆文件不存在: {MEM_PATH}")
        return 0

    with open(MEM_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    changed = 0
    for i, it in enumerate(items, start=1):
        hid = str(it.get("heat_id", ""))
        if UUID_RE.match(hid):
            it["legacy_id"] = hid            # 原始 uuid 留痕，可回溯
            it["heat_id"] = f"第?炉"         # 真实炉号不可从 uuid 反推，保守标注
            changed += 1

    print(f"[scan] 共 {len(items)} 条，需规整 {changed} 条")
    if not changed:
        print("[ok] 无需迁移")
        return 0

    if not args.apply:
        print("[dry-run] 未写盘。确认后加 --apply")
        for it in items[:5]:
            print(f"   {it.get('id')} kind={it.get('kind')} "
                  f"heat_id: {it.get('legacy_id', '?')} -> {it['heat_id']}")
        return 0

    bak = MEM_PATH + f".bak.{datetime.now():%Y%m%d%H%M%S}"
    shutil.copy2(MEM_PATH, bak)
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print(f"[apply] 已迁移 {changed} 条，备份: {bak}")
    print("[note] 存量炉号为「第?炉」：uuid 无法反推真实炉号。")
    print("       建议在真实台账接入后按时间序重标，未标注条目仍可正常使用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
