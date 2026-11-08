"""All tests use an explicitly FAKE model: no API key, no real-model claims."""
from helpdesk.agent import HelpdeskSession


def make(storage, user="demo-user-a", thread="thread-1", profile="normal"):
    return HelpdeskSession(user, thread, profile, storage, mode="fake")


def tools_used(result):
    names = []
    for item in result["trace"]:
        for message in item.get("messages_added", []):
            if message.get("tool_name"):
                names.append(message["tool_name"])
    return names


def test_fake_agent_uses_multiple_tools_and_ticket(tmp_path):
    with make(tmp_path) as s:
        first = s.respond("Show me the Wi-Fi troubleshooting steps.")
        assert "find_instructions" in tools_used(first)
        second = s.respond("I enabled Wi-Fi and forgot the saved network, but still cannot connect. "
                           "Check whether it is down. If it is operating, prepare a ticket.")
        assert "check_service_status" in tools_used(second)
        assert "prepare_ticket" in tools_used(second)
        assert len(second["ticket_files"]) == 1
        assert not second["loop_limit_hit"]


def test_fake_agent_does_not_create_conditional_ticket_during_outage(tmp_path):
    with make(tmp_path, profile="wifi_outage") as s:
        r = s.respond("I enabled Wi-Fi and tried reconnecting. Is it down? If it is operating, prepare a ticket.")
        assert "check_service_status" in tools_used(r)
        assert "prepare_ticket" not in tools_used(r)
        assert r["ticket_files"] == []


def test_missing_details_requires_question_then_creates_draft(tmp_path):
    with make(tmp_path) as s:
        first = s.respond("Prepare a support ticket.")
        assert first["ticket_files"] == []
        second = s.respond("The issue is Wi-Fi. I enabled it and tried reconnecting, but it still fails.")
        assert len(second["ticket_files"]) == 1


def test_conversation_survives_recreating_app(tmp_path):
    with make(tmp_path, thread="restart-thread") as first_process:
        first_process.respond("My issue is Wi-Fi. I enabled it and tried reconnecting, but it still fails.")
    # SQLite connections are closed. This is a new instance, reopening files.
    with make(tmp_path, thread="restart-thread") as second_process:
        result = second_process.respond("Which problem and steps did we discuss?")
        assert result["trace"][0]["previous_conversation_messages"] > 0
        assert "reconnect" in result["final_reply"].lower()


def test_user_preference_survives_new_thread_without_history_leak(tmp_path):
    with make(tmp_path, user="demo-user-a", thread="first") as s:
        r = s.respond("Please remember that I prefer replies in Kazakh. I have a Wi-Fi problem.")
        assert r["preferred_language"] == "Kazakh"
    with make(tmp_path, user="demo-user-a", thread="second") as s:
        r = s.respond("Which language did I ask you to use? What can you help with?")
        assert r["preferred_language"] == "Kazakh"
        assert r["trace"][0]["previous_conversation_messages"] == 0
    with make(tmp_path, user="demo-user-b", thread="second") as s:
        r = s.respond("Have I told you a preferred language or a previous problem?")
        assert r["preferred_language"] == "not set"
        assert r["trace"][0]["previous_conversation_messages"] == 0


def test_thread_id_cannot_cross_user_boundary(tmp_path):
    with make(tmp_path, user="demo-user-a", thread="shared-id") as s:
        s.respond("I cannot connect to Wi-Fi. I enabled Wi-Fi.")
    with make(tmp_path, user="demo-user-b", thread="shared-id") as s:
        result = s.respond("Which problem did I previously report?")
        assert result["trace"][0]["previous_conversation_messages"] == 0
