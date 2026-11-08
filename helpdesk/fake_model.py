"""Explicitly FAKE tool-calling model used in offline tests, NOT a real LLM result."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from .common import detect_topic, user_stated_steps


def call_tool(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": "fake-" + uuid.uuid4().hex[:10],
                                              "name": name, "args": args, "type": "tool_call"}])


class FakeToolModel:
    """Tiny deterministic simulator validating graph wiring without a private key.

    It does not replace the required real OpenAI model demonstration.
    """
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        human_idx = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        if not human_idx:
            return AIMessage(content="Please describe your IT problem.")
        pos = human_idx[-1]
        message = str(messages[pos].content)
        lower = message.lower()
        earlier = [str(m.content) for m in messages[:pos] if isinstance(m, HumanMessage)]
        all_texts = earlier + [message]
        tools_this_turn = {}
        for m in messages[pos + 1:]:
            if isinstance(m, ToolMessage):
                try:
                    tools_this_turn[m.name] = json.loads(str(m.content))
                except ValueError:
                    tools_this_turn[m.name] = {"error": str(m.content)}
        sys = next((str(m.content) for m in messages if isinstance(m, SystemMessage)), "")
        kazakh = "PREFERRED_LANGUAGE: Kazakh" in sys
        topic = detect_topic(message) or detect_topic(" ".join(earlier))
        service = "wifi" if topic == "wifi" else "account_recovery"
        ticket_wanted = ("ticket" in lower or any("prepare a support ticket" in m.lower() for m in earlier))
        condition = any("if it is operating" in m.lower() or "if it is working" in m.lower()
                        for m in all_texts)
        status_wanted = ("down" in lower or "status" in lower or "known problem" in lower
                         or "unavailable" in lower or condition)
        instruction_wanted = ("troubleshooting steps" in lower or "instructions" in lower
                              or "forgot my password" in lower)

        if "which language" in lower or "preferred language" in lower:
            return AIMessage(content=("Сіз жауаптарды қазақ тілінде сұрадыңыз. Мен Wi-Fi, құпиясөзді қалпына келтіру, қызмет күйін тексеру және өтінім жобасын дайындауға көмектесемін."
                                      if kazakh else "You have not saved a preferred language for this user."))
        if "have i told you" in lower or "previous problem" in lower:
            if earlier:
                return AIMessage(content="This conversation includes an earlier message, but I cannot assume another user's history.")
            return AIMessage(content="No language preference or previous problem has been recorded for this user.")
        if "which steps did" in lower or "which problem and steps" in lower or "already tried that" in lower:
            steps = user_stated_steps(earlier)
            issue = detect_topic(" ".join(earlier))
            if kazakh:
                return AIMessage(content="Сіз Wi-Fi мәселесін айттыңыз. Бұрын орындаған қадамдарыңыз: " + ("; ".join(steps) if steps else "нақты қадамдар көрсетілмеді"))
            return AIMessage(content=f"Earlier you reported a {issue or 'not yet specified'} problem. You already tried: "
                                      + ("; ".join(steps) if steps else "no explicit steps were recorded"))

        if status_wanted and "check_service_status" not in tools_this_turn:
            return call_tool("check_service_status", {"service": service})
        if condition and "check_service_status" in tools_this_turn:
            status = tools_this_turn["check_service_status"].get("status", "unknown")
            if status != "operational":
                if status == "outage":
                    return AIMessage(content="The selected fictional status snapshot reports an outage. No ticket was drafted because your condition was not met. No repair time is provided.")
                return AIMessage(content="The demo status is unknown. I cannot confirm the service is operating, so no conditional ticket was drafted. Would you like a draft noting that uncertainty?")
        if ticket_wanted and "prepare_ticket" not in tools_this_turn:
            if not topic or not user_stated_steps(all_texts):
                return AIMessage(content="What problem are you having, and what steps have you already tried?")
            return call_tool("prepare_ticket", {"category": topic,
                                                 "problem_description": message,
                                                 "steps_tried": user_stated_steps(all_texts)})
        if instruction_wanted and "find_instructions" not in tools_this_turn and topic:
            return call_tool("find_instructions", {"topic": topic})

        if "prepare_ticket" in tools_this_turn:
            r = tools_this_turn["prepare_ticket"]
            return AIMessage(content=(f"I prepared a LOCAL DRAFT: {r.get('filename')}. Nothing was sent."
                                      if r.get("result") == "draft_created" else r.get("question", r.get("reason", "No draft was created."))))
        if "find_instructions" in tools_this_turn:
            r = tools_this_turn["find_instructions"]
            return AIMessage(content=f"{r.get('instruction_id')}: " + "; ".join(r.get("steps", [])))
        if "check_service_status" in tools_this_turn:
            r = tools_this_turn["check_service_status"]
            return AIMessage(content=f"DEMO {r.get('service')}: {r.get('status')}. {r.get('message')}")
        if kazakh:
            return AIMessage(content="Мен Wi-Fi, құпиясөз және IT қолдау туралы сұрақтарға көмектесемін.")
        return AIMessage(content="I can help with Wi-Fi, password recovery, service status, and local ticket drafts. What problem are you having?")
