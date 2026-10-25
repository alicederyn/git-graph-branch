#!/usr/bin/env python3
"""Print the reviewThreads cursors of a PR, decoded, next to the thread data.

Usage: probe_review_thread_cursors.py <domain> <owner> <repo> <pr> [--first N] [--cafile PATH]
Token: $<FIRST DOMAIN LABEL>_TOKEN, e.g. $BBGITHUB_TOKEN for bbgithub.example.com.
Proxy and CA file default to git's http.proxy and http.sslcainfo for the endpoint.
Sends only read-only queries.
"""

import argparse
import base64
import binascii
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

QUERY = """
query ($owner: String!, $name: String!, $number: Int!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: $first) {
        totalCount
        pageInfo { startCursor endCursor hasNextPage }
        edges {
          cursor
          node {
            id
            isResolved
            comments(first: 1) { nodes { databaseId createdAt } }
          }
        }
      }
    }
  }
}
"""


def endpoint(domain: str) -> str:
    if domain.count(".") == 1:
        return f"https://api.{domain}/graphql"
    return f"https://{domain}/api/graphql"


def git_http_config(url: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "config", "--get-urlmatch", "http", url],
        capture_output=True,
        text=True,
    )
    config = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        config[key.lower()] = value
    return config


def post(
    opener: urllib.request.OpenerDirector, url: str, token: str, body: object
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener.open(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read()[:500]!r}")
    result: dict[str, object] = json.loads(payload)
    if "errors" in result:
        sys.exit(json.dumps(result["errors"], indent=2))
    return result


def decode(value: str) -> bytes | str:
    # Newer node IDs are "<TYPE>_<base64url>", e.g. PRRT_kwDO...
    encoded = re.sub(r"^[A-Z]+_", "", value)
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except binascii.Error:
        pass
    try:
        return base64.urlsafe_b64decode(padded)
    except binascii.Error:
        return "<not base64>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("pr", type=int)
    parser.add_argument("--first", type=int, default=5)
    parser.add_argument("--cafile")
    args = parser.parse_args()

    variable = args.domain.split(".", maxsplit=1)[0].upper() + "_TOKEN"
    token = os.environ.get(variable)
    if not token:
        sys.exit(f"${variable} is not set")
    url = endpoint(args.domain)
    http_config = git_http_config(f"https://{args.domain}")
    cafile = args.cafile or http_config.get("http.sslcainfo")
    proxy = http_config.get("http.proxy") or urllib.request.getproxies().get("https")
    context = ssl.create_default_context(cafile=cafile)
    # Python 3.13 rejects CA certs whose Basic Constraints are not marked critical
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy} if proxy else {}),
        urllib.request.HTTPSHandler(context=context),
    )

    variables = {
        "owner": args.owner,
        "name": args.repo,
        "number": args.pr,
        "first": args.first,
    }
    result = post(opener, url, token, {"query": QUERY, "variables": variables})
    threads = result["data"]["repository"]["pullRequest"]["reviewThreads"]  # type: ignore[index]
    print(f"totalCount: {threads['totalCount']}")
    print(f"pageInfo: {threads['pageInfo']}")
    for edge in threads["edges"]:
        node = edge["node"]
        comment = node["comments"]["nodes"][0]
        print(f"cursor: {edge['cursor']}")
        print(f"  decoded: {decode(edge['cursor'])!r}")
        print(f"  thread id: {node['id']} (decoded: {decode(node['id'])!r})")
        print(f"  resolved: {node['isResolved']}")
        print(f"  first comment: {comment['databaseId']} at {comment['createdAt']}")


if __name__ == "__main__":
    main()
