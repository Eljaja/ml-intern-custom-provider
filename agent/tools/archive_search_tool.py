"""
Internet Archive — search archive.org catalog and fetch item metadata.

Docs: https://archive.org/services/docs/api/index.html
"""

from typing import Any

import httpx

from agent.tools.types import ToolResult

IA_ADVANCED = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata"
DEFAULT_LIMIT = 15
MAX_LIMIT = 50
IA_TIMEOUT = 25.0

# Fields returned for search hits (Archive.org Lucene index)
_DEFAULT_FL = [
    "identifier",
    "title",
    "mediatype",
    "description",
    "publicdate",
    "year",
    "creator",
]

ARCHIVE_SEARCH_TOOL_SPEC: dict[str, Any] = {
    "name": "archive_search",
    "description": (
        "Search the Internet Archive (archive.org) catalog: books, audio, video, software, "
        "historical web collections, and more. Use Lucene query syntax, e.g. a plain keyword, "
        "'mediatype:texts', 'collection:opensource', or combined AND/OR queries. "
        "Use operation 'metadata' with an identifier from search results to load full item details "
        "and file lists."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search", "metadata"],
                "description": (
                    "search: query the public catalog. metadata: get one item by identifier."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Required for search. Query string (keywords or fielded), e.g. "
                    "'neural network', 'mediatype:audio AND collection:etree'."
                ),
            },
            "identifier": {
                "type": "string",
                "description": "Required for metadata. Item id, e.g. 'iacollection_academic' or a book id.",
            },
            "limit": {
                "type": "integer",
                "description": f"For search: max results ({DEFAULT_LIMIT} default, {MAX_LIMIT} max).",
            },
        },
        "required": ["operation"],
    },
}


async def _op_search(args: dict[str, Any], limit: int) -> ToolResult:
    q = (args.get("query") or "").strip()
    if not q:
        return {
            "formatted": "For operation=search, non-empty 'query' is required.",
            "isError": True,
        }

    limit = min(max(1, limit), MAX_LIMIT)
    params: list[tuple[str, str]] = [
        ("q", q),
        ("rows", str(limit)),
        ("output", "json"),
    ]
    for f in _DEFAULT_FL:
        params.append(("fl[]", f))

    async with httpx.AsyncClient(timeout=IA_TIMEOUT) as client:
        r = await client.get(IA_ADVANCED, params=params)
        r.raise_for_status()
        data = r.json()

    resp = data.get("response", {})
    num = resp.get("numFound", 0)
    docs = resp.get("docs", []) or []
    if not docs:
        return {
            "formatted": f"Internet Archive: no results for query={q!r} (numFound={num}).",
            "isError": False,
        }

    lines = [f"Internet Archive search — {len(docs)} of {num} hit(s) for: {q}\n"]
    for i, d in enumerate(docs, 1):
        ident = d.get("identifier", "?")
        title = (d.get("title") or "(no title)")[:200]
        mt = d.get("mediatype", "")
        year = d.get("year", "")
        creator = d.get("creator", "")
        if isinstance(creator, list):
            creator = ", ".join(str(c) for c in creator[:3])
        when = d.get("publicdate", "")
        desc = d.get("description", "") or ""
        if isinstance(desc, list):
            desc = " ".join(str(x) for x in desc[:1])
        desc = str(desc)[:180].replace("\n", " ")
        base = f"https://archive.org/details/{ident}"
        lines.append(
            f"{i}. **{title}**\n"
            f"   - identifier: `{ident}`\n"
            f"   - mediatype: {mt}  year: {year}  date: {when}\n"
            f"   - creator: {creator}\n"
            f"   - {desc}\n"
            f"   - {base}\n"
        )

    return {"formatted": "\n".join(lines), "isError": False}


async def _op_metadata(args: dict[str, Any], _limit: int) -> ToolResult:
    ident = (args.get("identifier") or "").strip()
    if not ident:
        return {
            "formatted": "For operation=metadata, non-empty 'identifier' is required.",
            "isError": True,
        }

    url = f"{IA_METADATA}/{ident}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=IA_TIMEOUT) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    if data.get("error"):
        return {
            "formatted": f"Archive.org metadata error: {data.get('error')}",
            "isError": True,
        }

    title = (data.get("metadata") or {}).get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    desc = (data.get("metadata") or {}).get("description")
    if isinstance(desc, list):
        desc = " ".join(str(x) for x in desc[:2])[:2000]
    else:
        desc = str(desc or "")[:2000]

    files = data.get("files") or []
    file_rows = [f for f in files if isinstance(f, dict) and f.get("name")]
    names_preview = [f["name"] for f in file_rows[:25]]

    ddir = data.get("dir")
    if not isinstance(ddir, str):
        ddir = f"https://archive.org/download/{ident}/"

    out = [
        f"**Internet Archive item** `{ident}`",
        f"**Title:** {title or '(unknown)'}",
        f"**Page:** https://archive.org/details/{ident}",
        f"**Dir:** {ddir}",
        "",
        f"**Description (excerpt):** {desc or '(none)'}",
        "",
        f"**Files (sample, {min(len(names_preview), 20)} shown):**",
    ]
    out.extend(f"  - {n}" for n in names_preview[:20])
    if len(file_rows) > 20:
        out.append(f"  ... and {len(file_rows) - 20} more files")

    return {"formatted": "\n".join(out), "isError": False}


_OPERATIONS: dict[str, Any] = {
    "search": _op_search,
    "metadata": _op_metadata,
}


async def archive_search_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Handler for the agent tool router."""
    operation = (arguments.get("operation") or "").strip()
    if not operation:
        return "'operation' is required (search or metadata).", False

    handler = _OPERATIONS.get(operation)
    if not handler:
        return f"Unknown operation: {operation!r}. Use: search, metadata.", False

    try:
        limit = int(arguments.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = min(max(1, limit), MAX_LIMIT)

    try:
        result = await handler(arguments, limit)
        return result["formatted"], not result.get("isError", False)
    except httpx.HTTPStatusError as e:
        return (
            f"archive.org HTTP {e.response.status_code}: {e.response.text[:300]}",
            False,
        )
    except httpx.RequestError as e:
        return f"archive.org request error: {e}", False
    except Exception as e:
        return f"archive_search error: {e}", False
