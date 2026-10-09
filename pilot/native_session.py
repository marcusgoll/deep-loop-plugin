"""Parse native JSONL session observations from a protected host capture.

This parser authenticates no input by itself. Its caller must prove the capture
belongs to the exact pinned native unit/invocation and is inaccessible to the
candidate. Candidate text, nested tool output and final prose are not events.
"""
import json
import uuid

MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024


def session_from_capture(data, expected_session=None, *, complete=True):
    if not isinstance(data, bytes) or len(data) > MAX_CAPTURE_BYTES:
        raise ValueError('Invalid or oversized native capture')
    if expected_session is not None:
        _uuid(expected_session)
    session = None
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if len(line) > MAX_LINE_BYTES:
            raise ValueError('Oversized native event')
        # A live read can end between writes. Ignore only its incomplete tail;
        # stopped captures must be complete and parse without repair.
        if not line.endswith(b'\n'):
            if not complete and index == len(lines)-1:
                break
            raise ValueError('Incomplete stopped native capture')
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError('Malformed native JSONL event') from exc
        if not isinstance(event, dict) or not isinstance(event.get('type'), str):
            raise ValueError('Malformed native event envelope')
        if event['type'] != 'thread.started':
            continue
        # Only the native top-level event establishes the session, never a
        # similarly shaped object embedded in tool output or agent prose.
        if set(event) != {'type', 'thread_id'}:
            raise ValueError('Unexpected native session event schema')
        observed = event['thread_id']
        _uuid(observed)
        if session is not None and session != observed:
            raise ValueError('Multiple native sessions in one capture')
        if expected_session is not None and expected_session != observed:
            raise ValueError('Native resume changed session identity')
        session = observed
    return session


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError('Canonical native session UUID required')
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError('Canonical native session UUID required') from exc
    if str(parsed) != value or parsed.int == 0:
        raise ValueError('Canonical nonzero native session UUID required')
