# HW5 — Fictional University IT Helpdesk with LangGraph

This repository implements **CSS4007 HW5 (Parts 1–4)** using a deterministic routing graph, a real tool-capable LLM, three local tools, SQLite conversation/user memory, 14 scenarios, tests and CI. The original assignment is preserved in `ASSIGNMENT.md` and the demonstration specification in `SCENARIOS.md`.

**Important:** `data/` is made-up practice material, not actual university IT records. A ticket is **only** a local JSON draft. Do not enter actual credentials.

## 1. Install (Python 3.11 recommended)

```bash
python --version
python -m pip install -r requirements.txt
```

Top-level dependencies are pinned in `requirements.txt`; their transitive dependencies are resolved by pip. Tested with Python 3.13.18 in Google Colab and Python 3.11 in GitHub Actions. Run this repository directly using the CLI commands below. The separate Colab notebook is optional and is not included in this repository.

## 2. Configure a model for REAL demonstrations

Set environment variables in your shell, `.env` (ignored by git), or Colab secrets:

```bash
# Do NOT commit a real key.
# Bash/macOS/Linux example:
export OPENAI_API_KEY="your-key"
export MODEL_NAME="gpt-4o-mini"
export LANGSMITH_TRACING="false"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your-key"
$env:MODEL_NAME="gpt-4o-mini"
```

Use any model that supports OpenAI function/tool calling and is available to your API account. The required Part 1 and offline tests do **not** need a key.

## 3. Run Part 1 (no model)

```bash
python -m helpdesk.cli part1 --variant original --message "I cannot connect to Wi-Fi."
python -m helpdesk.cli part1 --variant original --message "My Wi-Fi password does not work."
python -m helpdesk.cli part1 --variant with_clarification --message "My Wi-Fi password does not work."
```

The command prints each node executed and the state after its update. The graph diagrams and predictions are in `SUBMISSION.md`.

## 4. Call the three tools without a model

```bash
python -m helpdesk.cli direct-tools --profile normal
```

This calls `find_instructions`, `check_service_status` and `prepare_ticket` directly. A fictional draft is written to `local-storage/tickets/`.

## 5. Run the REAL model and all 14 scenarios

```bash
python -m helpdesk.cli run-scenarios --mode real
python -m helpdesk.cli report --mode real
```

Each scenario is based on the supplied `data/scenarios.json`. `reset_before` removes its **own** previous storage, not the storage for other scenarios. `restart_process` truly ends a Python child process and starts a new one with the same SQLite files. S11/S12 JSON logs include distinct child process IDs. The real run writes **`outputs/S01.json` ... `outputs/S14.json`**, then the `report` command fills `SUBMISSION.md` with measured results, tool calls, ticket filenames, and memory observations. Fictional ticket JSON drafts are also copied into `outputs/tickets/` so they can be inspected in the submitted repository. Inspect and correct any `REVIEW` outcomes; a language model is nondeterministic.

For a quick real test:

```bash
python -m helpdesk.cli run-scenarios --mode real --ids S06 S07 S08 S14
```

For a chat that accepts several consecutive messages in one process:

```bash
python -m helpdesk.cli chat --user demo-user-a --thread my-thread --profile normal --mode real
```

Choose `--profile normal`, `wifi_outage`, `recovery_outage`, or `status_unavailable` when chatting. Use the same `--thread` and `--user` after restarting the program to resume; a new thread for the same user retains only the saved language preference.

## 6. Test safely without an API key

```bash
python -m pytest -q
python -m helpdesk.cli run-scenarios --mode fake
python -m helpdesk.cli report --mode fake
```

The test mode uses a **clearly labelled fake deterministic tool-calling model**, not an OpenAI API call. Fake scenario traces go under `outputs/fake/` and the fake report is `SUBMISSION_FAKE_PREVIEW.md`. Do **not** submit the fake preview as real-model evidence. The tests cover routing, direct tool execution, status conditions, missing ticket details, checkpoint persistence, user-vs-thread isolation, and process restart splitting.

## 7. Memory storage and reset

- `local-storage/scenario-runs/<SXX>/checkpoints.sqlite` — LangGraph conversation checkpoints.
- `local-storage/scenario-runs/<SXX>/preferences.sqlite` — independent language preferences per fictional user.
- `local-storage/scenario-runs/<SXX>/tickets/` — local ticket drafts.
- `local-storage/checkpoints.sqlite` and `local-storage/preferences.sqlite` — interactive chat sessions.

To clear all memory and test drafts, stop all running helpdesk processes and delete `local-storage/`. Keep `outputs/` only if you want to preserve execution evidence. All databases and `.env` are git-ignored.

**Colab caveat:** `/content/` disappears when the Colab runtime is reset or disconnected. Save the completed repo ZIP locally or put storage on a mounted Google Drive. The S11/S12 restart exercise itself is implemented as genuine new OS subprocesses within one connected runtime.

## 8. GitHub Actions

`.github/workflows/tests.yml` runs `pytest` on every push / pull request with Python 3.11 and no API key. GitHub Actions validates code and fake-model tests, while real-model runs and their saved output logs are performed separately in Colab.

## 9. File map

- `helpdesk/part1.py` — original and modified StateGraph with route traces.
- `helpdesk/tools.py` — three independent local tools, ticket constraints and fixture lookup.
- `helpdesk/agent.py` — tool-loop StateGraph, cap, tracing and conversation checkpointer.
- `helpdesk/memory.py` — SQLite user preferences.
- `helpdesk/fake_model.py` — explicit no-API simulator used for tests only.
- `helpdesk/runner.py` — scenario orchestration with real child-process restarts.
- `helpdesk/report.py` — updates `SUBMISSION.md` using *observed* logs (not invented results).
- `tests/` — API-free tests.
- `outputs/` — measured JSON traces and shareable demo ticket drafts in `outputs/tickets/` after running scenarios.

## 10. Suggested commit sequence

```bash
git add helpdesk/part1.py; git commit -m "Implement deterministic routing graph"
git add helpdesk/tools.py helpdesk/agent.py; git commit -m "Add tool-calling LangGraph agent"
git add helpdesk/memory.py helpdesk/runner.py; git commit -m "Persist user and thread memory and replay scenarios"
git add tests .github requirements.txt README.md; git commit -m "Add offline tests and CI"
git add SUBMISSION.md outputs/S*.json; git commit -m "Document observed runs and traces"
```

Commit commands are examples; only commit a file after it exists. Do not commit API secrets or SQLite databases. Submit the link to your **public fork**; do not create a pull request against the instructor's starter.


## Extra Part 3: literal contextual-memory demonstration

```bash
python -m helpdesk.extra_demo --mode real
python -m helpdesk.cli report --mode real
```

The exact follow-up `I already tried that.` uses previous messages
from the same conversation thread.

Evidence: `outputs/EXTRA_MEMORY_REFERENCE.json`.

Instructions in `data/helpdesk.json` are retrieval.
SQLite checkpoints store conversation memory.
`preferences.sqlite` stores user language preferences.
