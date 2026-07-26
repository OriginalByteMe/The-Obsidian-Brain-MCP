import json
from datetime import date, datetime, time

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


def _yaml_scalar(value: object) -> str:
    """Encode YAML date/time scalars; anything else is a real bug."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(payload: object) -> str:
    """Serialize a payload that may carry YAML-typed frontmatter values.

    PyYAML turns `created: 2026-07-26` into a `date`/`datetime`, which plain
    `json.dumps` refuses. Only those scalars are converted, so unexpected
    objects still surface as errors instead of being stringified silently.
    """
    return json.dumps(payload, default=_yaml_scalar)
