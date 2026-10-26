from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from storage import SQLiteStore


MessageKind = Literal["group", "c2c"]


@dataclass(frozen=True, slots=True)
class MessageContext:
    kind: MessageKind
    scope_id: str
    user_id: str
    message_id: str
    content: str
    store: SQLiteStore

    @property
    def is_group(self) -> bool:
        return self.kind == "group"


def clean_content(content: str) -> str:
    value = str(content or "").replace("\u200b", "").strip()
    return re.sub(r"^(?:<@!?[^>]+>\s*)+", "", value).strip()


def parse_command(content: str) -> tuple[str, list[str], str] | None:
    value = clean_content(content)
    if not value.startswith("/"):
        return None
    body = value[1:].strip()
    if not body:
        return None
    parts = body.split(maxsplit=1)
    name = parts[0].casefold()
    argument_text = parts[1].strip() if len(parts) > 1 else ""
    arguments = argument_text.split() if argument_text else []
    return name, arguments, argument_text


def command_is(content: str, *names: str) -> tuple[list[str], str] | None:
    parsed = parse_command(content)
    if parsed is None:
        return None
    name, arguments, argument_text = parsed
    if name not in {item.lstrip("/").casefold() for item in names}:
        return None
    return arguments, argument_text
