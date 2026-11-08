"""Additional real conversation-memory demonstration."""

import argparse
import json
import shutil

from .agent import HelpdeskSession
from .common import ROOT


def run_demo(mode="real"):
    output = ROOT / "outputs"
    if mode == "fake":
        output = output / "fake"
    output.mkdir(parents=True, exist_ok=True)

    storage = ROOT / "local-storage" / f"extra-memory-{mode}"
    if storage.exists():
        shutil.rmtree(storage)

    with HelpdeskSession(
        "demo-user-a",
        "literal-that-thread",
        "normal",
        storage,
        mode=mode
    ) as app:

        first = app.respond(
            "I cannot connect to Wi-Fi. "
            "Find the local Wi-Fi instructions "
            "and recommend only the first step."
        )

        second = app.respond("I already tried that.")

    guides = [
        message.get("tool_result")
        for row in first["trace"]
        for message in row.get("messages_added", [])
        if message.get("tool_name") == "find_instructions"
    ]

    previous = second["trace"][0]["previous_conversation_messages"]

    checks = {
        "guide_retrieved": bool(guides),
        "previous_messages_loaded": previous > 0,
        "no_unrequested_ticket": len(second["ticket_files"]) == 0,
        "no_loop_limit": not second["loop_limit_hit"]
    }

    log = {
        "title": "Literal contextual memory demonstration",
        "mode": mode,
        "model": first["model"],
        "user_id": "demo-user-a",
        "thread_id": "literal-that-thread",
        "messages": [first, second],
        "reference_retrieval": {
            "source": "data/helpdesk.json",
            "results": guides
        },
        "conversation_memory": {
            "source": "LangGraph SQLite checkpoint",
            "previous_messages": previous
        },
        "user_memory": {
            "source": "preferences.sqlite",
            "preferred_language": second["preferred_language"]
        },
        "checks": checks
    }

    path = output / "EXTRA_MEMORY_REFERENCE.json"
    path.write_text(
        json.dumps(log, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("FIRST ANSWER:", first["final_reply"])
    print("SECOND ANSWER:", second["final_reply"])
    print("CHECKS:", checks)
    print("SAVED:", path)

    return log


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["real", "fake"], default="real")
    args = parser.parse_args()
    run_demo(args.mode)
