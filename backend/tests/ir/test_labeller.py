"""The reading-pass page, and the two-tier rubric behind it."""

from __future__ import annotations

import json
import re

from brahmo.ir.judgments import JudgmentSet
from brahmo.ir.labeller import build_page
from brahmo.ir.worksheet import build_pools


def _payload(page: str) -> dict:
    body = page.split("const DATA = ", 1)[1].split(";\nconst KEY", 1)[0]
    return json.loads(body)


def _payload_online(page: str) -> dict:
    body = page.split("const DATA = ", 1)[1].split(";\n\nconst PAIRS", 1)[0]
    return json.loads(body)


def test_the_page_is_self_contained() -> None:
    """It has to open from disk with no server and nothing leaving the machine."""
    page = build_page()
    assert "<script src=" not in page
    assert "<link rel=\"stylesheet\"" not in page
    assert "http://" not in page.replace("http://www.w3.org", "")
    assert "fetch(" not in page


def test_every_pooled_pair_reaches_the_page() -> None:
    data = _payload(build_page())
    expected = sum(len(p.candidates) for p in build_pools(depth=8))
    assert sum(len(q["candidates"]) for q in data["questions"]) == expected


def test_every_candidate_has_its_text_embedded() -> None:
    """A reviewer cannot judge a document id."""
    data = _payload(build_page())
    for question in data["questions"]:
        for doc_id in question["candidates"]:
            assert doc_id in data["documents"]
            assert data["documents"][doc_id]["text"]


def test_each_question_carries_its_patient_context() -> None:
    """Relevance is judged for this patient, not for the topic in the abstract."""
    data = _payload(build_page())
    for question in data["questions"]:
        assert question["patient"].startswith("Patient ")
        assert question["probes"]


def test_the_page_asks_the_answerable_question() -> None:
    """Tier 1 is reading comprehension, and the wording has to say so."""
    page = build_page()
    assert "Does this text answer this question?" in page
    assert "Yes, it answers it" in page


def test_the_essential_grade_is_marked_as_unconfirmed() -> None:
    """A non-clinician's 2 is a proposal, and the export must say so."""
    page = build_page()
    assert "looks essential" in page
    assert "NOT yet confirmed" in page


def test_the_export_shape_loads_as_a_judgment_set() -> None:
    """What the page downloads must merge without a schema change."""
    data = _payload(build_page())
    exported = {
        "schema": 1,
        "corpus": "guidelines",
        "reviewed": False,
        "reading_pass_complete": True,
        "queries": [
            {
                "id": q["id"],
                "patient_id": q["patient_id"],
                "question": q["question"],
                "judgments": {q["candidates"][0]: 1} if q["candidates"] else {},
            }
            for q in data["questions"]
        ],
    }
    loaded = JudgmentSet.from_dict(exported)
    assert len(loaded) == len(data["questions"])
    assert loaded.reading_pass_complete is True
    assert loaded.reviewed is False


def test_the_caveat_distinguishes_the_tiers() -> None:
    """Binary metrics rest on the reading pass; nDCG does not."""
    reading_only = JudgmentSet.from_dict(
        {
            "schema": 1,
            "reading_pass_complete": True,
            "queries": [{"id": "q", "judgments": {"guideline:1": 1}}],
        }
    )
    assert "Reading pass complete" in reading_only.caveat
    assert "nDCG" in reading_only.caveat

    nothing = JudgmentSet.from_dict(
        {"schema": 1, "queries": [{"id": "q", "judgments": {"guideline:1": 1}}]}
    )
    assert "no reading pass" in nothing.caveat


def test_no_grade_is_pre_filled_in_the_page() -> None:
    """Shipping opinions as defaults is the mistake this whole tier split fixes."""
    page = build_page()
    assert re.search(r"grades\s*=\s*\{\}", page)


# -- the online page --------------------------------------------------------


def test_the_online_page_carries_the_same_pairs() -> None:
    """Both pages judge the same pooled set; only where grades live differs."""
    from brahmo.ir.online import build_page as build_online

    local = _payload(build_page())
    online = _payload_online(build_online())
    assert [q["id"] for q in online["questions"]] == [q["id"] for q in local["questions"]]
    assert sum(len(q["candidates"]) for q in online["questions"]) == sum(
        len(q["candidates"]) for q in local["questions"]
    )


def test_the_online_page_reaches_the_store_defensively() -> None:
    """Opened from disk there is no namespace, and absence is a supported state."""
    from brahmo.ir.online import build_page as build_online

    page = build_online()
    assert 'window.claude?.use?.("db")' in page
    assert 'if (!store) { setStatus("offline"); return; }' in page


def test_the_online_page_writes_one_document_per_question() -> None:
    """631 writes would be a burst the store is right to throttle."""
    from brahmo.ir.online import build_page as build_online

    page = build_online()
    assert 'db.doc("grades/" + qid).set(' in page
    assert "setTimeout(() => flush(qid), 700)" in page


def test_the_online_page_renders_before_the_store_answers() -> None:
    """First paint must not wait on a capability that may never resolve."""
    from brahmo.ir.online import build_page as build_online

    page = build_online()
    body = page.split("<script>", 1)[1]
    first_render = body.index("\nrender();")
    store_call = body.index('window.claude?.use?.("db")')
    assert first_render < store_call


def test_the_online_page_only_loads_allowed_hosts() -> None:
    from brahmo.ir.online import build_page as build_online

    page = build_online()
    hosts = {
        # Close the quote before splitting the path: a bare origin like
        # href="https://fonts.gstatic.com" has no trailing slash, so splitting
        # on "/" alone carries the rest of the attribute into the host.
        line.split('href="', 1)[1].split('"', 1)[0].split("/")[2]
        for line in page.splitlines()
        if 'href="https://' in line
    }
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts
