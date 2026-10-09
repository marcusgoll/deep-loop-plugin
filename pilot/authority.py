"""Fail closed on protected outcome revocation, including incomplete requests."""
from admission import initialize


class OutcomeRevoked(ValueError):
    pass


def require_active(store, key):
    initialize(key)
    for suffix in ('revocation-intent', 'revoked'):
        try:
            store.read(key + '.' + suffix + '.json')
        except FileNotFoundError:
            continue
        raise OutcomeRevoked('Outcome authority revoked; only trusted cleanup is allowed')
