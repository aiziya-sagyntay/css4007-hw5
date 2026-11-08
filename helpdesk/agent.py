"""LangGraph tool loop with persisted conversation + separate user preference memory."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .fake_model import FakeToolModel
from .memory import PreferenceStore, explicitly_requested_language
from .tools import ToolContext, make_tools

MAX_MODEL_ROUNDS = 6


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    preferred_language: str
    rounds: int
    loop_limit_hit: bool


def model_prompt(language: str | None) -> str:
    lang = language or "not set"
    return f"""You are a university IT HELPDESK for FICTIONAL local demo data.
PREFERRED_LANGUAGE: {lang}
The conversation history provided is only for the current user AND thread.
Help only with Wi-Fi, password recovery, status checks, and LOCAL ticket drafts.
Use tools whenever the user requests instructions, status, or a ticket.
For Wi-Fi status use service='wifi'. Password recovery uses service='account_recovery'.
Be explicit that statuses are local DEMO snapshots, not real university services.
The selected snapshot is authoritative. Outage has NO repair ETA. Unknown means the status cannot be determined, not that the service is down. Never claim a confirmed outage when status is unknown.
If the user requests a ticket ONLY IF a service is operating, FIRST call check_service_status.
Make that conditional ticket ONLY if returned status is exactly 'operational'.
If outage or unknown, do NOT call prepare_ticket for that conditional request.
Only create a ticket draft when the user explicitly requested one in this conversation. Never create one merely because a problem was reported.
If the user asks to recall previous problems or troubleshooting
steps, answer directly from conversation memory.
Do not suggest tickets, ask for ticket details, or initiate
a ticket workflow unless the user explicitly requests a ticket.
If the user only asks to remember a language preference,
confirm the preference without offering a ticket.
A ticket draft needs both the real problem and user-stated steps tried. Ask when missing.
When a ticket is requested after a clarification, use the earlier conversation.
NEVER invent troubleshooting steps performed; guide steps are suggestions, not claimed actions.
Do not claim a ticket was sent. Never ask for or store passwords, recovery codes or API keys.
For a saved language preference, answer in that language, including in a new conversation.
Do not claim to know other users' messages or preferences. Do not invent anything not in records.
For a message saying "I already tried that", use only previous
messages in the same thread. If the antecedent is ambiguous,
ask which earlier suggested step the user tried.
Never invent completed actions.

If the user only reports a problem, asks to remember a preference,
or asks to recall previous steps, answer directly.
Never offer, promise or initiate ticket drafting unless
the user requests ticket help.

If service status is unknown, explain that neither an outage
nor operational status is confirmed. Do not create a conditional
ticket. You may offer a DIFFERENT draft noting the uncertainty,
but create it only after the user's explicit request.

