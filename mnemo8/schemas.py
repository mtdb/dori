from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError


class SkillPayload(BaseModel):
    """Base payload shared by all skills.

    Notes:
    - We intentionally allow extra keys so users can extend skills without breaking validation.
    - `raw_text` is required for logging/debugging and to keep scripts deterministic.
    """

    model_config = {"extra": "allow"}

    skill: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_text: str = Field(min_length=1)


class RemindersPayload(SkillPayload):
    message: str = Field(min_length=1)
    when: str = Field(min_length=1)


class CalendarPayload(SkillPayload):
    title: str = Field(min_length=1)
    when: str = Field(min_length=1)
    duration: str | None = None
    location: str | None = None


class WebPayload(SkillPayload):
    query: str = Field(min_length=1)


class ImagesPayload(SkillPayload):
    query: str = Field(min_length=1)


class NewsPayload(SkillPayload):
    query: str = Field(min_length=1)
    since: str | None = None


class MapsPayload(SkillPayload):
    place: str = Field(min_length=1)
    directions_from: str | None = None


class CodePayload(SkillPayload):
    query: str = Field(min_length=1)
    language: str | None = None


class GitPayload(SkillPayload):
    topic: str = Field(min_length=1)
    context: str | None = None


class DockerPayload(SkillPayload):
    question: str = Field(min_length=1)


_SCHEMAS: dict[str, type[SkillPayload]] = {
    "reminders": RemindersPayload,
    "calendar": CalendarPayload,
    "web": WebPayload,
    "images": ImagesPayload,
    "news": NewsPayload,
    "maps": MapsPayload,
    "code": CodePayload,
    "git": GitPayload,
    "docker": DockerPayload,
}


def validate_skill_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and normalize a skill payload.

    Returns (normalized_payload, clarify_message). Exactly one will be non-None.
    """

    skill_name = payload.get("skill")
    schema = _SCHEMAS.get(skill_name, SkillPayload)

    try:
        model = schema.model_validate(payload)
    except ValidationError as exc:
        missing: list[str] = []
        invalid: list[str] = []
        for err in exc.errors():
            loc = err.get("loc")
            if not loc:
                continue
            field = str(loc[0])
            if err.get("type") == "missing":
                missing.append(field)
            else:
                invalid.append(field)

        if missing:
            parts = ", ".join(sorted(set(missing)))
            return None, f"I need {parts}."
        if invalid:
            parts = ", ".join(sorted(set(invalid)))
            return None, f"I need you to rephrase or restate: {parts}."
        return None, "I need one more detail before I can run that skill."

    return model.model_dump(), None
