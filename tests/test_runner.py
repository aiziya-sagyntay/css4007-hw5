from helpdesk.runner import split_at_restarts


def test_restart_causes_separate_process_segments():
    events = [{"action": "message", "message": "a"},
              {"action": "restart_process", "preserve_local_storage": True},
              {"action": "message", "message": "b"}]
    segments, restarts = split_at_restarts(events)
    assert restarts == 1
    assert len(segments) == 2
    assert segments[0][0]["message"] == "a"
    assert segments[1][0]["message"] == "b"
