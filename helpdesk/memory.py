"""Persist user-level preferences separately from conversation checkpoints."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


class PreferenceStore:
    def __init__(self, db_file: str | Path):
        path = Path(db_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS user_preferences (user_id TEXT PRIMARY KEY, language TEXT NOT NULL)")
        self.conn.commit()

    def get_language(self, user_id: str) -> str | None:
        row = self.conn.execute("SELECT language FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else None

    def set_language(self, user_id: str, language: str) -> None:
        if language not in {"Kazakh", "English", "Russian"}:
            raise ValueError("Unsupported demo language")
        self.conn.execute("INSERT INTO user_preferences(user_id,language) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
                          (user_id, language))
        self.conn.commit()

    def close(self):
        self.conn.close()


def explicitly_requested_language(text: str) -> str | None:
    # Learn only explicit preferences in messages, never from demo_users.json.
    if not re.search(r"\b(prefer|preference|reply|respond|answer|speak|use|remember)\b", text, re.I):
        return None
    for word in ["Kazakh", "Russian", "English"]:
        if re.search(r"\b" + re.escape(word) + r"\b", text, re.I):
            return word
    return None