Keep answers brief; cite the instruction ID when using instructions. """


def serialize_message(message: BaseMessage) -> dict:
    row: dict[str, Any] = {"type": message.type, "content": str(message.content)}
    if isinstance(message, AIMessage) and message.tool_calls:
        row["model_tool_requests"] = [
            {"name": x["name"], "args": x["args"], "id": x["id"]} for x in message.tool_calls]
    if isinstance(message, ToolMessage):
        row["tool_name"] = message.name
        try:
            row["tool_result"] = json.loads(str(message.content))
        except json.JSONDecodeError:
            row["tool_result"] = str(message.content)
        row["tool_call_id"] = message.tool_call_id
    return row


class HelpdeskSession:
    """Create a new instance for each (user_id, thread_id, status_profile) session."""
    def __init__(self, user_id: str, thread_id: str, status_profile: str,
                 storage_dir: str | Path, mode: str = "real", model_name: str | None = None):
        if not user_id or not thread_id:
            raise ValueError("A user ID and a thread ID are both required")
        if mode not in {"real", "fake"}:
            raise ValueError("Mode must be real or fake")
        self.user_id = user_id
        self.thread_id = thread_id
        self.status_profile = status_profile
        self.mode = mode
        self.model_name = model_name or os.environ.get("MODEL_NAME", "gpt-4o-mini")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.preference_store = PreferenceStore(self.storage_dir / "preferences.sqlite")
        self.conn = sqlite3.connect(self.storage_dir / "checkpoints.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(self.conn)
        self.ctx = ToolContext(user_id, thread_id, status_profile, self.storage_dir)
        self.tools = make_tools(self.ctx)
        if mode == "real":
            if not os.environ.get("OPENAI_API_KEY"):
                self.close()
                raise RuntimeError("OPENAI_API_KEY is missing; set it in Colab secrets before real-model runs")
            self.model = ChatOpenAI(model=self.model_name, temperature=0)
        else:
            self.model = FakeToolModel()
        self.graph = self._build_graph()
        # Namespace checkpoints by BOTH the external user ID and thread ID.
        hashed = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[:18]
        self.config = {"configurable": {"thread_id": f"u-{hashed(user_id)}-t-{hashed(thread_id)}"},
                       "recursion_limit": 24}

    def _build_graph(self):
        model = self.model.bind_tools(self.tools)

        def load_user_memory(state: AgentState) -> dict:
            latest = next((str(m.content) for m in reversed(state["messages"])
                           if isinstance(m, HumanMessage)), "")
            requested = explicitly_requested_language(latest)
            if requested:
                self.preference_store.set_language(self.user_id, requested)
            return {"preferred_language": self.preference_store.get_language(self.user_id) or "not set"}

        def assistant(state: AgentState) -> dict:
            rounds = state.get("rounds", 0)
            if rounds >= MAX_MODEL_ROUNDS:
                return {"messages": [AIMessage(content="The safe tool-call limit was reached; please retry with a shorter request.")],
                        "rounds": rounds, "loop_limit_hit": True}
            sys = SystemMessage(content=model_prompt(state.get("preferred_language")))
            answer = model.invoke([sys] + state["messages"])
            return {"messages": [answer], "rounds": rounds + 1}

        def route_after_assistant(state: AgentState) -> str:
            latest = state["messages"][-1]
            return "tools" if getattr(latest, "tool_calls", None) else "end"

        builder = StateGraph(AgentState)
        builder.add_node("load_user_memory", load_user_memory)
        builder.add_node("assistant", assistant)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_edge(START, "load_user_memory")
        builder.add_edge("load_user_memory", "assistant")
        builder.add_conditional_edges("assistant", route_after_assistant, {"tools": "tools", "end": END})
        builder.add_edge("tools", "assistant")
        return builder.compile(checkpointer=self.checkpointer)

    def respond(self, message: str) -> dict:
        before = self.graph.get_state(self.config)
        old_messages = before.values.get("messages", []) if before and before.values else []
        # Give tools only genuine user statements from the checkpoint + new user message.
        self.ctx.user_history = [str(m.content) for m in old_messages if isinstance(m, HumanMessage)] + [message]
        self.ctx.checked_services = {}
        self.ctx.created_tickets = []
        trace: list[dict] = [{"node": "INPUT", "message": message,
                              "previous_conversation_messages": len(old_messages),
                              "memory_source": "langgraph_sqlite_checkpointer" if old_messages else "new_conversation"}]
        for update in self.graph.stream({"messages": [HumanMessage(content=message)], "rounds": 0,
                                         "loop_limit_hit": False}, config=self.config, stream_mode="updates"):
            for node, values in update.items():
                row: dict[str, Any] = {"node": node}
                if isinstance(values, dict):
                    row["state_updates"] = {k: v for k, v in values.items() if k != "messages"}
                    if "messages" in values:
                        row["messages_added"] = [serialize_message(x) for x in values["messages"]]
                    if node == "load_user_memory":
                        row["memory_source"] = "preferences.sqlite / user_id=" + self.user_id
                    if node == "tools":
                        sources = []
                        for m in values.get("messages", []):
                            if isinstance(m, ToolMessage):
                                sources.append({"find_instructions": "data/helpdesk.json",
                                                "check_service_status": "data/service_status.json",
                                                "prepare_ticket": "data/ticket_template.json + user messages"}.get(m.name, "unknown"))
                        row["sources"] = sources
                trace.append(row)
        after = self.graph.get_state(self.config)
        latest = after.values["messages"][-1]
        return {"user_id": self.user_id, "thread_id": self.thread_id,
                "profile": self.status_profile, "mode": self.mode,
                "model": self.model_name if self.mode == "real" else "FAKE deterministic tool model",
                "final_reply": str(latest.content), "ticket_files": list(self.ctx.created_tickets),
                "preferred_language": after.values.get("preferred_language"),
                "loop_limit_hit": bool(after.values.get("loop_limit_hit", False)),
                "trace": trace}

    def close(self):
        if hasattr(self, "preference_store"):
            self.preference_store.close()
        if hasattr(self, "conn"):
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
