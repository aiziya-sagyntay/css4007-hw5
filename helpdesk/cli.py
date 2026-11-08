"""Command-line entry points. Example: python -m helpdesk.cli run-scenarios --mode real"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import HelpdeskSession
from .common import ROOT
from .part1 import run_part1
from .tools import ToolContext, make_tools

load_dotenv(ROOT / ".env")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


def cmd_batch(args):
    """One OS process for a consecutive segment of conversation events."""
    events = json.loads(Path(args.events_file).read_text(encoding="utf-8"))
    responses = []
    with contextlib.ExitStack() as stack:
        sessions = {}
        for event in events:
            if event.get("action") != "message":
                raise ValueError("batch only accepts message events")
            key = (event["user_id"], event["thread_id"])
            if key not in sessions:
                sessions[key] = stack.enter_context(HelpdeskSession(
                    key[0], key[1], args.profile, args.storage, args.mode, args.model))
            response = sessions[key].respond(event["message"])
            response["pid"] = os.getpid()
            responses.append(response)
    print(json.dumps({"pid": os.getpid(), "responses": responses}, ensure_ascii=False))


def cmd_chat(args):
    print(f"DEMO helpdesk | user={args.user} | thread={args.thread} | profile={args.profile} | mode={args.mode}")
    print("Type /exit to finish. Do not enter passwords or secrets.")
    with HelpdeskSession(args.user, args.thread, args.profile, args.storage, args.mode, args.model) as app:
        while True:
            try:
                message = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if message in {"/exit", "/quit"}:
                break
            if not message:
                continue
            result = app.respond(message)
            print("Helpdesk:", result["final_reply"])
            print("Nodes:", " -> ".join(x["node"] for x in result["trace"]))
            if result["ticket_files"]:
                print("LOCAL TICKET:", ", ".join(result["ticket_files"]))


def cmd_direct_tools(args):
    """Proof that all 3 tools work independently of any LLM."""
    ctx = ToolContext(user_id="demo-user-a", thread_id="direct", status_profile=args.profile,
                      storage_dir=Path(args.storage),
                      user_history=["My Wi-Fi fails. I enabled Wi-Fi and tried reconnecting."])
    instructions, status, draft = make_tools(ctx)
    results = {
        "find_instructions": json.loads(instructions.invoke({"topic": "wifi"})),
        "check_service_status": json.loads(status.invoke({"service": "wifi"})),
        "prepare_ticket": json.loads(draft.invoke({"category": "wifi",
                                                   "problem_description": ctx.user_history[-1],
                                                   "steps_tried": ["Enabled Wi-Fi", "tried reconnecting"]})),
    }
    print(json.dumps(results, indent=2, ensure_ascii=False))


def main(argv=None):
    p = argparse.ArgumentParser(description="CSS4007 HW5 fictional LangGraph helpdesk")
    sub = p.add_subparsers(dest="command", required=True)
    one = sub.add_parser("part1", help="Run original or modified deterministic routing graph")
    one.add_argument("--message", required=True)
    one.add_argument("--variant", choices=["original", "with_clarification"], default="original")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mode", choices=["real", "fake"], default="real")
    common.add_argument("--profile", default="normal",
                        choices=["normal", "wifi_outage", "recovery_outage", "status_unavailable"])
    common.add_argument("--storage", default=str(ROOT / "local-storage"))
    common.add_argument("--model", default=None)

    chat = sub.add_parser("chat", parents=[common], help="Start interactive multi-turn conversation")
    chat.add_argument("--user", required=True)
    chat.add_argument("--thread", required=True)
    batch = sub.add_parser("batch", parents=[common], help="Internal child-process scenario runner")
    batch.add_argument("--events-file", required=True)
    direct = sub.add_parser("direct-tools", parents=[common], help="Independently invoke all tools")
    run = sub.add_parser("run-scenarios", parents=[common], help="Replay S01-S14 and save execution logs")
    run.add_argument("--ids", nargs="*", default=None, help="Optional selected IDs, e.g. S06 S07")
    report = sub.add_parser("report", help="Rebuild SUBMISSION.md from ACTUAL saved logs")
    report.add_argument("--mode", choices=["real", "fake"], default="real")
    args = p.parse_args(argv)

    if args.command == "part1":
        print(json.dumps(run_part1(args.message, args.variant == "with_clarification"),
                         indent=2, ensure_ascii=False))
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "direct-tools":
        cmd_direct_tools(args)
    elif args.command == "run-scenarios":
        from .runner import run_all
        summary = run_all(mode=args.mode, ids=args.ids,
                          base_storage=Path(args.storage), model_name=args.model)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif args.command == "report":
        from .report import generate_submission
        print(generate_submission(args.mode))


if __name__ == "__main__":
    main()
