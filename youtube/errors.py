class StationError(Exception):
    """Safe to show. Must not carry tokens or stream keys."""


class AuthRequired(StationError):
    pass


class BroadcastError(StationError):
    pass
