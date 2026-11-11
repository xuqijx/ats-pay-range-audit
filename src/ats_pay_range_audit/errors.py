class UsageError(Exception):
    """Bad invocation or a local IO path this tool refuses to use. Exit code 2."""


class FetchError(Exception):
    """A documented GET failed, redirected, or could not be parsed. Exit code 1 when recorded."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message
