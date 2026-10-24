#!/usr/bin/env python3
"""Check if a GitHub GraphQL endpoint accepts a JSON array of operations.

Usage: probe_array_batching.py <domain> [--cafile PATH]
Token: $<FIRST DOMAIN LABEL>_TOKEN, e.g. $BBGITHUB_TOKEN for bbgithub.example.com.
Proxy and CA file default to git's http.proxy and http.sslcainfo for the endpoint.
Sends only read-only queries.
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

OPERATIONS = [
    {"query": "query A { viewer { login } }"},
    {"query": "query B { rateLimit { cost remaining used resetAt } }"},
]
RATE_HEADERS = ["x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-used"]


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
) -> None:
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
            status, headers, payload = (
                response.status,
                response.headers,
                response.read(),
            )
    except urllib.error.HTTPError as e:
        status, headers, payload = e.code, e.headers, e.read()
    print(f"  status: {status}")
    for name in RATE_HEADERS:
        print(f"  {name}: {headers.get(name)}")
    try:
        print(
            "  body:", json.dumps(json.loads(payload), indent=2).replace("\n", "\n  ")
        )
    except ValueError:
        print("  body (not JSON):", payload[:500])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
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
    print(f"Proxy: {proxy}")
    print(f"CA file: {cafile}")
    context = ssl.create_default_context(cafile=cafile)
    # Python 3.13 rejects CA certs whose Basic Constraints are not marked critical
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy} if proxy else {}),
        urllib.request.HTTPSHandler(context=context),
    )

    print(f"Array of {len(OPERATIONS)} operations -> {url}")
    post(opener, url, token, OPERATIONS)
    for operation in OPERATIONS:
        print(f"Single operation -> {url}")
        post(opener, url, token, operation)


if __name__ == "__main__":
    main()
