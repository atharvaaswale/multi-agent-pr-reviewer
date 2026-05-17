from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException

from app.github.client import GitHubClient, PR_URL_PATTERN


class TestPRURLPattern:
    def test_valid_pr_url(self):
        match = PR_URL_PATTERN.match("https://github.com/owner/repo/pull/42")
        assert match is not None
        assert match.group("owner") == "owner"
        assert match.group("repo") == "repo"
        assert match.group("number") == "42"

    def test_valid_pr_url_large_number(self):
        match = PR_URL_PATTERN.match("https://github.com/my-org/my-repo/pull/12345")
        assert match.group("owner") == "my-org"
        assert match.group("repo") == "my-repo"
        assert match.group("number") == "12345"

    def test_invalid_pr_url_no_number(self):
        assert PR_URL_PATTERN.match("https://github.com/owner/repo/pull/") is None

    def test_invalid_pr_url_wrong_domain(self):
        assert PR_URL_PATTERN.match("https://gitlab.com/owner/repo/pull/42") is None

    def test_invalid_pr_url_not_a_pr(self):
        assert PR_URL_PATTERN.match("https://github.com/owner/repo/issues/42") is None

    def test_invalid_pr_url_trailing_slash(self):
        match = PR_URL_PATTERN.match("https://github.com/owner/repo/pull/42/")
        assert match is not None
        assert match.group("number") == "42"


class TestParsePRURL:
    def test_parses_valid_url(self):
        client = GitHubClient(token="fake-token")
        owner, repo, number = client.parse_pr_url("https://github.com/owner/repo/pull/42")
        assert owner == "owner"
        assert repo == "repo"
        assert number == 42

    def test_raises_on_invalid_url(self):
        client = GitHubClient(token="fake-token")
        with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
            client.parse_pr_url("https://not-a-pr-url.com")


class TestGetRepository:
    def test_returns_repository(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "_gh") as mock_gh:
            mock_repo = MagicMock()
            mock_gh.get_repo.return_value = mock_repo

            result = client.get_repository("owner", "repo")

            mock_gh.get_repo.assert_called_once_with("owner/repo")
            assert result == mock_repo

    def test_raises_on_github_error(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "_gh") as mock_gh:
            mock_gh.get_repo.side_effect = GithubException(404, "Not Found")

            with pytest.raises(GithubException):
                client.get_repository("owner", "nonexistent")


class TestPostPRReview:
    def test_posts_comment_successfully(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get_repository") as mock_get_repo:
            mock_repo = MagicMock()
            mock_pr = MagicMock()
            mock_get_repo.return_value = mock_repo
            mock_repo.get_pull.return_value = mock_pr

            client.post_pr_review("owner", "repo", 42, "Test comment body")

            mock_repo.get_pull.assert_called_once_with(42)
            mock_pr.create_issue_comment.assert_called_once_with("Test comment body")

    def test_raises_on_github_error(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get_repository") as mock_get_repo:
            mock_get_repo.side_effect = GithubException(403, "Forbidden")

            with pytest.raises(GithubException):
                client.post_pr_review("owner", "repo", 42, "Test comment")

    def test_raises_on_pr_error(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get_repository") as mock_get_repo:
            mock_repo = MagicMock()
            mock_get_repo.return_value = mock_repo
            mock_repo.get_pull.side_effect = GithubException(404, "PR not found")

            with pytest.raises(GithubException):
                client.post_pr_review("owner", "repo", 99999, "Test comment")
