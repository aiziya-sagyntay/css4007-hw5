"""Shared helpers and local JSON fixtures (fictional data only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_data(name: str) -> dict:
    if name not in {"helpdesk.json", "service_status.json", "ticket_template.json", "scenarios.json"}:
        raise ValueError("Unknown fixture filename")
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def detect_topic(text: str) -> str | None:
    s = text.lower()
    if "wi-fi" in s or "wifi" in s:
        return "wifi"
    if "password" in s or "account recovery" in s or "account-recovery" in s:
        return "password"
    return None


def user_stated_steps(texts: list[str]) -> list[str]:
    """Conservative extraction: only report actions explicitly stated by the user.

    These patterns cover the supplied demo scenarios; they are not a general NLU parser.
    The model cannot persuade the ticket tool to write actions absent from user text.
    """
    s = " ".join(texts).lower()
    steps: list[str] = []
    if re.search(r"\b(enabl(?:e|ed|ing)|turn(?:ed)? on|switched on)\b.{0,28}\b(wi-?fi|it)\b", s):
        steps.append("Enabled Wi-Fi (user reported)")
    if re.search(r"\b(forgot|forget|removed|deleted)\b.{0,35}\b(saved network|network)\b", s):
        steps.append("Forgot/removed the saved network (user reported)")
    if re.search(r"\b(reconnect(?:ed|ing)?|tried reconnecting|connecting again)\b", s):
        steps.append("Tried reconnecting (user reported)")
    if re.search(r"\bfollowed (?:the )?instructions\b", s):
        steps.append("Followed the instructions (unspecified steps; user reported)")
    return steps


def clean_text(text: str) -> str:
    """Avoid storing accidental credential literals in a local ticket draft."""
    s = re.sub(r"(?i)(password|api[_ -]?key|recovery code)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    return s[:1200]
