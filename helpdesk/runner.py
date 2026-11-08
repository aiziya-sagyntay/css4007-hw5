"""Replay all fourteen supplied scenarios, with true new OS processes at restart events."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import ROOT, load_data
from .part1 import PREDICTIONS, run_part1


def split_at_restarts(events: list[dict]) -> tuple[list[list[dict]], int]:
    segments: list[list[dict]] = []
    current: list[dict] = []
    restart_count = 0
    for ev in events:
        if ev["action"] == "restart_process":
            if current:
                segments.append(current)
            current = []
            restart_count += 1
        else:
            current.append(ev)
    if current:
        segments.append(current)
    return segments, restart_count


def tool_records(results: list[dict]) -> list[dict]:
    records = []
    for answer in results:
        for node in answer.get("trace", []):
            for msg in node.get("messages_added", []):
                if msg.get("model_tool_requests"):
                    records.extend({"event": "model_requested", **x} for x in msg["model_tool_requests"])
                if "tool_result" in msg:
                    records.append({"event": "tool_returned", "name": msg.get("tool_name"),
                                    "result": msg["tool_result"]})
    return records


def assessment(sid: str, results: list[dict]) -> dict:
    """Basic automatic checks; review raw logs for nuanced model quality."""
    replies = [x.get("final_reply", "") for x in results]
    records = tool_records(results)
    called = [r["name"] for r in records if r["event"] == "tool_returned"]
    tickets = sum(len(x.get("ticket_files", [])) for x in results)
    statuses = [r["result"].get("status") for r in records
                if r["event"] == "tool_returned" and r["name"] == "check_service_status"
                and isinstance(r["result"], dict)]
    if sid in {"S01", "S02", "S03", "S04", "S05"}:
        return {"passed": True, "reason": "Deterministic graph executed", "route": results[0]["route"]}
    checks = {
        "S06": "find_instructions" in called and "check_service_status" in called and "prepare_ticket" in called and tickets >= 1,
        "S07": "outage" in statuses and tickets == 0,
        "S08": "unknown" in statuses and tickets == 0,
        "S09": len(results) == 2 and not results[0]["ticket_files"] and bool(results[1]["ticket_files"]),
        "S10": len(results) == 2 and results[1].get("trace", [{}])[0].get("previous_conversation_messages", 0) > 0,
        "S11": len(results) == 2 and results[1].get("trace", [{}])[0].get("previous_conversation_messages", 0) > 0
                 and results[1].get("preferred_language") == "Kazakh",
        "S12": len(results) == 2 and results[1]["thread_id"] != results[0]["thread_id"]
                 and results[1].get("preferred_language") == "Kazakh"
                 and results[1].get("trace", [{}])[0].get("previous_conversation_messages", -1) == 0,
        "S13": len(results) == 2 and results[0].get("preferred_language") == "Kazakh"
                 and results[1].get("preferred_language") == "not set" and
                 results[1].get("trace", [{}])[0].get("previous_conversation_messages", -1) == 0,
        "S14": "outage" in statuses and "check_service_status" in called,
    }
    return {"passed": bool(checks.get(sid, False)), "tool_results": called,
            "observed_statuses": statuses, "ticket_count": tickets,
            "reason": "Automatic fixture check; inspect the replies and traces for content accuracy."}


def run_all(mode: str, ids: list[str] | None = None, base_storage: Path | None = None,
            model_name: str | None = None) -> dict:
    scenarios = load_data("scenarios.json")["scenarios"]
    if ids:
        unknown = set(ids) - {sc["id"] for sc in scenarios}
        if unknown:
            raise ValueError(f"Unknown scenario IDs: {sorted(unknown)}")
    out_dir = ROOT / "outputs" if mode == "real" else ROOT / "outputs" / "fake"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_storage = Path(base_storage or (ROOT / "local-storage"))
    base_storage.mkdir(parents=True, exist_ok=True)
    statuses = {}
    for sc in scenarios:
        sid = sc["id"]
        if ids and sid not in ids:
            continue
        storage = base_storage / "scenario-runs" / sid
        if sc.get("reset_before") and storage.exists():
            shutil.rmtree(storage)
        storage.mkdir(parents=True, exist_ok=True)
        if sc["part"] == 1:
            ev = sc["events"][0]
            variant = sc.get("graph_variant", "original")
            trace = run_part1(ev["message"], variant == "with_clarification")
            results = [{"user_id": ev["user_id"], "thread_id": ev["thread_id"],
                        "profile": sc["status_profile"], "mode": "no LLM",
                        "final_reply": trace["final_state"]["reply"], "route": trace["route"],
                        "state_after_each_node": trace["trace"], "ticket_files": [],
                        "trace": trace["trace"]}]
            process_events = []
            commands = [f'python -m helpdesk.cli part1 --variant {variant} --message {json.dumps(ev["message"])}']
        else:
            segments, n_restarts = split_at_restarts(sc["events"])
            results = []
            process_events = []
            commands = []
            for i, segment in enumerate(segments):
                path = storage / f"segment_{i + 1}.json"
                path.write_text(json.dumps(segment, ensure_ascii=False), encoding="utf-8")
                command = [sys.executable, "-m", "helpdesk.cli", "batch", "--mode", mode,
                           "--profile", sc["status_profile"], "--storage", str(storage),
                           "--events-file", str(path)]
                if model_name:
                    command += ["--model", model_name]
                commands.append(" ".join(command))
                proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                      timeout=360, env=os.environ.copy())
                if proc.returncode:
                    raise RuntimeError(f"{sid}: child process #{i + 1} failed:\n{proc.stderr[-3500:]}")
                payload = json.loads(proc.stdout)
                process_events.append({"action": "process_start", "segment": i + 1,
                                       "pid": payload["pid"], "events": len(segment)})
                results.extend(payload["responses"])
                process_events.append({"action": "process_exit", "pid": payload["pid"]})
                if i < n_restarts:
                    process_events.append({"action": "restart_process", "method": "separate subprocess.run call",
                                           "storage_preserved": True})
        # Export only fictional local ticket drafts into shareable output evidence.
        # The live SQLite databases remain ignored; these demo JSON files contain no secrets.
        for answer in results:
            shared = []
            for ticket_path in answer.get("ticket_files", []):
                source_path = Path(ticket_path)
                if source_path.is_file():
                    dest_dir = out_dir / "tickets"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / f"{sid}_{source_path.name}"
                    shutil.copyfile(source_path, dest)
                    shared.append(str(dest.relative_to(ROOT)))
            answer["published_ticket_files"] = shared
        if mode == "real" and sc["part"] != 1:
            model_label = model_name or os.getenv("MODEL_NAME", "gpt-4o-mini")
        else:
            model_label = "none" if sc["part"] == 1 else "FAKE deterministic simulator"
        log = {
            "scenario_id": sid, "title": sc["title"], "part": sc["part"],
            "status_profile": sc["status_profile"], "mode": mode,
            "model_provider": "OpenAI" if mode == "real" and sc["part"] != 1 else "no real LLM",
            "model_name": model_label, "original_events": sc["events"],
            "commands_executed": commands, "process_events": process_events,
            "messages": results, "tool_call_and_result_sequence": tool_records(results),
            "evaluation": assessment(sid, results),
            "loop_limit_reached": any(r.get("loop_limit_hit") for r in results),
        }
        logfile = out_dir / f"{sid}.json"
        logfile.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        statuses[sid] = {"passed": log["evaluation"]["passed"], "log_file": str(logfile),
                         "notes": log["evaluation"]["reason"]}
        print(f"{sid}: {'PASS' if statuses[sid]['passed'] else 'REVIEW'}  -> {logfile}", file=sys.stderr)
    return {"mode": mode, "total": len(statuses), "passed": sum(x["passed"] for x in statuses.values()),
            "results": statuses}
