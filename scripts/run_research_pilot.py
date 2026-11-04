"""Four-case unpublished research pilot. Requires private inputs and opt-in key.

This is not a collector or a scheduled publishing path. One sequential run
shares the $2 SQLite ledger; the provider project must additionally enforce
a hard $2 limit because GitHub Actions runners are ephemeral between runs.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

from marketsignal.cli import main as run_cli
from marketsignal.evaluation_harness import load_test_fixture
from marketsignal.model_budget import ModelBudget
from marketsignal.research_runtime import configure_research_sources, load_seed_captures
from marketsignal.topic_lead import load_topic_context


EXPECTED_IDS = {"hormuz": "2176270", "ipo": "1321561",
                "fed": "3215008", "uap": "703257"}
MANIFEST = Path("data/private/pilot-manifest.json")
LIMIT_USD = "2.00"
MAX_ARCHIVE_BYTES = 36_000  # base64 below GitHub's 48-KB secret ceiling
MAX_INPUT_BYTES = 250_000
PUBLISHER_DATE_BASES = {"publisher_page_metadata", "embedded_json_metadata",
                        "embedded_xml_metadata", "first_party_official_feed",
                        "publisher_document_header"}


def _private_file(value: str) -> Path:
    if not isinstance(value, str) or not re.fullmatch(r"data/private/[A-Za-z0-9_./-]+\.json", value):
        raise ValueError("Pilot inputs must be private JSON paths")
    path = Path(value)
    if ".." in path.parts or not path.resolve().is_relative_to(Path("data/private").resolve()):
        raise ValueError("Pilot path escapes its private directory")
    return path


def _rows(manifest: Path = MANIFEST) -> list[dict]:
    if manifest != MANIFEST or not manifest.is_file() or manifest.stat().st_size > 8000:
        raise ValueError("Missing or oversized private pilot manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "cases"} or data["schema_version"] != 1:
        raise ValueError("Invalid pilot manifest schema")
    cases = data["cases"]
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("Pilot requires exactly four frozen subjects")
    expected_fields = {"name", "context_file", "captures_file", "policy_file",
                       "test_fixture_file", "angle_id"}
    if {case.get("name") for case in cases if isinstance(case, dict)} != set(EXPECTED_IDS):
        raise ValueError("Pilot case set is incomplete or duplicated")
    for case in cases:
        if not isinstance(case, dict) or set(case) != expected_fields or not isinstance(case["angle_id"], str) or not case["angle_id"].strip():
            raise ValueError("Invalid pilot case entry")
        for field in expected_fields - {"name", "angle_id"}:
            _private_file(case[field])
    return cases


def require_complete_source_packet(context, captures, policy: dict,
                                   source_rows: list[dict]) -> None:
    """Zero-model-cost evidence and rights gate; never certify truth here.

    In particular, three excerpt rows from one PDF count as *one* origin.
    A licensed independent reporting source must be explicitly allowlisted.
    """
    allowed = {row["host"]: row for row in policy["publishers"]}
    leads = {lead.source_id: lead for lead in context.sources}
    if (not 3 <= len(captures) <= 15 or len(captures) != len(source_rows) or
            len(leads) < len(captures) or
            {cap.source_id for cap in captures} !=
            {row.get("source_id") for row in source_rows}):
        raise ValueError("Pilot evidence inventory is incomplete")
    origins = set()
    kinds = set()
    source_kind_map = {"primary_record": {"official_record", "original_research"},
                       "independent_reporting": {"independent_reporting"},
                       "public_statement": {"statement"}}
    for capture, row in zip(captures, source_rows):
        host = urlsplit(capture.url).hostname
        permission = allowed.get(host)
        lead = leads.get(capture.source_id)
        if (not isinstance(row, dict) or row.get("source_id") != capture.source_id or
                permission is None or lead is None or
                capture.publisher != host or capture.origin_key != host or
                capture.source_kind != permission["kind"] or
                row.get("copyright_basis") != permission["copyright_basis"] or
                row.get("robots_decision") != "allowed" or
                capture.publication_date_basis not in PUBLISHER_DATE_BASES or
                not re.fullmatch(r"[a-f0-9]{64}", capture.document_sha256) or
                not capture.content_location or not capture.mime_type or
                not 0 < capture.published_at <= context.as_of or
                capture.captured_at > context.as_of + 30 * 60 or
                lead.url != capture.url or lead.publisher != capture.publisher or
                lead.origin_key != capture.origin_key or
                lead.published_at != capture.published_at or
                capture.source_kind not in source_kind_map.get(lead.source_type, set())):
            raise ValueError("Pilot source lacks original, dated, permissioned provenance")
        origins.add(capture.origin_key)
        kinds.add(capture.source_kind)
    if len(origins) < 3 or not ({"official_record", "original_research"} & kinds) or \
            "independent_reporting" not in kinds:
        raise ValueError("Pilot requires three origins, a primary source, and licensed reporting")


def preflight(cases: list[dict]) -> None:
    """Validate the entire private batch before exposing an API credential."""
    for case in cases:
        context = load_topic_context(_private_file(case["context_file"]))
        fixture = load_test_fixture(_private_file(case["test_fixture_file"]))
        captures_file = _private_file(case["captures_file"])
        captures = load_seed_captures(captures_file)
        policy_file = _private_file(case["policy_file"])
        if policy_file.stat().st_size > 64_000:
            raise ValueError("Oversized research policy")
        policy = json.loads(policy_file.read_text(encoding="utf-8"))
        configure_research_sources(policy)  # construction only; no external fetch
        source_packet = json.loads(captures_file.read_text(encoding="utf-8"))
        if not isinstance(source_packet, dict) or not isinstance(source_packet.get("source_rows"), list):
            raise ValueError("Pilot requires an original source-capture packet")
        lead_sources = {lead.source_id: lead for lead in context.sources}
        if (context.quantitative_pitch.market_id != EXPECTED_IDS[case["name"]] or
                context.story_id != fixture.case_id or fixture.market_id != EXPECTED_IDS[case["name"]] or
                context.as_of != fixture.as_of or not context.coverage_checked or
                any(source.published_at > context.as_of for source in captures) or
                not any(capture.source_id in lead_sources and
                        capture.url == lead_sources[capture.source_id].url
                        for capture in captures)):
            raise ValueError("Pilot identity, coverage, or source clock mismatch")
        require_complete_source_packet(context, captures, policy,
                                       source_packet["source_rows"])


def run() -> int:
    cases = _rows()
    preflight(cases)
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("API key absent; no paid pilot started")
    ledger = ModelBudget("data/private/pilot-model-budget.sqlite", LIMIT_USD)
    for case in cases:
        name = case["name"]
        args = ["research-v3-shadow", "--context-file", case["context_file"],
                "--captures-file", case["captures_file"],
                "--policy-file", case["policy_file"],
                "--test-fixture-file", case["test_fixture_file"],
                "--angle-id", case["angle_id"],
                "--max-model-spend-usd", LIMIT_USD,
                "--model-budget-db", str(ledger.path),
                "--out", f"data/private/pilot-results/{name}.json"]
        if run_cli(args) != 0:
            raise RuntimeError("A pilot case failed; remaining cases were not billed")
    print(json.dumps({"pilot": "attempted_shadow_only", "publication_enabled": False,
                      "spending": ledger.summary()}))
    return 0


def pack() -> None:
    """Create a bounded, secret-ready private bundle from explicit inputs."""
    cases = _rows()
    preflight(cases)
    files = {str(MANIFEST)}
    for case in cases:
        files.update(case[field] for field in ("context_file", "captures_file",
                                                "policy_file", "test_fixture_file"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for file in sorted(files):
            if Path(file).stat().st_size > 64_000:
                raise ValueError("Oversized pilot input")
            archive.add(file, arcname=file, recursive=False)
    payload = buf.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Private bundle exceeds GitHub secret capacity")
    target = Path("data/private/pilot-bundle.b64")
    target.write_bytes(base64.b64encode(payload))
    print(json.dumps({"bundle": str(target), "case_count": 4,
                      "secret_name": "MARKETSIGNAL_PILOT_BUNDLE_B64"}))


def unpack_from_secret() -> None:
    """Fail closed on traversal, links, oversize or unexpected archive entries."""
    encoded = os.environ.get("MARKETSIGNAL_PILOT_BUNDLE_B64", "")
    if not encoded or len(encoded) > 48_000:
        raise ValueError("Private research bundle is absent or too large")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("Invalid private research bundle") from None
    if len(compressed) > MAX_ARCHIVE_BYTES:
        raise ValueError("Oversized private research bundle")
    pending: list[tuple[Path, bytes]] = []
    total_size = 0
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:gz") as archive:
        members = archive.getmembers()
        if not 2 <= len(members) <= 20:
            raise ValueError("Invalid private input count")
        for member in members:
            path = _private_file(member.name)
            if not member.isfile() or member.size > 64_000 or any(p == path for p, _ in pending):
                raise ValueError("Unsafe private bundle entry")
            total_size += member.size
            if total_size > MAX_INPUT_BYTES:
                raise ValueError("Unbounded private input payload")
            file = archive.extractfile(member)
            if file is None:
                raise ValueError("Missing private input body")
            data = file.read(member.size + 1)
            if len(data) != member.size:
                raise ValueError("Invalid private input length")
            pending.append((path, data))
    if MANIFEST not in (path for path, _ in pending):
        raise ValueError("Pilot manifest absent")
    for path, data in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unpublished $2 four-case pilot")
    parser.add_argument("mode", choices=("pack", "run", "run-from-secret"))
    args = parser.parse_args()
    try:
        if args.mode == "pack":
            pack()
            return 0
        if args.mode == "run-from-secret":
            unpack_from_secret()
        return run()
    except (ValueError, OSError, EOFError, KeyError, TypeError,
            RuntimeError, tarfile.TarError) as exc:
        # No model inputs, encoded secrets or publisher URLs in Action logs.
        print(json.dumps({"pilot": "held", "reason": type(exc).__name__,
                          "publication_enabled": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
