from helpdesk.part1 import PREDICTIONS, run_part1


def test_all_original_routes_match_predictions():
    for message, prediction in PREDICTIONS.items():
        result = run_part1(message)
        assert result["route"] == prediction
        assert result["final_state"]["message"] == message
        assert result["final_state"]["reply"]
        assert len(result["trace"]) == 4


def test_original_wifi_has_priority():
    result = run_part1("My Wi-Fi password does not work.")
    assert result["final_state"]["category"] == "wifi"
    assert "GUIDE-WIFI" in result["final_state"]["reply"]


def test_clarification_is_new_node():
    result = run_part1("My Wi-Fi password does not work.", True)
    assert result["final_state"]["category"] == "both"
    assert "clarify_problem" in result["route"]
    assert "wifi_help" not in result["route"]


def test_unsupported_request_asks_question():
    result = run_part1("Broken screen")
    assert result["final_state"]["category"] == "other"
    assert "Wi-Fi or a password" in result["final_state"]["reply"]
