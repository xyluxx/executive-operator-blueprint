#!/usr/bin/env python3
"""Read-only, fail-closed audit of the declared public GitHub release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess  # nosec B404
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "contracts" / "public-release-policy.yaml"
POLICY_SCHEMA = ROOT / "templates" / "public-release-policy.schema.json"
REPORT_SCHEMA = ROOT / "templates" / "public-release-audit-report.schema.json"
TOKEN_RE = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|(?:Bearer|token)\s+[A-Za-z0-9._~+/=-]{20,})", re.I)
PATH_RE = re.compile(r"(?<![\w])/(?:home|Users|root|opt|srv|var/www|etc)/[^\s\"']+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str):
        return PATH_RE.sub("[REDACTED]", TOKEN_RE.sub("[REDACTED]", value))
    return value


def _check(identifier: str, ok: bool, good: str, bad: str, status: str | None = None) -> dict[str, str]:
    return {"id": identifier, "status": status or ("pass" if ok else "fail"), "summary": good if ok else bad}


def _exact(actual, contract) -> bool:
    values = set(actual)
    return values == set(contract["allowed"]) and set(contract["required"]) <= values


def git_content_digest(repository: Path, ref: str, excluded_paths: list[str]) -> str:
    """Hash every tracked blob's path, canonical Git mode, and bytes."""
    tree = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-r", "-z", ref],
        capture_output=True, timeout=120,
    )  # nosec B603 B607
    if tree.returncode != 0:
        raise RuntimeError("cannot read release Git tree")
    excluded = set(excluded_paths)
    digest = hashlib.sha256()
    for entry in tree.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, relative_bytes = entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ", 2)
        relative = relative_bytes.decode("utf-8")
        if object_type != b"blob" or relative in excluded:
            continue
        blob = subprocess.run(
            ["git", "-C", str(repository), "cat-file", "blob", object_id.decode("ascii")],
            capture_output=True, timeout=120,
        )  # nosec B603 B607
        if blob.returncode != 0:
            raise RuntimeError("cannot read release Git blob")
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(mode)
        digest.update(b"\0")
        digest.update(hashlib.sha256(blob.stdout).digest())
    return digest.hexdigest()


