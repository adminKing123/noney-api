"""
fuse/node_catalog_browse.py
===========================
Paginated / sectioned node catalog for the studio picker (n8n-style).

Returns listing metadata only — full definitions stay on GET /fuse/nodes/<type>.
"""

from __future__ import annotations

import re
from collections import defaultdict

from fuse.node_definitions import ACTION_NODES, STARTER_NODES
from fuse.node_listing import (
    filter_nodes_for_user,
    node_to_listing_metadata,
)

# Picker category order (integrations grouped at the end).
SECTION_ORDER: tuple[str, ...] = (
    "General",
    "Notifications",
    "AI",
    "Logic",
    "Network",
    "Webex",
    "Gmail",
    "Google Sheets",
    "GitHub",
    "Handle Files",
    "Other",
)

# Default icon + blurb for category rows (n8n-style picker root).
SECTION_META: dict[str, dict[str, str]] = {
    "General": {
        "icon": "TbCalendarTime",
        "description": "Schedules, webhooks, and other general triggers and steps.",
    },
    "Notifications": {
        "icon": "TbBell",
        "description": "Push notifications and email alerts.",
    },
    "AI": {
        "icon": "TbSparkles",
        "description": "Generate text or structured data with AI.",
    },
    "Logic": {
        "icon": "TbGitBranch",
        "description": "Branch, merge, loop, and set variables in your flow.",
    },
    "Network": {
        "icon": "TbWorldWww",
        "description": "HTTP requests and external APIs.",
    },
    "Webex": {
        "icon": "SiWebex",
        "description": "Messages and rooms in Webex.",
    },
    "Gmail": {
        "icon": "SiGmail",
        "description": "Send email with your connected Gmail account.",
    },
    "Google Sheets": {
        "icon": "SiGooglesheets",
        "description": "Read and write rows in Google Sheets.",
    },
    "GitHub": {
        "icon": "SiGithub",
        "description": "Repositories, pull requests, and GitHub events.",
    },
    "Handle Files": {
        "icon": "TbFileCode",
        "description": "Create and upload files from workflow data.",
    },
    "Other": {
        "icon": "TbWorldWww",
        "description": "Additional actions and integrations.",
    },
}


def _section_sort_key(section: str) -> tuple[int, str]:
    name = section or "General"
    try:
        return (SECTION_ORDER.index(name), name)
    except ValueError:
        return (len(SECTION_ORDER), name)


def _nodes_for_role(role: str) -> list[dict]:
    if role == "starter":
        return list(STARTER_NODES)
    if role == "action":
        return list(ACTION_NODES)
    raise ValueError(f"Invalid role {role!r}; expected 'starter' or 'action'.")


def _available_listings(role: str, user_integrations: dict) -> list[dict]:
    nodes = filter_nodes_for_user(_nodes_for_role(role), user_integrations)
    return [node_to_listing_metadata(n) for n in nodes]


def list_catalog_sections(role: str, user_integrations: dict) -> list[dict]:
    """Section summaries for the picker root view."""
    listings = _available_listings(role, user_integrations)
    counts: dict[str, int] = defaultdict(int)
    icons: dict[str, str | None] = {}

    for item in listings:
        section = item.get("section") or "General"
        counts[section] += 1
        if section not in icons and item.get("icon"):
            icons[section] = item["icon"]

    sections = sorted(counts.keys(), key=_section_sort_key)
    out: list[dict] = []
    for section in sections:
        meta = SECTION_META.get(section, {})
        out.append(
            {
                "id": section,
                "label": section,
                "count": counts[section],
                "icon": meta.get("icon") or icons.get(section),
                "description": meta.get("description")
                or f"{counts[section]} {'node' if counts[section] == 1 else 'nodes'} available",
            }
        )
    return out


def list_nodes_in_section(
    role: str,
    section: str,
    user_integrations: dict,
    *,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """Listing metadata for one section (lazy-loaded when user opens a category)."""
    section = (section or "General").strip()
    listings = _available_listings(role, user_integrations)
    matched = [
        n for n in listings if (n.get("section") or "General") == section
    ]
    matched.sort(key=lambda n: (n.get("label") or "").lower())
    total = len(matched)
    page = matched[offset : offset + limit]
    return {
        "section": section,
        "role": role,
        "total": total,
        "offset": offset,
        "limit": limit,
        "nodes": page,
    }


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"[\s_\-./]+", query.lower()) if t]


def search_catalog_listings(
    query: str,
    user_integrations: dict,
    *,
    role: str | None = None,
    limit: int = 40,
) -> list[dict]:
    """
    Keyword search over listing metadata for the picker search bar.
    """
    tokens = _tokenize(query)
    query_norm = query.lower().strip().replace(" ", "_")
    scored: list[tuple[float, dict]] = []

    roles = ("starter", "action") if not role else (role,)
    for r in roles:
        for item in _available_listings(r, user_integrations):
            blob = " ".join(
                [
                    item.get("type") or "",
                    item.get("label") or "",
                    item.get("section") or "",
                    item.get("description") or "",
                ]
            ).lower()

            score = 0.0
            node_type = item.get("type") or ""
            if query_norm and query_norm == node_type:
                score += 100
            if query_norm and query_norm in blob.replace(" ", "_"):
                score += 20
            for token in tokens:
                if len(token) < 2:
                    continue
                if token in blob:
                    score += 2
                if token in node_type:
                    score += 5

            if score > 0 or not tokens:
                entry = {**item, "role": r}
                if score > 0:
                    entry["match_score"] = score
                scored.append((score, entry))

    scored.sort(key=lambda x: (-x[0], x[1].get("label") or ""))
    if not tokens:
        return [entry for _, entry in scored[:limit]]
    return [entry for score, entry in scored[:limit] if score > 0]
