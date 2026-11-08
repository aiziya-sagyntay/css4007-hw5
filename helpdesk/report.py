"""Fill SUBMISSION.md based on actual saved observations (no fabricated model results)."""
from __future__ import annotations

import json
import platform
from pathlib import Path

from .common import ROOT, load_data
from .part1 import PREDICTIONS


PART1_GRAPH = """```mermaid
flowchart LR
    START --> read_request
    read_request -->|wifi / wi-fi| wifi_help
    read_request -->|password| password_help
    read_request -->|other| other_help
    wifi_help --> END
    password_help --> END
    other_help --> END
```"""
CHANGED_GRAPH = """```mermaid
flowchart LR
    START --> read_request
    read_request -->|both| clarify_problem
    read_request -->|wifi only| wifi_help
    read_request -->|password only| password_help
    read_request -->|other| other_help
    clarify_problem --> END
    wifi_help --> END
    password_help --> END
    other_help --> END
```"""
MODEL_GRAPH = """```mermaid
flowchart LR
    START --> load_user_memory --> assistant
    assistant -->|tool_calls exist| tools
    tools -->|ToolMessages| assistant
    assistant -->|no tool calls| END
```"""


def report_log(sid: str, mode: str) -> dict | None:
    path = ROOT / "outputs" / ("" if mode == "real" else "fake") / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def short(text: str, length: int = 145) -> str:
    return text.replace("\n", " ").replace("|", "/")[:length]


