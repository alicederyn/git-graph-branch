"""GitHub data, loaded through nix facts (ADRs 3–5)."""

from .checks import CheckStatus, pr_check_status

__all__ = ["CheckStatus", "pr_check_status"]
