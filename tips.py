"""Productivity tips for pomodoro breaks, and the break card contract with Unblockbrücke.

Built-in tips ship as `data/tips.json` (loaded at import); the user's own tips live in the toolbox
file. `break_tip()` asks Unblockbrücke for a card when its tool `unblockbruecke_card` is registered:
`{"action": "draw", "context": "break"}` must answer `{"title": str, "text": str}` (JSON). Any error,
a wrong shape or no answer falls back to a tip. This contract is Eselsbrücke's; Unblockbrücke adopts
it when that track is built.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Callable, Optional

CARD_TOOL = "unblockbruecke_card"
CARD_ARGS = {"action": "draw", "context": "break"}


def _load() -> list[dict]:
    data = json.loads((Path(__file__).resolve().parent / "data" / "tips.json").read_text(encoding="utf-8"))
    return [{**t, "source": "builtin"} for t in data["tips"]]


BUILTIN = _load()


def all_tips(user_tips: Optional[list] = None) -> list[dict]:
    own = [{"id": t.get("id"), "title": t["title"], "why": t.get("why", ""), "source": "user"}
           for t in (user_tips or []) if isinstance(t, dict) and t.get("title")]
    return BUILTIN + own


def pick_tip(user_tips: Optional[list] = None, seed: Optional[int] = None) -> dict:
    tips = all_tips(user_tips)
    i = (seed if seed is not None else secrets.randbelow(10_000)) % len(tips)
    return tips[i]


def break_tip(has_tool: Callable[[str], bool], dispatch: Callable[[str, dict], Any],
              user_tips: Optional[list] = None, seed: Optional[int] = None) -> dict:
    """{"source": "unblockbruecke"|"builtin"|"user", "title", "text"}; never raises."""
    try:
        if has_tool(CARD_TOOL):
            answer = dispatch(CARD_TOOL, dict(CARD_ARGS))
            if isinstance(answer, str):
                answer = json.loads(answer)
            if (isinstance(answer, dict) and isinstance(answer.get("title"), str) and answer["title"].strip()
                    and isinstance(answer.get("text"), str)):
                return {"source": "unblockbruecke", "title": answer["title"][:200], "text": answer["text"][:600]}
    except Exception:
        pass
    tip = pick_tip(user_tips, seed)
    return {"source": tip["source"], "title": tip["title"], "text": tip.get("why", "")}