def generate_submission(mode: str = "real") -> str:
    scenarios = load_data("scenarios.json")["scenarios"]
    logs = {sc["id"]: report_log(sc["id"], mode) for sc in scenarios}
    rows = []
    for prompt, predicted in PREDICTIONS.items():
        sid = {"I cannot connect to Wi-Fi.": "S01", "I forgot my PASSWORD.": "S02",
               "My laptop screen is broken.": "S03", "My Wi-Fi password does not work.": "S04"}[prompt]
        observed = logs[sid]["messages"][0]["route"] if logs[sid] else None
        rows.append(f"| {prompt} | {' → '.join(predicted)} | " +
                    (" → ".join(observed) if observed else "Not run yet") + " | " +
                    ("Matches prediction" if observed == predicted else "Requires review" if observed else "Awaiting run") + " |")
    graph_change = "Not run yet."
    if logs["S05"]:
        graph_change = "Observed S05 route: **" + " → ".join(logs["S05"]["messages"][0]["route"]) + "**."

    real_mode_note = ("The scenarios in this report were run with OpenAI for Parts 2-3."
                      if mode == "real" else
                      "**WARNING: FAKE TEST MODE ONLY. These are NOT real model results; run --mode real before submitting.**")
    model_name = next((l["model_name"] for l in logs.values() if l and l["part"] > 1), "Not run yet")
    memory_rows = []
    for sid, description in [("S10", "Current thread reference"), ("S11", "Close process and restart"),
                             ("S12", "Same user, a new thread"), ("S13", "Different user")]:
        l = logs[sid]
        detail = "Not run yet"
        if l:
            message = l["messages"][-1]
            detail = ("Result=" + ("PASS" if l["evaluation"]["passed"] else "REVIEW") +
                      f"; saved language={message.get('preferred_language')}; " +
                      f"prior messages in this thread={message.get('trace', [{}])[0].get('previous_conversation_messages', '?')}")
            if sid in {"S11", "S12"}:
                detail += "; process PIDs=" + str([p["pid"] for p in l["process_events"] if p["action"] == "process_start"])
        memory_rows.append(f"| {description} | `python -m helpdesk.cli run-scenarios --mode {mode} --ids {sid}` | "
                           f"`outputs/{'' if mode == 'real' else 'fake/'}{sid}.json` | {detail} |")

    scenario_rows = []
    for sc in scenarios:
        sid = sc["id"]
        l = logs[sid]
        status = "Not run yet"
        if l:
            replies = " / ".join(short(x["final_reply"], 75) for x in l["messages"])
            grade = "PASS" if l["evaluation"]["passed"] else "REVIEW"
            status = f"{grade}; {replies}"
        scenario_rows.append(f"| {sid} — {sc['title']} | `--ids {sid}` | "
                             f"`outputs/{'' if mode == 'real' else 'fake/'}{sid}.json` | {short(status, 260)} |")
    checked = sum(l is not None for l in logs.values())
    passed = sum(bool(l and l["evaluation"]["passed"]) for l in logs.values())
    part2 = []
    for sid in ["S06", "S07", "S08", "S14"]:
        log = logs[sid]
        if log:
            calls = [x["name"] for x in log["tool_call_and_result_sequence"] if x["event"] == "tool_returned"]
            tix = sum(len(m.get("ticket_files", [])) for m in log["messages"])
            part2.append(f"- **{sid}** (`{log['status_profile']}`): observed tool results: "
                         f"{', '.join(calls) or 'none'}; tickets created: {tix}. "
                         f"Full trace: `outputs/{'' if mode == 'real' else 'fake/'}{sid}.json`.")
        else:
            part2.append(f"- **{sid}:** Not run yet.")
    doc = f"""# HW5 — My LangGraph helpdesk

**Course:** CSS4007 Artificial Intelligence  
**Python used for this generated report:** {platform.python_version()} (run `python --version` in Colab to confirm)  
**Provider:** OpenAI for real runs / labelled fake model for offline tests  
**Model:** {model_name}  
**Recorded scenarios:** {checked}/14; automatic checks passed: {passed}/14.

{real_mode_note}

## Part 1 — How the graph works

### My original graph and state

{PART1_GRAPH}

The state includes `message`, `category`, and `reply`. `read_request` reads `message` and writes `category`. Each help node reads the category or message as needed, retrieves the corresponding local guide, and writes `reply`. The conditional edge reads `category` and chooses a next node; unlike a node, it does not produce a state update. Every node receives the current accumulated state, not just the previous node's delta. `START` is the entry marker, `END` is the finish marker, and compiling produces a runnable graph from nodes and edges.

### Predictions made before running

| Message | Predicted route | Actual route | Conclusion |
| --- | --- | --- | --- |
""" + "\n".join(rows) + f"""

The original rule checks Wi-Fi first, so the message that contains both 'Wi-Fi' and 'password' follows the Wi-Fi node.

### Modified graph with clarification

{CHANGED_GRAPH}

{graph_change}

The new `clarify_problem` node is reached only when both topic keywords appear. LangGraph controls node execution and state propagation; my Python routing function decides the category and my Python help functions decide the response content. No LLM runs in Part 1.

## Part 2 — Model chooses tools

{MODEL_GRAPH}

The `assistant` node calls a bound tool-capable model. Its tool calls determine the conditional edge to `tools`. The `ToolNode` executes the corresponding Python tool and adds `ToolMessage` results to the accumulated conversation. The agent node sees those results on the next loop, then chooses whether to make another tool call or provide a final answer. This differs from fixed keyword routing because the model chooses actions based on the conversation and observed tool results, while Python still enforces the conditional ticket rule. The `assistant` node enforces a maximum of **6 model rounds per user message**; graph recursion is separately capped at 24.

All three tools also work as standalone Python functions via `python -m helpdesk.cli direct-tools --profile normal`. `find_instructions` reads `data/helpdesk.json`; `check_service_status` reads `data/service_status.json`; `prepare_ticket` validates user-stated steps and writes a JSON draft using `data/ticket_template.json`. No tickets are submitted.

### Actual snapshots and tool-use observations

""" + "\n".join(part2) + f"""

See the logs for model messages, tool arguments, tool results, final answers and ticket filenames. A Wi-Fi outage or unknown status must not satisfy the user's 'only if operating' condition. `account_recovery` is checked for password recovery problems.

## Part 3 — Conversation and user memory

The LangGraph `SqliteSaver` stores the accumulated messages separately for each `(user_id, thread_id)` pair in `local-storage/.../checkpoints.sqlite`. The identifier `thread_id` refers to one conversation, while `user_id` identifies the fictional user across multiple conversations. A separate SQLite table `user_preferences` in `preferences.sqlite` saves only an explicitly requested language preference keyed by `user_id`. Language is never initialized from `demo_users.json`.

On every turn the `load_user_memory` node reads preferences. User messages from the same thread remain available after a new OS process opens the same checkpoint database. The program actually launches separate child processes at `restart_process` events; the logs include their distinct PIDs and commands.

| Situation | Command | Log file | What actually happened |
| --- | --- | --- | --- |
""" + "\n".join(memory_rows) + f"""

Looking up troubleshooting steps in `helpdesk.json` is **retrieval** from an external reference file. Remembering the user's preference is **user memory** persisted by user ID; conversation messages are **thread memory** persisted by the checkpointer. Neither reference retrieval nor user memory is supplied by another user's conversation.

## Part 4 — Reproduction, tests and CI

Install exact package versions using `pip install -r requirements.txt`. Set the model key in an ignored `.env` or `OPENAI_API_KEY` environment variable, and choose a tool-capable `MODEL_NAME`. Run `python -m helpdesk.cli run-scenarios --mode real`. Run `python -m pytest -q` for **API-free tests** with an explicitly fake model. GitHub Actions runs the same tests on each push and pull request. Memory and drafts are in ignored `local-storage/`; remove the directory to reset them, while `outputs/*.json` contains fictional shareable traces. Full commands are in `README.md`.

Tests catch: Part 1 routing / case sensitivity / changed graph; incorrect guide or status lookup; missing ticket details; violation of conditional ticket policy; broken persistent preference and checkpoint reload; mixing two users or threads. The fake-model tests prove graph wiring only, not real LLM accuracy.

## Choices and limitations

SQLite is simple and persistent across real process restarts, suitable for a small single-user demo. `SqliteSaver` is not a production high-concurrency database. The fake tool model has no intelligence and its outputs must not be represented as real LLM calls. The real model may vary wording or choose extra tools; review every real trace. A conservative deterministic pattern recognizer accepts explicitly reported troubleshooting steps for the supplied exercises but does not understand all paraphrases. Service status and tickets are fictional, not university systems. Google Colab temporary runtime storage is lost if its runtime resets unless this project is saved to Google Drive.

## Supplied scenarios — actual results

Run all fourteen: `python -m helpdesk.cli run-scenarios --mode real`, and regenerate this file: `python -m helpdesk.cli report --mode real`.

| Scenario | Runner command suffix | Log file | Observed result / review |
| --- | --- | --- | --- |
""" + "\n".join(scenario_rows) + "\n\n## AI tool disclosure\n\nI used ChatGPT to help understand the assignment and draft the implementation and documentation. Actual execution results are saved separately in the program logs.\n"
    target = ROOT / ("SUBMISSION.md" if mode == "real" else "SUBMISSION_FAKE_PREVIEW.md")
    target.write_text(doc, encoding="utf-8")
    return f"Written {target} with {checked} observed scenarios (mode={mode}); automatic checks passed: {passed}"
