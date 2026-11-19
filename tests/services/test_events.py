from src.services import events

# Log ----------------------------------------------------------------------------------------------

def _log(session, entity_type, entity_id, action, payload=None):
    """Log an event as the web actor and commit it, as a service would."""
    event = events.log(session, events.ACTOR_WEB, entity_type, entity_id, action, payload)
    session.commit()
    return event

def test_log_records_event_fields(session):
    """Log stores who did what to which entity
    Given an event logged with a payload
    When reading it back from the history
    Then all its fields are stored
    """
    _log(session, "task", 1, "completed", {"from": "DOING", "to": "DONE"})

    [event] = events.history(session, "task", 1)
    assert event.actor == "web"
    assert event.entity_type == "task"
    assert event.entity_id == 1
    assert event.action == "completed"
    assert event.payload == {"from": "DOING", "to": "DONE"}
    assert event.at is not None

def test_log_payload_is_optional(session):
    """Log without a payload stores none
    Given an event logged without a payload
    When reading it back
    Then its payload is empty
    """
    _log(session, "task", 1, "deleted")

    [event] = events.history(session, "task", 1)
    assert event.payload is None

def test_log_does_not_commit(session):
    """Log leaves the commit to the caller
    Given an event logged and flushed but not committed
    When the session is rolled back
    Then the event is gone
    """
    events.log(session, events.ACTOR_WEB, "task", 1, "created")
    session.flush()
    session.rollback()

    assert not events.history(session, "task", 1)

def test_log_survives_commit(session):
    """Log is stored when the caller commits
    Given an event logged then committed
    When the session is rolled back afterwards
    Then the event is still there
    """
    events.log(session, events.ACTOR_WEB, "task", 1, "created")
    session.commit()
    session.rollback()

    assert len(events.history(session, "task", 1)) == 1


# History ------------------------------------------------------------------------------------------

def test_history_oldest_first(session):
    """History lists events in the order they happened
    Given three events logged for a task
    When reading its history
    Then they come back in logging order
    """
    for action in ("created", "started", "completed"):
        _log(session, "task", 1, action)

    result = events.history(session, "task", 1)
    assert [e.action for e in result] == ["created", "started", "completed"]

def test_history_scoped_to_entity(session):
    """History returns only the requested entity's events
    Given events for task 1, task 2 and a project with id 1
    When reading the history of task 1
    Then only task 1's event is returned
    """
    _log(session, "task", 1, "created")
    _log(session, "task", 2, "created")
    _log(session, "project", 1, "created")

    result = events.history(session, "task", 1)
    assert [(e.entity_type, e.entity_id) for e in result] == [("task", 1)]

def test_history_empty(session):
    """History of an entity with no events is an empty list
    Given no events
    When reading a task's history
    Then the resulting list is empty
    """
    assert not events.history(session, "task", 1)