def audit(policy: dict[str, Any], client: Any) -> dict[str, Any]:
    data = client.collect(policy)
    repo = data.get("repository") or {}
    expected_repo = policy["repository"]
    owner = (repo.get("owner") or {}).get("login")
    checks = [
        _check("repository.identity", owner == expected_repo["owner"] and repo.get("name") == expected_repo["name"] and repo.get("visibility") == expected_repo["visibility"] and repo.get("default_branch") == expected_repo["default_branch"], "Repository identity, public visibility, and default branch match.", "Repository identity, visibility, or default branch differs."),
        _check("refs.branches", _exact(data.get("branches", []), policy["refs"]["branches"]), "Branch set matches policy.", "Branch set differs from policy."),
        _check("refs.tags", _exact((data.get("tags") or {}).keys(), policy["refs"]["tags"]), "Tag set matches policy.", "Tag set differs from policy."),
        _check("refs.releases", _exact((data.get("releases") or {}).keys(), policy["refs"]["releases"]), "Release set matches policy.", "Release set differs from policy."),
    ]
    release = policy["release"]
    tag_sha = (data.get("tags") or {}).get(release["tag"])
    commits = data.get("commits") or []
    branch_sha = (data.get("branch_heads") or {}).get(expected_repo["default_branch"])
    commit_shas = {item.get("sha") for item in commits}
    checks.append(_check("release.immutable_tag", bool(tag_sha and tag_sha == branch_sha and tag_sha in commit_shas), "Release tag, default branch, and audited commit agree.", "Release tag is absent or differs from the default branch or audited commit."))
    checks.append(_check("release.commit_count", len(commits) == release["commit_count"]["expected"], "Candidate commit count matches policy.", "Candidate commit count differs from policy."))
    expected_content = release["content_digest"]["sha256"]
    checks.append(_check("release.content_digest", data.get("content_digest") == expected_content, "Tracked release content matches the policy digest.", "Tracked release content differs from the policy digest."))
    allowed_git = {(item["name"], item["email"]) for item in policy["identities"]["allowed_git_identities"]}
    identities_ok = bool(commits) and all((commit.get(role) or {}).get("name") is not None and ((commit[role]["name"], commit[role]["email"]) in allowed_git) for commit in commits for role in ("author", "committer"))
    checks.append(_check("commits.identities", identities_ok, "All candidate author and committer identities are allowed.", "A candidate author or committer identity is missing or disallowed."))
    checks.append(_check("contributors.allowlist", set(data.get("contributors") or []) == set(policy["identities"]["allowed_contributors"]), "Public contributor attribution exactly matches its allowlist.", "Public contributor attribution differs from its allowlist."))
    authenticated = bool(getattr(client, "authenticated", False))
    protected = (("collaborators.allowlist", "collaborators", policy["identities"]["allowed_collaborators"]), ("access.invitations", "invitations", []), ("access.teams", "teams", []), ("access.deploy_keys", "deploy_keys", []))
    for identifier, key, expected in protected:
        available = authenticated and key in data and data.get(key) is not None
        if not available:
            checks.append(_check(identifier, False, "", "Authenticated access state could not be inspected.", "unverified"))
        else:
            checks.append(_check(identifier, set(data[key]) == set(expected), f"Authenticated {key} state matches policy.", f"Authenticated {key} state differs from policy."))
    checks.extend([
        _check("public.clone", data.get("clone") is True, "Unauthenticated clone works.", "Unauthenticated clone failed."),
        _check("public.archive", isinstance(data.get("archive"), str), "Unauthenticated release archive works.", "Unauthenticated release archive failed."),
        _check("public.readme", data.get("readme") is True, "Unauthenticated README works.", "Unauthenticated README failed."),
        _check("public.assets", all((data.get("assets") or {}).get(path) is True for path in policy["public_surface"]["assets"]), "Unauthenticated public assets work.", "An unauthenticated public asset failed."),
        _check("release.archive_checksum", bool(re.fullmatch(r"[0-9a-f]{64}", str(data.get("archive") or ""))), "Downloaded archive produced a SHA-256 checksum.", "Downloaded archive checksum is missing or invalid."),
    ])
    checksum_text = (((data.get("releases") or {}).get(release["tag"]) or {}).get("assets") or {}).get(release["checksum_asset"])
    expected_line = f"{data.get('archive')}  {release['checksum_entry']}"
    agreement = isinstance(checksum_text, str) and expected_line in {line.strip() for line in checksum_text.splitlines()}
    checks.append(_check("release.checksum_asset", agreement, "Published checksum agrees with the policy and downloaded archive.", "Published checksum is absent or disagrees."))
    if "error" in data:
        checks.append(_check("client.collection", False, "", str(data["error"])))
    result = "fail" if any(item["status"] == "fail" for item in checks) else ("unverified" if any(item["status"] == "unverified" for item in checks) else "pass")
    report = {"schema_version": 1, "repository": f"{expected_repo['owner']}/{expected_repo['name']}", "release": release["tag"], "result": result, "checks": checks}
    return redact(report)


