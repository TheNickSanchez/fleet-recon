from __future__ import annotations

from fleet_session_host.runs import RunStore


def test_thread_history_round_trip():
    store = RunStore()
    assert store.get_thread_history("thread-1") == []
    store.append_thread_history("thread-1", "user", "hello")
    store.append_thread_history("thread-1", "assistant", "hi there")
    assert store.get_thread_history("thread-1") == [("user", "hello"), ("assistant", "hi there")]
    # A different thread never sees another thread's history.
    assert store.get_thread_history("thread-2") == []


def test_thread_history_caps_at_max_turns():
    store = RunStore()
    for i in range(20):
        store.append_thread_history("thread-1", "user", f"turn {i}")
    history = store.get_thread_history("thread-1")
    assert len(history) == 12  # MAX_HISTORY_TURNS
    assert history[0] == ("user", "turn 8")  # oldest turns dropped, not newest
    assert history[-1] == ("user", "turn 19")


def test_create_and_update_run():
    store = RunStore()
    run = store.create(thread_id="thread-1", input_kind="text")
    assert run.status == "queued"
    assert run.thread_id == "thread-1"
    assert run.activity == []

    store.update(run.id, status="completed", result={"type": "chat.text", "text": "hi"})
    updated = store.get(run.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.result == {"type": "chat.text", "text": "hi"}
    assert updated.updated_at >= updated.created_at


def test_append_activity_while_running():
    store = RunStore()
    run = store.create(thread_id="thread-1", input_kind="text")
    store.update(run.id, status="running")

    store.append_activity(run.id, "Calling jamf -> get_computer_by_username...")
    store.append_activity(run.id, "Got a result back.")

    updated = store.get(run.id)
    assert updated is not None
    assert updated.activity == [
        "Calling jamf -> get_computer_by_username...",
        "Got a result back.",
    ]


def test_append_activity_is_a_noop_once_terminal():
    # A chat turn's background task can keep reporting progress after the
    # store already marked the run failed/completed -- that must not
    # resurrect or mutate a terminal run's activity feed.
    store = RunStore()
    run = store.create(thread_id="thread-1", input_kind="text")
    store.update(run.id, status="completed", result={"type": "chat.text", "text": "hi"})

    store.append_activity(run.id, "Calling jamf...")

    assert store.get(run.id).activity == []


def test_append_activity_unknown_run_is_a_noop():
    store = RunStore()
    store.append_activity("does-not-exist", "Calling jamf...")  # must not raise
