"""Additional API-free memory tests."""

import json
import os
import subprocess
import sys

from helpdesk.agent import HelpdeskSession
from helpdesk.common import ROOT


def test_literal_followup(tmp_path):
    with HelpdeskSession(
        "demo-user-a", "test-thread", "normal",
        tmp_path, mode="fake"
    ) as app:

        first = app.respond(
            "I cannot connect to Wi-Fi. "
            "Please show Wi-Fi instructions."
        )
        second = app.respond("I already tried that.")

    assert second["trace"][0]["previous_conversation_messages"] > 0
    assert "earlier Wi-Fi instructions" in second["final_reply"]
    assert second["ticket_files"] == []


def test_literal_followup_without_context(tmp_path):
    with HelpdeskSession(
        "demo-user-a", "empty-thread", "normal",
        tmp_path, mode="fake"
    ) as app:
        result = app.respond("I already tried that.")

    assert result["trace"][0]["previous_conversation_messages"] == 0
    assert "clarify" in result["final_reply"].lower()


def test_memory_survives_real_process_restart(tmp_path):
    storage = tmp_path / "persistent-storage"
    pids = []
    results = []

    segments = [
        [{
            "action": "message",
            "user_id": "demo-user-a",
            "thread_id": "restart-thread",
            "message": (
                "My Wi-Fi does not work. "
                "I enabled Wi-Fi and tried reconnecting."
            )
        }],
        [{
            "action": "message",
            "user_id": "demo-user-a",
            "thread_id": "restart-thread",
            "message": "Which problem and steps did we discuss?"
        }]
    ]

    for i, events in enumerate(segments):
        path = tmp_path / f"segment_{i}.json"
        path.write_text(json.dumps(events), encoding="utf-8")

        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env["LANGSMITH_TRACING"] = "false"
        env["LANGGRAPH_STRICT_MSGPACK"] = "true"

        process = subprocess.run(
            [
                sys.executable, "-m", "helpdesk.cli",
                "batch",
                "--mode", "fake",
                "--storage", str(storage),
                "--events-file", str(path)
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )

        payload = json.loads(process.stdout)
        pids.append(payload["pid"])
        results.extend(payload["responses"])

    assert pids[0] != pids[1]
    assert results[1]["trace"][0]["previous_conversation_messages"] > 0
    assert "reconnect" in results[1]["final_reply"].lower()