class GitHubClient:
    """Small mockable read-only GitHub REST/raw/git client."""
    def __init__(self, token: str | None = None, timeout: int = 45):
        self.token = token
        self.authenticated = bool(token)
        self.timeout = timeout

    def _request(self, url: str, *, api: bool = True) -> bytes:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "executive-operator-public-release-audit"}
        if api and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
            return response.read()

    def _json(self, url: str):
        return json.loads(self._request(url).decode("utf-8"))

    def _access_list(self, url: str, field: str = "login"):
        if not self.authenticated:
            return None
        try:
            values = self._json(url)
            return [item.get(field) or item.get("name") or str(item.get("id")) for item in values]
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 404}:
                return None
            raise

    def collect(self, policy: dict[str, Any]) -> dict[str, Any]:
        owner, name = policy["repository"]["owner"], policy["repository"]["name"]
        base = f"https://api.github.com/repos/{owner}/{name}"
        repo = self._json(base)
        branch_rows = self._json(base + "/branches?per_page=100")
        branches = [item["name"] for item in branch_rows]
        branch_heads = {item["name"]: item["commit"]["sha"] for item in branch_rows}
        tag_rows = self._json(base + "/tags?per_page=100")
        tags = {item["name"]: item["commit"]["sha"] for item in tag_rows}
        releases_raw = self._json(base + "/releases?per_page=100")
        releases = {}
        for item in releases_raw:
            assets = {}
            for asset in item.get("assets", []):
                if asset["name"] == policy["release"]["checksum_asset"]:
                    assets[asset["name"]] = self._request(asset["browser_download_url"], api=False).decode("utf-8")
            releases[item["tag_name"]] = {"tag_name": item["tag_name"], "target_commitish": item["target_commitish"], "assets": assets}
        tag = policy["release"]["tag"]
        if policy["release"]["commit_count"]["mode"] == "exact-delta":
            commit_rows = self._json(base + f"/compare/{policy['release']['commit_count']['base']}...{tag}").get("commits", [])
        else:
            commit_rows = self._json(base + f"/commits?sha={tag}&per_page=100")
        commits = [{"sha": item["sha"], "author": item["commit"]["author"], "committer": item["commit"]["committer"]} for item in commit_rows]
        contributors = [item["login"] for item in self._json(base + "/contributors?anon=1&per_page=100") if item.get("login")]
        archive_url = f"https://github.com/{owner}/{name}/archive/refs/tags/{tag}.tar.gz"
        archive_bytes = self._request(archive_url, api=False)
        with tempfile.TemporaryDirectory(prefix="public-release-audit-") as directory:
            clone = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", tag, f"https://github.com/{owner}/{name}.git", directory], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})  # nosec B603 B607
            clone_ok = clone.returncode == 0
            content_digest = git_content_digest(Path(directory), tag, policy["release"]["content_digest"]["excluded_paths"]) if clone_ok else None
        raw = f"https://raw.githubusercontent.com/{owner}/{name}/{tag}/"
        def public_ok(path: str) -> bool:
            try:
                return bool(self._request(raw + path, api=False))
            except (urllib.error.URLError, TimeoutError):
                return False
        return {"repository": repo, "branches": branches, "branch_heads": branch_heads, "tags": tags, "releases": releases, "commits": commits, "contributors": contributors, "collaborators": self._access_list(base + "/collaborators?affiliation=all&per_page=100"), "invitations": self._access_list(base + "/invitations?per_page=100"), "teams": self._access_list(base + "/teams?per_page=100", "slug"), "deploy_keys": self._access_list(base + "/keys?per_page=100", "title"), "clone": clone_ok, "content_digest": content_digest, "archive": hashlib.sha256(archive_bytes).hexdigest(), "readme": public_ok(policy["public_surface"]["readme"]), "assets": {path: public_ok(path) for path in policy["public_surface"]["assets"]}}


def load_policy(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    jsonschema.validate(value, json.loads(POLICY_SCHEMA.read_text(encoding="utf-8")), format_checker=jsonschema.FormatChecker())
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="Environment variable to read; its value is never reported")
    args = parser.parse_args(argv)
    try:
        report = audit(load_policy(args.policy), GitHubClient(os.environ.get(args.token_env)))
    except Exception as exc:
        report = {"schema_version": 1, "repository": "xyluxx/executive-operator-blueprint", "release": "unknown", "result": "fail", "checks": [{"id": "client.collection", "status": "fail", "summary": str(redact(str(exc)))}]}
    jsonschema.validate(report, json.loads(REPORT_SCHEMA.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
