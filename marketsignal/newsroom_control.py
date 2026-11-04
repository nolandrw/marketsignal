"""A bounded, auditable newsroom workflow; no LLM or publishing side effects.

Every transition is an explicit decision. Agents may request research or
revisions, but neither source text nor model output can expand budgets or
grant approval to publish. Owner approval is a separate, necessary state.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


STATES = (
    "detected", "triaged", "topic_review", "investigating", "verifying",
    "chief_editor", "drafting", "editorial_review", "copy_editing",
    "audience_review", "release_review", "pending_owner_approval",
    "spiked", "held", "approved_for_manual_release",
)
TRANSITIONS = {
    "detected": {"triaged", "spiked"},
    "triaged": {"topic_review", "spiked"},
    "topic_review": {"investigating", "spiked", "held"},
    "investigating": {"verifying", "spiked", "held"},
    "verifying": {"investigating", "chief_editor", "spiked", "held"},
    "chief_editor": {"drafting", "spiked", "held"},
    "drafting": {"editorial_review", "spiked"},
    "editorial_review": {"drafting", "copy_editing", "spiked", "held"},
    "copy_editing": {"audience_review", "verifying", "spiked"},
    "audience_review": {"release_review", "editorial_review", "spiked"},
    "release_review": {"verifying", "chief_editor", "pending_owner_approval", "held", "spiked"},
    "pending_owner_approval": {"approved_for_manual_release", "held", "spiked"},
    "held": {"topic_review", "investigating", "spiked"},
    "spiked": set(), "approved_for_manual_release": set(),
}
MAX_RESEARCH_REVISIONS = 2
MAX_WRITER_REVISIONS = 2
MAX_RELEASE_RETURNS = 1


def story_id(market_id: str, observed_at: int) -> str:
    return hashlib.sha256(f"{market_id}:{observed_at}".encode()).hexdigest()[:20]


@dataclass(frozen=True)
class ResearchTicket:
    claim_id: str
    question: str
    evidence_needed: tuple[str, ...]
    priority: str = "normal"

    def __post_init__(self):
        if (not self.claim_id or not self.question.strip() or
                not 1 <= len(self.evidence_needed) <= 5 or
                self.priority not in ("normal", "high")):
            raise ValueError("Invalid research ticket")


@dataclass(frozen=True)
class ClaimReview:
    claim_id: str
    support: str  # direct | indirect | absent
    corroboration: str  # multiple | one | none
    conflict: str  # none | disputed | refuted
    disposition: str  # approved | qualified | research | rejected
    source_ids: tuple[str, ...]
    note: str

    def __post_init__(self):
        if (self.support not in {"direct", "indirect", "absent"} or
                self.corroboration not in {"multiple", "one", "none"} or
                self.conflict not in {"none", "disputed", "refuted"} or
                self.disposition not in {"approved", "qualified", "research", "rejected"} or
                not self.claim_id or not self.note.strip()):
            raise ValueError("Invalid claim review")
        if self.disposition == "approved" and (
            self.support != "direct" or self.corroboration == "none" or
            self.conflict != "none" or not self.source_ids
        ):
            raise ValueError("Approved claim lacks direct, uncontradicted provenance")


@dataclass(frozen=True)
class TopicRubric:
    news_peg: int
    consequences: int
    editorial_potential: int
    originality: int
    research_feasibility: int
    timeliness: int
    source_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("news_peg", "consequences", "editorial_potential", "originality",
                     "research_feasibility", "timeliness"):
            if not 0 <= getattr(self, name) <= 5:
                raise ValueError("Topic rubric dimensions must be 0..5")

    @property
    def score(self) -> int:
        # Fixed, editorially chosen weights; these are not trained probabilities.
        return (self.news_peg * 4 + self.consequences * 4 +
                self.editorial_potential * 4 + self.originality * 3 +
                self.research_feasibility * 3 + self.timeliness * 2)

    @property
    def eligible(self) -> bool:
        # Preliminary only; TopicLeadAgent applies independent, mandatory gates.
        return bool(self.score >= 65 and self.news_peg > 0 and self.source_ids)


@dataclass(frozen=True)
class NarrativeHypothesis:
    hypothesis_id: str
    theory: str
    supporting_claim_ids: tuple[str, ...]
    counter_claim_ids: tuple[str, ...]
    interest_score: int
    confidence: str = "unverified"  # never a probability

    def __post_init__(self):
        if (not 0 <= self.interest_score <= 100 or
                self.confidence not in {"unverified", "partially_supported", "substantiated"}):
            raise ValueError("Invalid hypothesis rating")


@dataclass
class StoryState:
    story_id: str
    market_id: str
    observed_at: int
    state: str = "detected"
    research_revisions: int = 0
    writer_revisions: int = 0
    release_returns: int = 0
    quantitative_score: int | None = None
    topic_score: int | None = None
    topic_decision: str | None = None
    semantic_review_passed: bool = False
    risk: str = "unknown"
    owner_approved: bool = False
    dossier_audited: bool = False
    independently_sourced_claims: int = 0
    independent_origins: int = 0
    editorial_assignment_ready: bool = False
    editorial_review_passed: bool = False
    copy_review_passed: bool = False
    article_sha256: str | None = None
    copy_article_sha256: str | None = None
    human_factcheck_reference: str | None = None
    factchecked_article_sha256: str | None = None
    audience_review_recorded: bool = False
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class WorkflowController:
    """Reconciles requested stage transitions with deterministic policy."""

    @staticmethod
    def advance_investigator_v3(story: StoryState, investigation: dict,
                                oversight: object) -> StoryState:
        """Gate Investigator v3 -> Verifier through a separate overseer result.

        The overseer may return work or hold it; an Investigator self-score
        cannot directly move a case into editorial verification.
        """
        if (story.state != "investigating" or
                investigation.get("case_id") != story.story_id or
                getattr(oversight, "case_id", None) != story.story_id or
                investigation.get("publication_enabled") is not False):
            raise ValueError("Unrelated or out-of-order investigator handoff")
        disposition = investigation.get("disposition")
        if disposition == "spike":
            return WorkflowController.advance(story, "spiked", reason="investigator_v3_spiked")
        if disposition != "ready_for_verifier":
            return WorkflowController.advance(story, "held", reason="investigator_v3_unready")
        if (getattr(oversight, "status", None) != "to_verifier" or
                getattr(oversight, "issues", None) or
                getattr(oversight, "publication_enabled", True)):
            return WorkflowController.advance(story, "held", reason="handoff_overseer_blocked")
        return WorkflowController.advance(story, "verifying", reason="investigator_v3_overseen")

    @staticmethod
    def advance(story: StoryState, target: str, *, reason: str,
                owner_authorized: bool = False) -> StoryState:
        if story.state not in STATES or target not in TRANSITIONS.get(story.state, set()):
            raise ValueError("Invalid newsroom state transition")
        if not reason or len(reason) > 250:
            raise ValueError("A bounded transition reason is required")
        if story.state == "topic_review" and target == "investigating" and not (
            story.topic_decision == "go" and story.topic_score is not None and
            story.topic_score >= 65
        ):
            raise ValueError("Topic Lead GO decision and passing score required for investigation")
        if story.state == "held" and target == "investigating" and story.topic_decision != "go":
            raise ValueError("Held topic must be re-evaluated before investigation")
        if story.state == "verifying" and target == "chief_editor" and not (
            story.dossier_audited and story.independent_origins >= 2 and
            story.independently_sourced_claims >= 4
        ):
            raise ValueError("No audited, independently sourced reporting dossier")
        if story.state == "chief_editor" and target == "drafting" and not story.editorial_assignment_ready:
            raise ValueError("Writer requires an explicit chief-editor assignment")
        if story.state == "editorial_review" and target == "copy_editing" and not story.editorial_review_passed:
            raise ValueError("Editor has not approved this draft")
        if story.state == "copy_editing" and target == "audience_review" and not (
            story.copy_review_passed and story.article_sha256 and
            story.article_sha256 == story.copy_article_sha256
        ):
            raise ValueError("Copy artifact does not match the editor-reviewed article")
        if story.state == "audience_review" and target == "release_review" and not story.audience_review_recorded:
            raise ValueError("Audience diagnostic must be recorded, not necessarily positive")
        if story.state == "verifying" and target == "investigating":
            story.research_revisions += 1
            if story.research_revisions > MAX_RESEARCH_REVISIONS:
                story.state = "held"
                story.problems.append("research_revision_budget_exhausted")
                return story
        if story.state == "editorial_review" and target == "drafting":
            story.writer_revisions += 1
            if story.writer_revisions > MAX_WRITER_REVISIONS:
                story.state = "held"
                story.problems.append("writer_revision_budget_exhausted")
                return story
        if story.state == "release_review" and target in {"verifying", "chief_editor"}:
            story.release_returns += 1
            if story.release_returns > MAX_RELEASE_RETURNS:
                story.state = "held"
                story.problems.append("release_revision_budget_exhausted")
                return story
            story.semantic_review_passed = False
        if target == "pending_owner_approval" and (not story.semantic_review_passed or
                                                   story.risk != "low" or
                                                   not story.dossier_audited or
                                                   not story.editorial_review_passed or
                                                   not story.copy_review_passed or
                                                   not story.audience_review_recorded or
                                                   not story.human_factcheck_reference or
                                                   not story.article_sha256 or
                                                   story.copy_article_sha256 != story.article_sha256 or
                                                   story.factchecked_article_sha256 != story.article_sha256):
            raise ValueError("Unverified or elevated-risk story cannot request release")
        if target == "approved_for_manual_release":
            if not (owner_authorized and story.semantic_review_passed and story.risk == "low" and
                    story.owner_approved is False and story.human_factcheck_reference and
                    story.factchecked_article_sha256 == story.copy_article_sha256 == story.article_sha256):
                raise ValueError("Explicit owner approval and independent review are required")
            story.owner_approved = True
        story.state = target
        return story


def accept_structural_dossier(story: StoryState, candidate: object,
                              dossier: object) -> tuple[str, ...]:
    """Use the existing independent dossier policy; never imply semantic truth."""
    from .feature_story import NewspaperEditor, audit_dossier

    if story.state != "verifying" or getattr(candidate, "candidate_id", None) != \
            getattr(dossier, "candidate_id", None):
        raise ValueError("Dossier belongs to a different story or stage")
    issues = audit_dossier(dossier, candidate)
    plan = NewspaperEditor().plan(candidate, dossier)
    if issues or plan.blockers or plan.disposition != "draft_shadow":
        story.dossier_audited = False
        return tuple(sorted(set(issues + plan.blockers)))
    story.dossier_audited = True
    story.independent_origins = plan.independent_origins
    story.independently_sourced_claims = len(dossier.claims)
    return ()


class StoryLedger:
    """Append-only private SQLite event ledger; never write it to public Git."""

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.filename)
        self.db.execute("""CREATE TABLE IF NOT EXISTS story_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            state TEXT NOT NULL, agent TEXT NOT NULL, reason_code TEXT NOT NULL,
            metadata TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS story_idx ON story_events(story_id,event_id)")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "StoryLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def record(self, state: StoryState, agent: str, reason_code: str,
               metrics: dict[str, int | float | bool | str] | None = None,
               *, now: int | None = None) -> str:
        """Only small non-sensitive metrics, not sources, allegations, or prompts."""
        metrics = metrics or {}
        if (not agent.isidentifier() or len(agent) > 60 or
                not reason_code.replace("_", "").isalnum() or len(reason_code) > 80 or
                len(metrics) > 15 or any(not k.isidentifier() or len(k) > 50 or
                                         not isinstance(v, (str, int, float, bool)) or
                                         (isinstance(v, float) and not math.isfinite(v)) or
                                         (isinstance(v, str) and len(v) > 90)
                                         for k, v in metrics.items())):
            raise ValueError("Unsafe or oversized audit metadata")
        timestamp = int(time.time()) if now is None else now
        previous_row = self.db.execute(
            "SELECT event_hash FROM story_events WHERE story_id=? ORDER BY event_id DESC LIMIT 1",
            (state.story_id,)).fetchone()
        previous = previous_row[0] if previous_row else "GENESIS"
        payload = {"story_id": state.story_id, "created_at": timestamp,
                   "state": state.state, "agent": agent, "reason_code": reason_code,
                   "metadata": metrics, "previous_hash": previous}
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        with self.db:
            self.db.execute("""INSERT INTO story_events
                (story_id,created_at,state,agent,reason_code,metadata,previous_hash,event_hash)
                VALUES (?,?,?,?,?,?,?,?)""",
                (state.story_id, timestamp, state.state, agent, reason_code,
                 json.dumps(metrics, sort_keys=True), previous, digest))
        return digest

    def metrics(self) -> dict:
        rows = self.db.execute("""SELECT agent,reason_code,COUNT(*) FROM story_events
                                  GROUP BY agent,reason_code ORDER BY COUNT(*) DESC""").fetchall()
        by_agent: dict[str, dict[str, int]] = {}
        for agent, reason, count in rows:
            by_agent.setdefault(agent, {})[reason] = count
        return {"event_count": sum(sum(v.values()) for v in by_agent.values()),
                "agents": by_agent}

    def events(self, story_id: str) -> tuple[dict, ...]:
        rows = self.db.execute("""SELECT created_at,state,agent,reason_code,metadata,
                                previous_hash,event_hash FROM story_events
                                WHERE story_id=? ORDER BY event_id""", (story_id,)).fetchall()
        return tuple({"created_at": r[0], "state": r[1], "agent": r[2],
                      "reason_code": r[3], "metadata": json.loads(r[4]),
                      "previous_hash": r[5], "event_hash": r[6]} for r in rows)

    def verify_chain(self, story_id: str) -> bool:
        previous = "GENESIS"
        for entry in self.events(story_id):
            if entry["previous_hash"] != previous:
                return False
            payload = {"story_id": story_id, "created_at": entry["created_at"],
                       "state": entry["state"], "agent": entry["agent"],
                       "reason_code": entry["reason_code"],
                       "metadata": entry["metadata"], "previous_hash": previous}
            expected = hashlib.sha256(json.dumps(payload, sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
            if expected != entry["event_hash"]:
                return False
            previous = expected
        return True
