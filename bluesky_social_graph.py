#!/usr/bin/env python3
"""
Bluesky Social Graph Explorer

Fetch and analyze the social graph (followers, follows, mutuals)
for any Bluesky / AT Protocol account.

Usage:
    # Public access (no auth needed for basic queries)
    python bluesky_social_graph.py --actor alice.bsky.social

    # Authenticated access (needed for blocks, mutes, known followers)
    python bluesky_social_graph.py --actor alice.bsky.social --handle your.bsky.social --password your-app-password

    # Export to JSON
    python bluesky_social_graph.py --actor alice.bsky.social --export json --output graph.json

    # Export to CSV
    python bluesky_social_graph.py --actor alice.bsky.social --export csv --output graph.csv
"""

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBLIC_API = "https://public.api.bsky.app/xrpc"
AUTH_API = "https://bsky.social/xrpc"
PAGE_LIMIT = 100
REQUEST_DELAY = 0.4  # seconds between paginated requests


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Profile:
    did: str
    handle: str
    display_name: str = ""
    description: str = ""
    followers_count: int = 0
    follows_count: int = 0
    posts_count: int = 0


@dataclass
class GraphEntry:
    did: str
    handle: str
    display_name: str = ""
    description: str = ""
    indexed_at: str = ""


@dataclass
class SocialGraph:
    actor: str
    profile: Optional[Profile] = None
    followers: list[GraphEntry] = field(default_factory=list)
    follows: list[GraphEntry] = field(default_factory=list)
    mutuals: list[GraphEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class BlueskyClient:
    """Lightweight client for the Bluesky / AT Protocol API."""

    def __init__(self, handle: str = None, password: str = None):
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.did: Optional[str] = None
        self.authenticated = False

        if handle and password:
            self._login(handle, password)

    def _login(self, handle: str, password: str) -> None:
        """Authenticate and obtain a session token."""
        resp = self.session.post(
            f"{AUTH_API}/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["accessJwt"]
        self.did = data["did"]
        self.authenticated = True
        self.session.headers.update(
            {"Authorization": f"Bearer {self.access_token}"}
        )
        print(f"Authenticated as {data['handle']} ({self.did})")

    @property
    def base_url(self) -> str:
        return AUTH_API if self.authenticated else PUBLIC_API

    # -- Profile -------------------------------------------------------------

    def get_profile(self, actor: str) -> Profile:
        """Fetch profile metadata for an actor."""
        resp = self.session.get(
            f"{PUBLIC_API}/app.bsky.actor.getProfile",
            params={"actor": actor},
        )
        resp.raise_for_status()
        d = resp.json()
        return Profile(
            did=d["did"],
            handle=d["handle"],
            display_name=d.get("displayName", ""),
            description=d.get("description", ""),
            followers_count=d.get("followersCount", 0),
            follows_count=d.get("followsCount", 0),
            posts_count=d.get("postsCount", 0),
        )

    # -- Paginated helpers ---------------------------------------------------

    def _paginate(self, endpoint: str, actor: str, key: str) -> list[GraphEntry]:
        """Generic paginator for graph list endpoints."""
        entries: list[GraphEntry] = []
        cursor: Optional[str] = None
        page = 0

        while True:
            params: dict = {"actor": actor, "limit": PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor

            resp = self.session.get(
                f"{self.base_url}/{endpoint}", params=params
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get(key, []):
                entries.append(
                    GraphEntry(
                        did=item["did"],
                        handle=item["handle"],
                        display_name=item.get("displayName", ""),
                        description=item.get("description", ""),
                        indexed_at=item.get("indexedAt", ""),
                    )
                )

            cursor = data.get("cursor")
            page += 1
            if not cursor:
                break

            time.sleep(REQUEST_DELAY)

        return entries

    # -- Social graph --------------------------------------------------------

    def get_followers(self, actor: str) -> list[GraphEntry]:
        """Get all followers of an actor."""
        print(f"Fetching followers for {actor}...")
        followers = self._paginate(
            "app.bsky.graph.getFollowers", actor, "followers"
        )
        print(f"  Found {len(followers)} followers")
        return followers

    def get_follows(self, actor: str) -> list[GraphEntry]:
        """Get all accounts an actor follows."""
        print(f"Fetching follows for {actor}...")
        follows = self._paginate(
            "app.bsky.graph.getFollows", actor, "follows"
        )
        print(f"  Found {len(follows)} follows")
        return follows

    def get_social_graph(self, actor: str) -> SocialGraph:
        """Build the full social graph for an actor."""
        graph = SocialGraph(actor=actor)

        # Profile
        graph.profile = self.get_profile(actor)
        print(
            f"\nProfile: {graph.profile.display_name} (@{graph.profile.handle})"
        )
        print(
            f"  Followers: {graph.profile.followers_count} | "
            f"Following: {graph.profile.follows_count} | "
            f"Posts: {graph.profile.posts_count}"
        )
        print()

        # Followers & follows
        graph.followers = self.get_followers(actor)
        graph.follows = self.get_follows(actor)

        # Compute mutuals
        follower_dids = {f.did for f in graph.followers}
        graph.mutuals = [f for f in graph.follows if f.did in follower_dids]
        print(f"  Mutuals: {len(graph.mutuals)}")

        return graph


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def export_json(graph: SocialGraph, path: str) -> None:
    """Export the social graph to a JSON file."""
    data = {
        "actor": graph.actor,
        "profile": asdict(graph.profile) if graph.profile else None,
        "followers": [asdict(e) for e in graph.followers],
        "follows": [asdict(e) for e in graph.follows],
        "mutuals": [asdict(e) for e in graph.mutuals],
        "stats": {
            "followers_count": len(graph.followers),
            "follows_count": len(graph.follows),
            "mutuals_count": len(graph.mutuals),
        },
    }
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nExported JSON to {path}")


def export_csv(graph: SocialGraph, path: str) -> None:
    """Export the social graph to a CSV file."""
    fieldnames = ["relationship", "did", "handle", "display_name", "description", "indexed_at"]
    mutual_dids = {m.did for m in graph.mutuals}

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for entry in graph.followers:
            rel = "mutual" if entry.did in mutual_dids else "follower"
            writer.writerow(
                {
                    "relationship": rel,
                    "did": entry.did,
                    "handle": entry.handle,
                    "display_name": entry.display_name,
                    "description": entry.description,
                    "indexed_at": entry.indexed_at,
                }
            )

        follow_dids = {f.did for f in graph.followers}
        for entry in graph.follows:
            if entry.did not in follow_dids:
                writer.writerow(
                    {
                        "relationship": "following",
                        "did": entry.did,
                        "handle": entry.handle,
                        "display_name": entry.display_name,
                        "description": entry.description,
                        "indexed_at": entry.indexed_at,
                    }
                )

    print(f"\nExported CSV to {path}")


def print_summary(graph: SocialGraph) -> None:
    """Print a human-readable summary of the social graph."""
    print("\n" + "=" * 60)
    print("SOCIAL GRAPH SUMMARY")
    print("=" * 60)

    if graph.profile:
        print(f"Account:    {graph.profile.display_name} (@{graph.profile.handle})")
        print(f"DID:        {graph.profile.did}")
        print(f"Bio:        {graph.profile.description[:100]}..." if len(graph.profile.description) > 100 else f"Bio:        {graph.profile.description}")
    print(f"Followers:  {len(graph.followers)}")
    print(f"Following:  {len(graph.follows)}")
    print(f"Mutuals:    {len(graph.mutuals)}")

    if graph.mutuals:
        print(f"\n--- Top 20 Mutuals ---")
        for entry in graph.mutuals[:20]:
            name = entry.display_name or entry.handle
            print(f"  @{entry.handle:30s}  {name}")

    # Fans: follow you but you don't follow back
    follows_dids = {f.did for f in graph.follows}
    fans = [f for f in graph.followers if f.did not in follows_dids]
    if fans:
        print(f"\n--- Top 10 Fans (follow you, you don't follow back) ---")
        for entry in fans[:10]:
            name = entry.display_name or entry.handle
            print(f"  @{entry.handle:30s}  {name}")

    # Following but not followed back
    follower_dids = {f.did for f in graph.followers}
    not_followed_back = [f for f in graph.follows if f.did not in follower_dids]
    if not_followed_back:
        print(f"\n--- Top 10 Not Following Back ---")
        for entry in not_followed_back[:10]:
            name = entry.display_name or entry.handle
            print(f"  @{entry.handle:30s}  {name}")

    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Bluesky Social Graph Explorer - Fetch and analyze the social graph of any Bluesky account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Public (no auth needed)
  python bluesky_social_graph.py --actor alice.bsky.social

  # Authenticated
  python bluesky_social_graph.py --actor alice.bsky.social --handle you.bsky.social --password your-app-password

  # Export to JSON
  python bluesky_social_graph.py --actor alice.bsky.social --export json --output graph.json

  # Export to CSV
  python bluesky_social_graph.py --actor alice.bsky.social --export csv --output followers.csv
        """,
    )

    parser.add_argument(
        "--actor",
        required=True,
        help="Bluesky handle or DID to analyze (e.g. alice.bsky.social)",
    )
    parser.add_argument(
        "--handle",
        help="Your Bluesky handle for authenticated access",
    )
    parser.add_argument(
        "--password",
        help="Your Bluesky app password (create one in Settings > App Passwords)",
    )
    parser.add_argument(
        "--export",
        choices=["json", "csv"],
        help="Export format",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: <actor>_graph.json/csv)",
    )

    args = parser.parse_args()

    # Build client
    client = BlueskyClient(handle=args.handle, password=args.password)

    # Fetch social graph
    try:
        graph = client.get_social_graph(args.actor)
    except requests.HTTPError as e:
        print(f"\nAPI error: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)

    # Print summary
    print_summary(graph)

    # Export if requested
    if args.export:
        safe_actor = args.actor.replace(".", "_")
        output_path = args.output or f"{safe_actor}_graph.{args.export}"

        if args.export == "json":
            export_json(graph, output_path)
        elif args.export == "csv":
            export_csv(graph, output_path)


if __name__ == "__main__":
    main()
