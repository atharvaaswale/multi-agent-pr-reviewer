import re

from app.schemas.review import Finding, Severity

_SEVERITY_RANK = {
    Severity.critical: 4,
    Severity.high: 3,
    Severity.medium: 2,
    Severity.low: 1,
    Severity.info: 0,
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")
_SPACE_RE = re.compile(r"\s+")

# Semantic synonym groups. Each rule maps a canonical token to a list of
# conditions; a title matches the rule when, for *every* condition, it
# contains at least one of that condition's terms (an AND of ORs). Rules
# are evaluated top to bottom and the first match wins, so ordering is
# deterministic. Terms are matched as whole words/phrases.
_CANONICAL_RULES: list[tuple[str, list[list[str]]]] = [
    (
        "hardcoded_secret",
        [
            [
                "secret", "secrets", "api key", "api keys", "apikey",
                "credential", "credentials", "password", "passwords",
                "token", "tokens", "private key", "access key",
            ],
            [
                "hardcoded", "hard coded", "exposed", "exposure", "leaked",
                "leak", "plaintext", "plain text", "committed", "checked in",
            ],
        ],
    ),
    ("insecure_hashing", [["md5", "md4", "sha1", "sha 1"]]),
    (
        "insecure_hashing",
        [
            ["insecure", "weak", "broken", "unsafe", "deprecated"],
            ["hash", "hashing", "hashes", "hashed", "digest"],
        ],
    ),
    ("naming_issue", [["naming"]]),
    (
        "naming_issue",
        [
            [
                "unclear", "bad", "poor", "misleading", "confusing", "vague",
                "ambiguous", "inconsistent", "cryptic", "meaningless",
                "improper", "generic", "nondescriptive", "non descriptive",
            ],
            ["name", "names", "named", "identifier", "identifiers"],
        ],
    ),
]


def _normalize_title(title: str) -> str:
    """Lowercase, strip, drop punctuation and collapse repeated whitespace."""
    text = title.lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def canonicalize_title(title: str) -> str:
    """Reduce a finding title to a canonical token for semantic deduplication.

    The title is normalized (lowercased, trimmed, punctuation removed, spaces
    collapsed) and then matched against known synonym groups so that
    differently worded descriptions of the same issue collapse together --
    e.g. "Exposed Secret", "Hardcoded API key" and "api key exposed" all map
    to ``hardcoded_secret``. Titles matching no known group fall back to their
    normalized form (spaces joined with underscores), which preserves the
    previous exact-title matching behavior for everything else.

    The mapping is purely rule-based and order-deterministic.
    """
    normalized = _normalize_title(title)
    if not normalized:
        return ""

    padded = f" {normalized} "
    for canonical, conditions in _CANONICAL_RULES:
        if all(
            any(f" {term} " in padded for term in condition)
            for condition in conditions
        ):
            return canonical

    return normalized.replace(" ", "_")


def _dedup_key(finding: Finding) -> tuple:
    """Build the identity key used to detect duplicate findings.

    Two findings are treated as the same issue when they point at the same
    file and line and share the same canonicalized title, so semantically
    equivalent titles raised by different agents collapse together.
    """
    return (
        finding.file_path,
        finding.line_number,
        canonicalize_title(finding.title),
    )


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse duplicate findings, keeping the highest-severity copy of each.

    Findings are considered duplicates when they share the same file path,
    line number, and canonicalized (semantically normalized) title. When
    duplicates are found the one with the highest severity is kept; the first
    occurrence wins on a severity tie. Original ordering of the surviving
    findings is preserved.
    """
    deduped: dict[tuple, Finding] = {}

    for finding in findings:
        key = _dedup_key(finding)
        existing = deduped.get(key)
        if existing is None or _SEVERITY_RANK.get(finding.severity, 0) > _SEVERITY_RANK.get(
            existing.severity, 0
        ):
            deduped[key] = finding

    return list(deduped.values())
