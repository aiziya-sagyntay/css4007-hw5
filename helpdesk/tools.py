"""Three callable local tools. They are also tested independently of a model."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from .common import clean_text, detect_topic, load_data, user_stated_steps


@dataclass
class ToolContext:
    user_id: str
    thread_id: str
    status_profile: str
    storage_dir: Path
    user_history: list[str] = field(default_factory=list)
    checked_services: dict[str, str] = field(default_factory=dict)
    created_tickets: list[str] = field(default_factory=list)


def make_tools(ctx: ToolContext):
    guide = load_data("helpdesk.json")
    status_fixtures = load_data("service_status.json")["profiles"]
    ticket_template = load_data("ticket_template.json")["ticket"]
    if ctx.status_profile not in status_fixtures:
        raise ValueError(f"Invalid status profile: {ctx.status_profile}")

    @tool
    def find_instructions(topic: Literal["wifi", "password"]) -> str:
        """Retrieve practical instructions for Wi-Fi or password recovery from the fictional local guide."""
        row = guide["instructions"].get(topic)
        if row is None:
            return json.dumps({"error": "unknown_topic", "topic": topic})
        return json.dumps({"topic": topic, "instruction_id": row["instruction_id"],
                           "title": row["title"], "steps": row["steps"],
                           "source": "data/helpdesk.json"}, ensure_ascii=False)

    @tool
    def check_service_status(service: Literal["wifi", "account_recovery"]) -> str:
        """Look up the selected DEMO snapshot; wifi and account_recovery are distinct services."""
        record = status_fixtures[ctx.status_profile].get(service)
        if not record:
            return json.dumps({"error": "unknown_service", "service": service})
        ctx.checked_services[service] = record["status"]
        return json.dumps({"service": service, "status": record["status"],
                           "message": record["message"], "profile": ctx.status_profile,
                           "source": "data/service_status.json"}, ensure_ascii=False)

    @tool
    def prepare_ticket(category: Literal["wifi", "password"], problem_description: str,
                       steps_tried: list[str]) -> str:
        """Make a local ticket draft ONLY from explicit user details. Never submit a ticket.

        Args:
          category: wifi or password.
          problem_description: the user's actual problem, not hypothetical instructions.
          steps_tried: steps the user explicitly says were tried (validated against history).
        """
        # The model may propose details, but the local program independently checks facts.
        user_texts = ctx.user_history
        recognized = user_stated_steps(user_texts)
        user_topic = detect_topic(" ".join(user_texts))
        if not user_topic or category != user_topic or not recognized:
            return json.dumps({"result": "missing_information", "question":
                               "What problem are you having, and what steps have you already tried?",
                               "source": "conversation_memory"})
        topic_messages = [m for m in user_texts if detect_topic(m) == category]
        if not topic_messages:
            return json.dumps({"result": "missing_information", "question": "Please describe your problem."})
        # We do not write the model's proposed text to disk: use user messages instead.
        user_description = clean_text(topic_messages[-1])
        service = guide["topic_services"][category]
        conditional = any("if it is operating" in m.lower() or "if it is working" in m.lower()
                          or "if the service is operating" in m.lower() for m in user_texts)
        if conditional:
            observed = ctx.checked_services.get(service)
            if observed != "operational":
                return json.dumps({"result": "blocked_by_condition", "service": service,
                                   "observed_status": observed or "not_checked",
                                   "reason": "The user requested a ticket only if service is confirmed operational."})
        # If no status lookup was actually made, record not_checked, not operational.
        known_status = ctx.checked_services.get(service, "not_checked")
        ticket = json.loads(json.dumps(ticket_template))
        ticket_id = "HW5-" + uuid.uuid4().hex[:10].upper()
        ticket.update({"ticket_id": ticket_id, "status": "draft", "user_id": ctx.user_id,
                       "thread_id": ctx.thread_id, "category": category,
                       "summary": user_description, "steps_tried": recognized,
                       "service_status": known_status, "status_profile": ctx.status_profile,
                       "reference_ids": [guide["instructions"][category]["instruction_id"]]})
        folder = ctx.storage_dir / "tickets"
        folder.mkdir(parents=True, exist_ok=True)
        ticket_file = folder / f"{ticket_id}.json"
        ticket_file.write_text(json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
        ctx.created_tickets.append(str(ticket_file))
        return json.dumps({"result": "draft_created", "ticket_id": ticket_id,
                           "filename": str(ticket_file), "delivery": "local draft only",
                           "source": "data/ticket_template.json + conversation_memory",
                           "ticket": ticket}, ensure_ascii=False)

    return [find_instructions, check_service_status, prepare_ticket]
