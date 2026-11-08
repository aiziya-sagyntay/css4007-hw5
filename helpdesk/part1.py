"""Part 1: fixed LangGraph routing, without any model or API key."""
from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from .common import load_data


class RouteState(TypedDict, total=False):
    message: str
    category: str
    reply: str


def build_part1_graph(with_clarification: bool = False):
    guides = load_data("helpdesk.json")["instructions"]

    def read_request(state: RouteState) -> RouteState:
        text = state["message"].lower()
        wifi = "wifi" in text or "wi-fi" in text
        password = "password" in text
        if wifi and password and with_clarification:
            category = "both"
        elif wifi:
            category = "wifi"  # Original rule gives Wi-Fi priority.
        elif password:
            category = "password"
        else:
            category = "other"
        return {"category": category}

    def wifi_help(state: RouteState) -> RouteState:
        data = guides["wifi"]
        return {"reply": f"{data['instruction_id']}: " + " ".join(data["steps"])}

    def password_help(state: RouteState) -> RouteState:
        data = guides["password"]
        return {"reply": f"{data['instruction_id']}: " + " ".join(data["steps"])}

    def other_help(state: RouteState) -> RouteState:
        return {"reply": "Is your question about Wi-Fi or a password?"}

    def clarify_problem(state: RouteState) -> RouteState:
        return {"reply": "Is the issue connecting to Wi-Fi, or recovering an account password? Which should we solve first?"}

    def choose(state: RouteState) -> str:
        return state["category"]

    builder = StateGraph(RouteState)
    for node, action in [("read_request", read_request), ("wifi_help", wifi_help),
                         ("password_help", password_help), ("other_help", other_help)]:
        builder.add_node(node, action)
    if with_clarification:
        builder.add_node("clarify_problem", clarify_problem)
    builder.add_edge(START, "read_request")
    mapping = {"wifi": "wifi_help", "password": "password_help", "other": "other_help"}
    if with_clarification:
        mapping["both"] = "clarify_problem"
    builder.add_conditional_edges("read_request", choose, mapping)
    for name in mapping.values():
        builder.add_edge(name, END)
    return builder.compile()


def run_part1(message: str, with_clarification: bool = False) -> dict:
    graph = build_part1_graph(with_clarification)
    state = {"message": message}
    trace = [{"node": "START", "state": dict(state)}]
    for chunk in graph.stream(state, stream_mode="updates"):
        for node, update in chunk.items():
            if not isinstance(update, dict):
                continue
            state.update(update)
            trace.append({"node": node, "update": update, "state": dict(state)})
    trace.append({"node": "END", "state": dict(state)})
    return {"variant": "with_clarification" if with_clarification else "original",
            "message": message, "route": [row["node"] for row in trace],
            "final_state": state, "trace": trace}


PREDICTIONS = {
    "I cannot connect to Wi-Fi.": ["START", "read_request", "wifi_help", "END"],
    "I forgot my PASSWORD.": ["START", "read_request", "password_help", "END"],
    "My laptop screen is broken.": ["START", "read_request", "other_help", "END"],
    "My Wi-Fi password does not work.": ["START", "read_request", "wifi_help", "END"],
}

if __name__ == "__main__":
    for prompt, prediction in PREDICTIONS.items():
        actual = run_part1(prompt)
        print(json.dumps({"predicted": prediction, "observed": actual}, indent=2))
    print(json.dumps(run_part1("My Wi-Fi password does not work.", True), indent=2))
