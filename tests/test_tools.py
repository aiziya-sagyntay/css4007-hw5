import json

from helpdesk.tools import ToolContext, make_tools


def setup_ctx(tmp_path, profile="normal", text="I enabled Wi-Fi and tried reconnecting, but it still fails."):
    ctx = ToolContext("demo-user-a", "test", profile, tmp_path, user_history=[text])
    return ctx, make_tools(ctx)


def invoke(tool, **kwargs):
    return json.loads(tool.invoke(kwargs))


def test_all_three_tools_are_directly_callable(tmp_path):
    ctx, (guide, status, ticket) = setup_ctx(tmp_path)
    instructions = invoke(guide, topic="wifi")
    assert instructions["instruction_id"] == "GUIDE-WIFI"
    assert instructions["source"] == "data/helpdesk.json"
    status_result = invoke(status, service="wifi")
    assert status_result["status"] == "operational"
    record = invoke(ticket, category="wifi", problem_description=ctx.user_history[-1], steps_tried=["enabled Wi-Fi"])
    assert record["result"] == "draft_created"
    ticket_file = tmp_path / "tickets" / f"{record['ticket_id']}.json"
    assert ticket_file.exists()
    actual = json.loads(ticket_file.read_text())
    assert actual["status"] == "draft"
    assert actual["steps_tried"] == ["Enabled Wi-Fi (user reported)", "Tried reconnecting (user reported)"]
    assert actual["service_status"] == "operational"


def test_no_invented_steps_or_problem(tmp_path):
    ctx, (_, _, ticket) = setup_ctx(tmp_path, text="Prepare a support ticket.")
    record = invoke(ticket, category="wifi", problem_description="I fixed my laptop", steps_tried=["changed password"])
    assert record["result"] == "missing_information"
    assert list((tmp_path / "tickets").glob("*.json")) == [] if (tmp_path / "tickets").exists() else True


def test_status_snapshots_are_distinct(tmp_path):
    for profile, expected in [("normal", "operational"), ("wifi_outage", "outage"),
                              ("status_unavailable", "unknown")]:
        ctx, (_, status, _) = setup_ctx(tmp_path / profile, profile)
        assert invoke(status, service="wifi")["status"] == expected
    ctx, (_, status, _) = setup_ctx(tmp_path / "recovery", "recovery_outage")
    assert invoke(status, service="account_recovery")["status"] == "outage"


def test_conditional_ticket_requires_verified_operational_status(tmp_path):
    message = "I enabled Wi-Fi and tried reconnecting. Check status. If it is operating, prepare a ticket."
    for profile in ["wifi_outage", "status_unavailable"]:
        ctx, (_, check, ticket) = setup_ctx(tmp_path / profile, profile, message)
        status = invoke(check, service="wifi")
        assert status["status"] != "operational"
        result = invoke(ticket, category="wifi", problem_description=message, steps_tried=["reconnected"])
        assert result["result"] == "blocked_by_condition"
        assert ctx.created_tickets == []
    ctx, (_, check, ticket) = setup_ctx(tmp_path / "normal", "normal", message)
    assert invoke(check, service="wifi")["status"] == "operational"
    assert invoke(ticket, category="wifi", problem_description=message,
                  steps_tried=["tried reconnecting"])["result"] == "draft_created"
