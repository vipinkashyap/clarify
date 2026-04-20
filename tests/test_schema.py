import pytest
from pydantic import ValidationError

from clarify.schema import Claim, ClaimsFile, ClaimType, Hedging, Paper, Section


def make_claim(**overrides):
    base = dict(
        id="intro-01",
        statement="Transformers dominate language modeling.",
        type=ClaimType.BACKGROUND,
        evidence=None,
        dependencies=["vaswani-2017"],
        hedging=Hedging.ASSERTED,
        section="Introduction",
        char_start=0,
        char_end=42,
    )
    base.update(overrides)
    return Claim(**base)


def test_claim_roundtrip():
    c = make_claim()
    assert Claim.model_validate_json(c.model_dump_json()) == c


def test_claim_requires_known_type():
    with pytest.raises(ValidationError):
        make_claim(type="not_a_real_type")


def test_paper_default_claims_empty():
    p = Paper(
        arxiv_id="2301.12345",
        title="Toy Paper",
        authors=["A"],
        abstract="abs",
        sections=[Section(title="Intro", level=1, text="hi", html="<p>hi</p>")],
        source_type="latex",
    )
    assert p.claims == []


def test_claims_file_accepts_bare_list_after_wrap():
    c = make_claim()
    cf = ClaimsFile(arxiv_id="2301.12345", claims=[c])
    assert cf.claims[0] == c
