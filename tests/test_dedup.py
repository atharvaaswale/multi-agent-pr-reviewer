import pytest

from app.schemas.review import Finding, FindingCategory, Severity
from app.utils.dedup import canonicalize_title, deduplicate_findings


def _finding(
    title: str = "Issue",
    severity: Severity = Severity.medium,
    file_path: str | None = "app.py",
    line_number: int | None = 10,
    category: FindingCategory = FindingCategory.security,
) -> Finding:
    return Finding(
        title=title,
        description="description",
        severity=severity,
        category=category,
        file_path=file_path,
        line_number=line_number,
    )


class TestDeduplicateFindings:
    def test_empty_list(self):
        assert deduplicate_findings([]) == []

    def test_unique_findings_unchanged(self):
        findings = [
            _finding(title="A", line_number=1),
            _finding(title="B", line_number=2),
        ]
        assert len(deduplicate_findings(findings)) == 2

    def test_exact_duplicates_collapsed(self):
        findings = [_finding(title="Same"), _finding(title="Same")]
        assert len(deduplicate_findings(findings)) == 1

    def test_keeps_highest_severity(self):
        findings = [
            _finding(title="Leak", severity=Severity.low),
            _finding(title="Leak", severity=Severity.critical),
            _finding(title="Leak", severity=Severity.medium),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0].severity == Severity.critical

    def test_title_normalized_case_and_whitespace(self):
        findings = [
            _finding(title="SQL Injection"),
            _finding(title="  sql injection  "),
        ]
        assert len(deduplicate_findings(findings)) == 1

    def test_different_line_numbers_not_duplicates(self):
        findings = [
            _finding(title="Same", line_number=10),
            _finding(title="Same", line_number=20),
        ]
        assert len(deduplicate_findings(findings)) == 2

    def test_different_files_not_duplicates(self):
        findings = [
            _finding(title="Same", file_path="a.py"),
            _finding(title="Same", file_path="b.py"),
        ]
        assert len(deduplicate_findings(findings)) == 2

    def test_duplicates_across_categories_collapsed(self):
        # Same location and title raised by different agents.
        findings = [
            _finding(title="Risk", category=FindingCategory.security),
            _finding(title="Risk", category=FindingCategory.quality),
        ]
        assert len(deduplicate_findings(findings)) == 1

    def test_severity_tie_keeps_first_occurrence(self):
        first = _finding(title="Tie", severity=Severity.high)
        second = _finding(title="Tie", severity=Severity.high)
        result = deduplicate_findings([first, second])
        assert len(result) == 1
        assert result[0] is first

    def test_findings_without_location_deduplicated_by_title(self):
        findings = [
            _finding(title="Generic", file_path=None, line_number=None),
            _finding(title="Generic", file_path=None, line_number=None),
        ]
        assert len(deduplicate_findings(findings)) == 1

    def test_order_preserved(self):
        findings = [
            _finding(title="First", line_number=1),
            _finding(title="Second", line_number=2),
            _finding(title="First", line_number=1, severity=Severity.high),
        ]
        result = deduplicate_findings(findings)
        assert [f.title for f in result] == ["First", "Second"]


class TestCanonicalizeTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "Exposed Secret",
            "Hardcoded Secret",
            "hardcoded secret",
            "Hardcoded API key",
            "API key exposed",
            "Hard-coded credential!",
            "exposed   secret",
            "Leaked access key",
        ],
    )
    def test_secret_variants_canonicalize_together(self, title):
        assert canonicalize_title(title) == "hardcoded_secret"

    @pytest.mark.parametrize(
        "title",
        [
            "MD5 usage",
            "Insecure hashing",
            "Insecure password hashing",
            "Weak hash algorithm",
            "Use of SHA-1 digest",
        ],
    )
    def test_hashing_variants_canonicalize_together(self, title):
        assert canonicalize_title(title) == "insecure_hashing"

    @pytest.mark.parametrize(
        "title",
        [
            "Unclear function name",
            "Bad function name",
            "Misleading variable name",
            "Inconsistent naming",
            "Naming convention violation",
        ],
    )
    def test_naming_variants_canonicalize_together(self, title):
        assert canonicalize_title(title) == "naming_issue"

    def test_unrelated_titles_get_distinct_canonical_forms(self):
        assert canonicalize_title("SQL Injection") != canonicalize_title("Exposed secret")
        assert canonicalize_title("SQL Injection") != canonicalize_title("MD5 usage")

    def test_unmatched_title_falls_back_to_normalized_form(self):
        assert canonicalize_title("SQL Injection!") == "sql_injection"
        assert canonicalize_title("  Path   Traversal  ") == "path_traversal"

    def test_case_and_punctuation_insensitive(self):
        assert canonicalize_title("SQL-Injection") == canonicalize_title("sql injection")

    def test_empty_title(self):
        assert canonicalize_title("") == ""
        assert canonicalize_title("   ") == ""


class TestSemanticDeduplication:
    def test_semantic_title_variants_collapse(self):
        findings = [
            _finding(title="Exposed Secret", severity=Severity.medium),
            _finding(title="Hardcoded Secret", severity=Severity.high),
            _finding(title="hardcoded api key", severity=Severity.low),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0].severity == Severity.high

    def test_semantic_duplicates_collapse_across_categories(self):
        findings = [
            _finding(title="Exposed secret", category=FindingCategory.security),
            _finding(title="Hardcoded API key", category=FindingCategory.quality),
        ]
        assert len(deduplicate_findings(findings)) == 1

    def test_unrelated_findings_do_not_collapse(self):
        findings = [
            _finding(title="Exposed secret"),
            _finding(title="SQL injection"),
        ]
        assert len(deduplicate_findings(findings)) == 2

    def test_semantic_duplicates_on_different_lines_stay_separate(self):
        findings = [
            _finding(title="Exposed secret", line_number=10),
            _finding(title="Hardcoded secret", line_number=42),
        ]
        assert len(deduplicate_findings(findings)) == 2

    def test_insecure_hashing_variants_collapse(self):
        findings = [
            _finding(title="MD5 usage", severity=Severity.low),
            _finding(title="Insecure password hashing", severity=Severity.high),
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0].severity == Severity.high
