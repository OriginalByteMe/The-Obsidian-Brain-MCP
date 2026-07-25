import json

from ..exceptions import CLINotFoundError, ObsidianCLIError, ObsidianNotRunningError


OPERATIONAL_ERRORS: tuple[type[Exception], ...] = (
    CLINotFoundError,
    ObsidianCLIError,
    ObsidianNotRunningError,
)


def error_json(error: Exception) -> str:
    return json.dumps(
        {
            "error": True,
            "type": type(error).__name__,
            "message": str(error),
        }
    )
