import os
import re
from dataclasses import dataclass

import structlog
from github import Github
from github.GithubException import GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository

logger = structlog.get_logger(__name__)

PR_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


@dataclass
class PRMetadata:
    number: int
    title: str
    body: str
    state: str
    base_branch: str
    head_branch: str
    head_sha: str
    url: str


@dataclass
class ChangedFile:
    filename: str
    status: str
    additions: int
    deletions: int
    patch: str | None


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ["GITHUB_TOKEN"]
        self._gh = Github(self._token)

    def parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
        match = PR_URL_PATTERN.match(pr_url)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        return match.group("owner"), match.group("repo"), int(match.group("number"))

    def get_repository(self, owner: str, repo: str) -> Repository:
        logger.info("fetching_repository", owner=owner, repo=repo)
        try:
            return self._gh.get_repo(f"{owner}/{repo}")
        except GithubException as exc:
            logger.error("fetch_repository_failed", owner=owner, repo=repo, error=str(exc))
            raise

    def fetch_pr_metadata(self, owner: str, repo: str, pr_number: int) -> PRMetadata:
        logger.info("fetching_pr_metadata", owner=owner, repo=repo, pr_number=pr_number)
        try:
            repo_obj = self.get_repository(owner, repo)
            pr = repo_obj.get_pull(pr_number)
            return PRMetadata(
                number=pr.number,
                title=pr.title,
                body=pr.body or "",
                state=pr.state,
                base_branch=pr.base.ref,
                head_branch=pr.head.ref,
                head_sha=pr.head.sha,
                url=pr.html_url,
            )
        except GithubException as exc:
            logger.error("fetch_pr_metadata_failed", pr_number=pr_number, error=str(exc))
            raise

    def fetch_changed_files(self, owner: str, repo: str, pr_number: int) -> list[ChangedFile]:
        logger.info("fetching_changed_files", owner=owner, repo=repo, pr_number=pr_number)
        try:
            repo_obj = self.get_repository(owner, repo)
            pr = repo_obj.get_pull(pr_number)
            return [
                ChangedFile(
                    filename=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                )
                for f in pr.get_files()
            ]
        except GithubException as exc:
            logger.error("fetch_changed_files_failed", pr_number=pr_number, error=str(exc))
            raise

    def fetch_pr_diffs(self, owner: str, repo: str, pr_number: int) -> dict[str, str]:
        logger.info("fetching_pr_diffs", owner=owner, repo=repo, pr_number=pr_number)
        changed_files = self.fetch_changed_files(owner, repo, pr_number)
        return {
            f.filename: f.patch or ""
            for f in changed_files
            if f.patch
        }

    def fetch_pr_data(self, pr_url: str) -> tuple[PRMetadata, list[ChangedFile], dict[str, str]]:
        logger.info("fetching_full_pr_data", pr_url=pr_url)
        owner, repo, pr_number = self.parse_pr_url(pr_url)
        metadata = self.fetch_pr_metadata(owner, repo, pr_number)
        changed_files = self.fetch_changed_files(owner, repo, pr_number)
        diffs = {f.filename: f.patch or "" for f in changed_files if f.patch}
        return metadata, changed_files, diffs
