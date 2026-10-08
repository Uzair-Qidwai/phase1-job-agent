"""Structured candidate profile used by filtering and ranking."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_PROFILE_PATH = Path(__file__).parent.parent / "data" / "candidate_profile.json"


class CandidateProfile(BaseModel):
    version: str
    target_roles: list[str] = Field(default_factory=list)
    role_keywords: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_allowed: bool = True
    strict_locations: bool = False
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_title_keywords: list[str] = Field(default_factory=list)


def load_candidate_profile(path: Path = DEFAULT_PROFILE_PATH) -> CandidateProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(payload)
