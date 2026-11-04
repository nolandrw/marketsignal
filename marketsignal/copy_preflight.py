"""Deterministic copy-desk artifact checks, not a model copy editor.

This module checks that formatting or link assembly has not changed the
evidence-bound story. It does not verify facts, copyright rights, or render a
public site. Unknown photo rights always fail closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from .feature_story import NewspaperDraft, SourceDocument


def article_digest(draft: NewspaperDraft) -> str:
    """A fingerprint of the exact editor-reviewed headline and draft text."""
    content = {"headline": draft.headline, "deck": draft.deck,
               "paragraphs": [asdict(p) for p in draft.paragraphs]}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CopyLink:
    source_id: str
    url: str


@dataclass(frozen=True)
class CopyImage:
    url: str
    alt_text: str
    credit: str
    rights_reference: str  # externally checked rights record, not a model guess


@dataclass(frozen=True)
class CopyArtifact:
    headline: str
    deck: str
    paragraph_texts: tuple[str, ...]
    approved_article_sha256: str
    links: tuple[CopyLink, ...]
    images: tuple[CopyImage, ...] = ()


def prepare_copy_artifact(draft: NewspaperDraft,
                          sources: tuple[SourceDocument, ...]) -> CopyArtifact:
    """Build an unmodified private baseline suitable for a later copy editor."""
    used = {source_id for paragraph in draft.paragraphs for source_id in paragraph.source_ids}
    return CopyArtifact(draft.headline, draft.deck,
                        tuple(p.text for p in draft.paragraphs), article_digest(draft),
                        tuple(CopyLink(source.source_id, source.url)
                              for source in sources if source.source_id in used))


def check_copy_artifact(draft: NewspaperDraft,
                        sources: tuple[SourceDocument, ...],
                        artifact: CopyArtifact) -> tuple[str, ...]:
    """Validate provenance and semantic immutability; return specific issues."""
    issues: list[str] = []
    expected_hash = article_digest(draft)
    if artifact.approved_article_sha256 != expected_hash:
        issues.append("article_digest_mismatch")
    if (artifact.headline != draft.headline or artifact.deck != draft.deck or
            artifact.paragraph_texts != tuple(p.text for p in draft.paragraphs)):
        issues.append("copy_modified_editor_approved_prose")

    source_map = {source.source_id: source for source in sources}
    used = {sid for paragraph in draft.paragraphs for sid in paragraph.source_ids}
    links = {link.source_id: link.url for link in artifact.links}
    if len(links) != len(artifact.links) or set(links) != used or not used <= set(source_map):
        issues.append("missing_or_extra_source_link")
    for source_id, url in links.items():
        try:
            parts = urlsplit(url)
            valid_url = parts.scheme == "https" and bool(parts.hostname) and not (
                parts.username or parts.password)
        except ValueError:
            valid_url = False
        if (source_id not in source_map or url != source_map[source_id].url or
                not valid_url or
                any(term in url.lower() for term in ("referral=", "affiliate=", "aff_id="))):
            issues.append("altered_or_unsafe_source_link")
    for image in artifact.images:
        try:
            parts = urlsplit(image.url)
            valid_url = parts.scheme == "https" and bool(parts.hostname) and not (
                parts.username or parts.password)
        except ValueError:
            valid_url = False
        if (not valid_url or
                not image.alt_text.strip() or not image.credit.strip() or
                not image.rights_reference.strip()):
            issues.append("unlicensed_or_unattributed_image")

    return tuple(sorted(set(issues)))
