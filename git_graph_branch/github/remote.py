"""Find the GitHub repository and GraphQL endpoint of a git remote."""

import re
from collections.abc import Hashable
from dataclasses import dataclass
from os import environ
from urllib.request import getproxies, proxy_bypass

from ..git.branch import Branch, RemoteBranch
from ..git.config import http_config, remote_push_default, remote_url
from .store import assumes_no_pr, read_push_state
from .transport import Endpoint


@dataclass(frozen=True)
class Repository:
    domain: str
    owner: str
    name: str


HTTPS_URL = re.compile(r"^https://([^/]*)/([^/]*)/([^/]*?)(?:\.git)?$")
GIT_URL = re.compile(r"^git@([^:]*):([^/]*)/([^/]*?)(?:\.git)?$")


def parse_repo_url(url: str) -> Repository | None:
    """Parse a GitHub repository URL

    >>> parse_repo_url("https://github.com/alicederyn/git-sync.git")
    Repository(domain='github.com', owner='alicederyn', name='git-sync')
    >>> parse_repo_url("git@github.com:alicederyn/git-graph-branch.git")
    Repository(domain='github.com', owner='alicederyn', name='git-graph-branch')
    >>> parse_repo_url("https://github.com/alicederyn/git-graph-branch")
    Repository(domain='github.com', owner='alicederyn', name='git-graph-branch')
    >>> parse_repo_url("/tmp/repo") is None
    True
    """
    m = HTTPS_URL.match(url) or GIT_URL.match(url)
    return Repository(*m.groups()) if m else None


def new_pr_url(repository: Repository, branch: str) -> str:
    """The link that GitHub shows on the first push of branch.

    >>> new_pr_url(Repository("github.com", "alicederyn", "git-sync"), "feature/x")
    'https://github.com/alicederyn/git-sync/pull/new/feature/x'
    """
    return f"https://{repository.domain}/{repository.owner}/{repository.name}/pull/new/{branch}"


def remote_repository(remote: str) -> Repository | None:
    url = remote_url(remote)
    return parse_repo_url(url) if url else None


def token_envvar(domain: str) -> str:
    """The environment variable that holds the token for domain.

    >>> token_envvar("github.com")
    'GITHUB_TOKEN'
    >>> token_envvar("bbgithub.example.com")
    'BBGITHUB_TOKEN'
    """
    return domain.split(".", maxsplit=1)[0].upper() + "_TOKEN"


def graphql_url(domain: str) -> str:
    """
    >>> graphql_url("github.com")
    'https://api.github.com/graphql'
    >>> graphql_url("bbgithub.example.com")
    'https://bbgithub.example.com/api/graphql'
    """
    if domain.count(".") == 1:
        return f"https://api.{domain}/graphql"
    return f"https://{domain}/api/graphql"


def proxy(domain: str, http: dict[str, str]) -> str | None:
    if proxy := http.get("proxy"):
        return proxy
    if proxy_bypass(domain):
        return None
    return getproxies().get("https")


def endpoint(domain: str) -> Endpoint | None:
    """The GraphQL endpoint for domain, or None if there is no token for it.

    Proxy and CA settings come from git's config for the domain, not for the API
    URL, as `[http "https://github.com"]` does not match api.github.com.
    """
    token = environ.get(token_envvar(domain))
    if not token:
        return None
    http = http_config(f"https://{domain}")
    return Endpoint(
        url=graphql_url(domain),
        token=token,
        proxy=proxy(domain, http),
        cafile=http.get("sslcainfo"),
    )


def github_repository(remote: str) -> tuple[Endpoint, Repository] | None:
    """The GraphQL endpoint and repository of a remote, if it is on GitHub and
    there is a token for it."""
    repository = remote_repository(remote)
    if repository is None:
        return None
    github = endpoint(repository.domain)
    return (github, repository) if github else None


def pr_remote_branch(branch: Branch) -> RemoteBranch | None:
    """The status branch: the remote branch whose open PR is the branch's PR
    (ADRs 5 and 8).

    This is the branch on the pushdefault remote if its remote-tracking branch
    exists, else the upstream branch if it is on a remote and its
    remote-tracking branch exists.
    """
    if downstream := branch.downstream:
        return downstream
    upstream = branch.upstream
    return upstream if isinstance(upstream, RemoteBranch) else None


@dataclass(frozen=True)
class PushTarget:
    """The remote branch that a push of the branch makes or changes (ADR 8)."""

    remote: str
    name: str

    @property
    def tracking(self) -> RemoteBranch | None:
        """The remote-tracking branch, if it exists."""
        b = RemoteBranch(self.remote, self.name)
        return b if b.exists() else None


def push_target(branch: Branch) -> PushTarget | None:
    """The branch of the same name on the pushdefault remote, else the upstream
    branch if it is on a remote.

    Taken from config, so the push target of a branch that has not been pushed
    is known before the push.
    """
    if push_remote := remote_push_default():
        return PushTarget(push_remote, branch.name)
    upstream = branch.upstream_config
    if upstream is None or upstream[0] == ".":
        return None
    return PushTarget(*upstream)


@dataclass(frozen=True)
class StatusBranch:
    """The status branch on GitHub, with the endpoint to load its data from."""

    endpoint: Endpoint
    repository: Repository
    remote: RemoteBranch

    @property
    def ref(self) -> str:
        return f"refs/heads/{self.remote.name}"

    @property
    def oid(self) -> str:
        return self.remote.commit.hash

    def assumes_no_pr(self, load: Hashable, pending: bool) -> bool:
        """Whether the load must show no PR, after a first push (ADR 8)."""
        return assumes_no_pr((self.remote.remote, self.remote.name), load, pending)


def read_push_target_state(branch: Branch) -> None:
    """Update the store record of the branch's push target, if it is on GitHub."""
    target = push_target(branch)
    if target is None or github_repository(target.remote) is None:
        return
    read_push_state((target.remote, target.name), target.tracking is not None)


def status_branch(branch: Branch) -> StatusBranch | None:
    """The branch's status branch, if it is on GitHub and there is a token for it.

    Reads the store record of the push target also when there is no status
    branch, so that the record exists before the first push. When the push
    target's remote-tracking branch exists, it is the status branch.
    """
    read_push_target_state(branch)
    remote = pr_remote_branch(branch)
    if remote is None:
        return None
    found = github_repository(remote.remote)
    if found is None:
        return None
    github, repository = found
    return StatusBranch(github, repository, remote)
