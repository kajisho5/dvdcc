"""The one exception dvdcc raises."""


class CaptionError(Exception):
    """A caption or subtitle file cannot be used as it is."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message
