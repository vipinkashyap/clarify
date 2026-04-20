from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel


class ClaimType(str, Enum):
    EMPIRICAL = "empirical_result"
    METHODOLOGICAL = "methodological_claim"
    THEORETICAL = "theoretical_claim"
    BACKGROUND = "background_claim"
    LIMITATION = "limitation"


class Hedging(str, Enum):
    ASSERTED = "asserted"
    SUGGESTED = "suggested"
    SPECULATED = "speculated"


class Claim(BaseModel):
    id: str
    statement: str
    type: ClaimType
    evidence: Optional[str] = None
    dependencies: list[str] = []
    hedging: Hedging
    section: str
    char_start: int
    char_end: int
    plain_language: Optional[str] = None


class Section(BaseModel):
    title: str
    level: int
    text: str
    html: str


class Paper(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    sections: list[Section]
    claims: list[Claim] = []
    source_type: Literal["latex", "pdf"]
    primary_category: Optional[str] = None
    categories: list[str] = []


class ClaimsFile(BaseModel):
    """Shape of the JSON Claude Code writes after extraction."""

    arxiv_id: str
    claims: list[Claim]
