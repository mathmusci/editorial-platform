from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class NextAction(BaseModel):
    label: str
    command: str


def payload_value(payload: dict[str, Any], key: str) -> Any:
    if key in payload:
        return payload[key]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and key in metadata:
        return metadata[key]
    return None


def payload_subset(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}


def simple_payload_highlights(
    payload: dict[str, Any],
    *,
    limit: int = 4,
    skip_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    highlights: dict[str, Any] = {}
    for key, value in payload.items():
        if key in skip_keys:
            continue
        if isinstance(value, str | int | float | bool) or value is None:
            highlights[key] = value
        if len(highlights) >= limit:
            break
    return highlights
