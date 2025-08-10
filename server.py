"""
Exa MCP Server
===============

This module implements a Model Context Protocol (MCP) server that exposes a
collection of atomic tools for interacting with the Exa API.  These tools
enable web search, retrieval of page contents (both individual pages and
multiple pages at once), crawling of subpages within a site, discovery of
similar links, direct question answering, and agentic research tasks.  The
server adheres to the patterns used in the Klavis AI open‑source project.
To run the server you need an Exa API key which can be provided via the
`EXA_API_KEY` environment variable or a `.env` file.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import click
import httpx
import mcp.types as types
from dotenv import load_dotenv
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

# Load environment variables from .env if present
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Read configuration from environment variables
EXA_MCP_SERVER_PORT = int(os.getenv("EXA_MCP_SERVER_PORT", "5000"))
EXA_API_KEY = os.getenv("EXA_API_KEY", "")

# Exa endpoints
EXA_SEARCH_ENDPOINT = "https://api.exa.ai/search"
EXA_CONTENTS_ENDPOINT = "https://api.exa.ai/contents"

# Additional Exa endpoints for extended functionality
# Endpoint for finding similar links based on an input URL
EXA_FIND_SIMILAR_ENDPOINT = "https://api.exa.ai/findSimilar"
# Endpoint for getting a direct answer to a question
EXA_ANSWER_ENDPOINT = "https://api.exa.ai/answer"
# Endpoint for creating and polling research tasks
EXA_RESEARCH_TASKS_ENDPOINT = "https://api.exa.ai/research/v0/tasks"


async def exa_web_search(query: str, num_results: int = 3) -> list[dict[str, Any]]:
    """Perform a web search using the Exa API.

    Args:
        query: The natural language query to search for.
        num_results: The maximum number of results to return.  Defaults to 3.

    Returns:
        A list of dictionaries each containing ``title``, ``url`` and ``snippet``
        keys.  If the Exa API returns fewer results than requested, the list
        will contain fewer items.

    Raises:
        Exception: If the API key is missing or if the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    payload = {
        "query": query,
        "num_results": num_results,
        "text": False,
    }
    logger.debug(f"Sending search request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(EXA_SEARCH_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    results: list[dict[str, Any]] = []
    for item in data.get("results", [])[: num_results]:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                # Fall back to summary if text isn't present
                "snippet": item.get("text") or item.get("summary") or "",
            }
        )
    logger.debug(f"Search results: {results}")
    return results


async def exa_find_similar_links(
    url: str,
    include_text: bool = False,
    num_results: int = 3,
) -> list[dict[str, Any]]:
    """Find and return links similar in meaning to the provided URL.

    This function calls Exa's ``findSimilar`` endpoint to retrieve links
    that are semantically related to the content at the given URL.

    Args:
        url: The URL to find similar links for.
        include_text: If ``True``, include the extracted page text in the
            returned objects. Defaults to ``False``.
        num_results: The maximum number of similar results to return.

    Returns:
        A list of dictionaries each containing at least ``title``, ``url``,
        and ``score``. If ``include_text`` is set, the ``text`` field will
        contain the extracted content of each similar page.

    Raises:
        Exception: If the API key is missing or the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    payload: dict[str, Any] = {"url": url, "text": include_text}
    logger.debug(f"Sending findSimilar request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(EXA_FIND_SIMILAR_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    results: list[dict[str, Any]] = []
    for item in data.get("results", [])[: num_results]:
        # Only include the full text when requested.  Use summary as a fallback.
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "score": item.get("score"),
                "text": (item.get("text") or item.get("summary") or "") if include_text else None,
            }
        )
    logger.debug(f"findSimilar results: {results}")
    return results


async def exa_answer_question(
    query: str,
    include_text: bool = False,
) -> dict[str, Any]:
    """Get a direct answer to a question using Exa's Answer API.

    Exa will perform a search and use an internal LLM to return either a
    concise answer for simple queries or a detailed summary with citations
    for open‑ended questions.

    Args:
        query: The natural‑language question to answer.
        include_text: If ``True``, include the full text of the supporting
            sources in the response. Defaults to ``False``.

    Returns:
        A dictionary containing at least ``answer`` and ``citations`` fields.

    Raises:
        Exception: If the API key is missing or the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    payload: dict[str, Any] = {"query": query, "text": include_text}
    logger.debug(f"Sending answer request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(EXA_ANSWER_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    logger.debug(f"Answer result: {data}")
    return data


async def exa_research_start(
    instructions: str,
    model: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an asynchronous research task.

    This function submits a research request to Exa's Research API. The
    research agent will decompose the task into steps, search the web,
    synthesize findings and return structured results with citations. A task
    identifier is returned immediately and should be used with
    :func:`exa_research_poll` to poll for completion.

    Args:
        instructions: Natural‑language instructions describing the research
            task to perform.
        model: Optional model name to use (e.g. ``"exa-research"`` or
            ``"exa-research-pro"``). If ``None`` the default model is
            selected by Exa.
        output_schema: Optional JSON Schema defining the desired output
            structure. If provided, it will be sent as ``output.schema`` in
            the payload.

    Returns:
        A dictionary with the key ``id`` corresponding to the newly created
        task's identifier.

    Raises:
        Exception: If the API key is missing or the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
    payload: dict[str, Any] = {"instructions": instructions}
    if model:
        payload["model"] = model
    if output_schema:
        payload["output"] = {"schema": output_schema}
    logger.debug(f"Sending research task creation to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(EXA_RESEARCH_TASKS_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    logger.debug(f"Research task created: {data}")
    return data


async def exa_research_poll(task_id: str) -> dict[str, Any]:
    """Poll the status and results of a previously created research task.

    Args:
        task_id: The identifier returned from :func:`exa_research_start`.

    Returns:
        A dictionary containing the task's status, instructions, schema, data,
        and citations. When the task is complete, the ``data`` field will
        contain the structured result or report.

    Raises:
        Exception: If the API key is missing or the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    # Compose the URL with the task ID
    url = f"{EXA_RESEARCH_TASKS_ENDPOINT}/{task_id}"
    logger.debug(f"Polling research task {task_id}")
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    logger.debug(f"Research task status: {data}")
    return data


async def exa_fetch_content(url: str) -> dict[str, Any]:
    """Retrieve the full text content of a given URL using Exa's contents API.

    Args:
        url: The URL of the page to fetch.

    Returns:
        A dictionary with keys ``title``, ``url`` and ``text`` containing the
        extracted content of the page.

    Raises:
        Exception: If the API key is missing or if the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    payload = {
        "urls": [url],
        "text": True,
    }
    logger.debug(f"Sending contents request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(EXA_CONTENTS_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    results = data.get("results", [])
    if not results:
        raise Exception("No content returned from Exa for the given URL")
    result = results[0]
    content: dict[str, Any] = {
        "title": result.get("title"),
        "url": result.get("url"),
        "text": result.get("text"),
    }
    logger.debug(f"Content result: {content}")
    return content


async def exa_fetch_contents(
    urls: list[str],
    livecrawl: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the full text content for multiple URLs using Exa's contents API.

    This helper function accepts a list of URLs and returns a list of
    dictionaries containing the title, URL and text of each page.  It is
    intended for internal use when enriching search results, but is also
    exposed as an atomic tool via the MCP `exa_fetch_contents` tool.  You
    can optionally request that Exa fetch the live version of each page
    instead of its cached copy by setting ``livecrawl`` to ``"always"``,
    ``"preferred"`` or ``"never"``.

    Args:
        urls: A list of URLs to fetch.  Must be non‑empty.
        livecrawl: Optional string controlling how Exa fetches the content.
            ``"always"`` forces a fresh crawl, ``"preferred"`` attempts a
            fresh crawl but falls back to cache on failure, and ``"never"``
            uses only cached results.  When ``None`` the default behaviour
            is used.

    Returns:
        A list of dictionaries, one per URL, with keys ``title``, ``url``
        and ``text`` representing the extracted page content.  If a page
        cannot be fetched, it will simply be omitted from the result list.

    Raises:
        Exception: If the API key is missing, if ``urls`` is empty, or if the
            HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    if not urls:
        raise Exception("Argument 'urls' must be a non‑empty list of URLs")
    headers = {"x-api-key": EXA_API_KEY}
    payload: dict[str, Any] = {"urls": urls, "text": True}
    if livecrawl:
        payload["livecrawl"] = livecrawl
    logger.debug(f"Sending bulk contents request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            EXA_CONTENTS_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "text": item.get("text"),
            }
        )
    logger.debug(f"Bulk content results: {results}")
    return results


async def exa_fetch_subpages(
    url: str,
    subpages: int = 5,
    subpage_target: list[str] | None = None,
    livecrawl: str | None = None,
) -> dict[str, Any]:
    """Retrieve the content of a page and its subpages using Exa's subpage crawling feature.

    Exa can automatically discover and crawl linked pages within a website.  This
    helper function wraps the `contents` endpoint with the ``subpages`` and
    ``subpage_target`` parameters to fetch a specified number of subpages from
    the given URL.  It returns both the primary page content and a list of
    subpage contents.

    Args:
        url: The root URL to crawl for subpages.
        subpages: Maximum number of subpages to crawl.  Defaults to 5.
        subpage_target: Optional list of keywords used to prioritise which
            subpages are retrieved (e.g. ["about", "products"]).  If ``None``
            all subpages are treated equally.
        livecrawl: Optional livecrawl mode controlling whether to fetch fresh
            content.  Accepts the same values as :func:`exa_fetch_contents`.

    Returns:
        A dictionary with two keys:
            ``page`` – a dictionary containing the title, URL and text of the
                root page; and
            ``subpages`` – a list of dictionaries for each discovered subpage
                containing title, URL and text.

    Raises:
        Exception: If the API key is missing or the HTTP request fails.
    """
    if not EXA_API_KEY:
        raise Exception("EXA_API_KEY environment variable is not set")
    headers = {"x-api-key": EXA_API_KEY}
    payload: dict[str, Any] = {
        "urls": [url],
        "text": True,
        "subpages": subpages,
    }
    if subpage_target:
        payload["subpage_target"] = subpage_target
    if livecrawl:
        payload["livecrawl"] = livecrawl
    logger.debug(f"Sending subpage crawl request to Exa: {payload}")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            EXA_CONTENTS_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    results = data.get("results", [])
    if not results:
        raise Exception("No content returned from Exa for the given URL")
    result = results[0]
    page = {
        "title": result.get("title"),
        "url": result.get("url"),
        "text": result.get("text"),
    }
    subpages_results = []
    for sub in result.get("subpages", []):
        subpages_results.append(
            {
                "title": sub.get("title"),
                "url": sub.get("url"),
                "text": sub.get("text"),
            }
        )
    logger.debug(f"Subpages results: {subpages_results}")
    return {"page": page, "subpages": subpages_results}

# New helper to build the MCP server without starting the ASGI app.
# This allows tests to import and exercise the tool definitions and dispatcher
# without invoking uvicorn.  The returned ``Server`` instance has the same
# ``list_tools`` and ``call_tool`` methods as defined in :func:`main`.
def build_mcp_server(json_response: bool = False) -> Server:
    """
    Construct and return an MCP Server instance with all Exa tools registered.

    This function encapsulates the tool definitions and dispatch logic so they
    can be reused outside of the CLI entrypoint.  It mirrors the behaviour of
    the server created in ``main`` without setting up any transports or
    starting the ASGI application.  Tests can call this function to obtain
    a fresh server and verify the behaviour of ``list_tools`` and ``call_tool``.

    Args:
        json_response: Unused placeholder to match the signature of the CLI.

    Returns:
        A fully configured ``Server`` instance with tools registered.
    """
    app = Server("exa-mcp-server")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            # Search tool
            types.Tool(
                name="exa_web_search",
                description=(
                    "Perform a real-time web search via Exa and return a list of "
                    "results with title, url, and snippet fields. Optionally "
                    "include full text in each result."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "minimum": 1,
                            "default": 3,
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include full page text in each search result",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # Content retrieval tool
            types.Tool(
                name="exa_fetch_content",
                description=(
                    "Retrieve and read the full text content of a given URL using "
                    "Exa's content retrieval API. Use after obtaining a URL from "
                    "exa_web_search or other means."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL of the page to fetch.",
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Bulk content retrieval tool
            types.Tool(
                name="exa_fetch_contents",
                description=(
                    "Retrieve the full text contents of multiple URLs in one call via Exa's "
                    "contents API. Provide a list of URLs and optionally specify the "
                    "livecrawl mode to control whether Exa should fetch fresh pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of URLs to fetch. Must contain at least one URL.",
                        },
                        "livecrawl": {
                            "type": "string",
                            "description": "Optional livecrawl mode: 'always', 'preferred', or 'never'.",
                            "enum": ["always", "preferred", "never"],
                        },
                    },
                    "required": ["urls"],
                },
            ),
            # Subpage crawling tool
            types.Tool(
                name="exa_fetch_subpages",
                description=(
                    "Crawl a website and retrieve the contents of the root page and a number of "
                    "its subpages. Use this when you need to explore beyond the main page, "
                    "such as fetching 'about' or 'products' pages on a company site."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The root URL from which to crawl subpages.",
                        },
                        "subpages": {
                            "type": "integer",
                            "description": "Maximum number of subpages to crawl.",
                            "minimum": 1,
                            "default": 5,
                        },
                        "subpage_target": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional keywords used to prioritise which subpages to fetch.",
                        },
                        "livecrawl": {
                            "type": "string",
                            "description": "Optional livecrawl mode: 'always', 'preferred', or 'never'.",
                            "enum": ["always", "preferred", "never"],
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Find similar links tool
            types.Tool(
                name="exa_find_similar_links",
                description=(
                    "Given a URL, return a list of links with similar meaning "
                    "using Exa's findSimilar API. Useful for discovering related "
                    "articles or pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to find similar links for.",
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include the text of each similar page in the response.",
                            "default": False,
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Maximum number of similar results to return",
                            "minimum": 1,
                            "default": 3,
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Answer question tool
            types.Tool(
                name="exa_answer_question",
                description=(
                    "Ask a natural-language question and get a direct answer using "
                    "Exa's Answer API. Returns both the answer and supporting "
                    "citations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The question to answer.",
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include full text of supporting sources in the response.",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # Research start tool
            types.Tool(
                name="exa_research_start",
                description=(
                    "Start an asynchronous research task that uses Exa's "
                    "agentic pipeline to search, reason, and synthesize an answer. "
                    "Returns a task ID which you can poll to retrieve results."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "instructions": {
                            "type": "string",
                            "description": "Natural-language instructions describing the research task.",
                        },
                        "model": {
                            "type": "string",
                            "description": "Optional model to use for research (e.g. 'exa-research' or 'exa-research-pro').",
                        },
                        "output_schema": {
                            "type": "object",
                            "description": "Optional JSON Schema specifying the desired structured output.",
                        },
                    },
                    "required": ["instructions"],
                },
            ),
            # Research poll tool
            types.Tool(
                name="exa_research_poll",
                description=(
                    "Poll a previously created research task to check its status and "
                    "retrieve results once complete."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The ID of the research task returned by exa_research_start.",
                        }
                    },
                    "required": ["task_id"],
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        """
        Dispatch calls to the appropriate Exa helper function based on tool name.

        This function mirrors the behaviour defined in ``main`` but without
        duplicating branches.  It validates inputs, invokes the corresponding
        asynchronous helper and returns a list of ``TextContent`` results.  If
        ``include_text`` is requested for web search, it enriches the search
        results by calling the contents API in bulk and falling back to
        per-page requests on failure.
        """
        try:
            if name == "exa_web_search":
                query: str | None = arguments.get("query")
                if not query:
                    raise ValueError("Argument 'query' is required")
                num_results: int = arguments.get("num_results", 3)
                include_text: bool = arguments.get("include_text", False)
                results = await exa_web_search(query=query, num_results=num_results)
                if include_text:
                    urls = [item.get("url") for item in results if item.get("url")]
                    try:
                        contents = await exa_fetch_contents(urls=urls)
                        url_to_content = {item.get("url"): item for item in contents}
                        enriched_results: list[dict[str, Any]] = []
                        for item in results:
                            page_url = item.get("url")
                            enriched_results.append(url_to_content.get(page_url, item))
                        results = enriched_results
                    except Exception:
                        enriched_results = []
                        for item in results:
                            try:
                                content = await exa_fetch_content(url=item.get("url"))
                                enriched_results.append(content)
                            except Exception:
                                enriched_results.append(item)
                        results = enriched_results
                return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
            elif name == "exa_fetch_content":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                result = await exa_fetch_content(url=url)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            elif name == "exa_find_similar_links":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                include_text: bool = arguments.get("include_text", False)
                num_results: int = arguments.get("num_results", 3)
                results = await exa_find_similar_links(url=url, include_text=include_text, num_results=num_results)
                return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
            elif name == "exa_fetch_contents":
                urls: list | None = arguments.get("urls")
                if not urls or not isinstance(urls, list):
                    raise ValueError("Argument 'urls' must be a non-empty list")
                livecrawl: str | None = arguments.get("livecrawl")
                results = await exa_fetch_contents(urls=urls, livecrawl=livecrawl)
                return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
            elif name == "exa_fetch_subpages":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                subpages: int = arguments.get("subpages", 5)
                subpage_target = arguments.get("subpage_target")
                if subpage_target and not isinstance(subpage_target, list):
                    raise ValueError("Argument 'subpage_target' must be an array of strings if provided")
                livecrawl: str | None = arguments.get("livecrawl")
                result = await exa_fetch_subpages(url=url, subpages=subpages, subpage_target=subpage_target, livecrawl=livecrawl)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            elif name == "exa_answer_question":
                query: str | None = arguments.get("query")
                if not query:
                    raise ValueError("Argument 'query' is required")
                include_text: bool = arguments.get("include_text", False)
                result = await exa_answer_question(query=query, include_text=include_text)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            elif name == "exa_research_start":
                instructions: str | None = arguments.get("instructions")
                if not instructions:
                    raise ValueError("Argument 'instructions' is required")
                model: str | None = arguments.get("model")
                output_schema: dict | None = arguments.get("output_schema")
                result = await exa_research_start(instructions=instructions, model=model, output_schema=output_schema)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            elif name == "exa_research_poll":
                task_id: str | None = arguments.get("task_id")
                if not task_id:
                    raise ValueError("Argument 'task_id' is required")
                result = await exa_research_poll(task_id=task_id)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            else:
                return [types.TextContent(type="text", text=f"Error: Unknown tool '{name}'")]
        except Exception as e:
            logger.exception(f"Error executing tool {name}: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    return app


@click.command()
@click.option(
    "--port", default=EXA_MCP_SERVER_PORT, help="Port to listen on for HTTP"
)
@click.option(
    "--log-level",
    default="INFO",
    help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
@click.option(
    "--json-response",
    is_flag=True,
    default=False,
    help="Enable JSON responses for StreamableHTTP instead of SSE streams",
)
def main(port: int, log_level: str, json_response: bool) -> int:
    """Entry point for running the Exa MCP server.

    Configures logging, sets up the MCP server with multiple tools, and runs
    the underlying ASGI application using `uvicorn`.  The server exposes
    both Server‑Sent Events and Streamable HTTP transports on separate
    routes.  See the README for a list of available tools.
    """
    # Configure logging for the application
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create a throwaway legacy server instance for backward-compatibility.
    # Tools and dispatcher will be registered on this instance but it will not be used
    # for transport registration.  A new server is built via build_mcp_server below.
    legacy_app = Server("exa-mcp-server")
    # Build the actual MCP server with all tools/dispatcher registered
    app = build_mcp_server(json_response=json_response)

    # Define the list of tools the server provides
    @legacy_app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            # Search tool
            types.Tool(
                name="exa_web_search",
                description=(
                    "Perform a real‑time web search via Exa and return a list of "
                    "results with title, url, and snippet fields. Optionally "
                    "include full text in each result."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "minimum": 1,
                            "default": 3,
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include full page text in each search result",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # Content retrieval tool
            types.Tool(
                name="exa_fetch_content",
                description=(
                    "Retrieve and read the full text content of a given URL using "
                    "Exa's content retrieval API. Use after obtaining a URL from "
                    "exa_web_search or other means."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL of the page to fetch.",
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Bulk content retrieval tool
            types.Tool(
                name="exa_fetch_contents",
                description=(
                    "Retrieve the full text contents of multiple URLs in one call via Exa's "
                    "contents API. Provide a list of URLs and optionally specify the "
                    "livecrawl mode to control whether Exa should fetch fresh pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of URLs to fetch. Must contain at least one URL.",
                        },
                        "livecrawl": {
                            "type": "string",
                            "description": "Optional livecrawl mode: 'always', 'preferred', or 'never'.",
                            "enum": ["always", "preferred", "never"],
                        },
                    },
                    "required": ["urls"],
                },
            ),
            # Subpage crawling tool
            types.Tool(
                name="exa_fetch_subpages",
                description=(
                    "Crawl a website and retrieve the contents of the root page and a number of "
                    "its subpages. Use this when you need to explore beyond the main page, "
                    "such as fetching 'about' or 'products' pages on a company site."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The root URL from which to crawl subpages.",
                        },
                        "subpages": {
                            "type": "integer",
                            "description": "Maximum number of subpages to crawl.",
                            "minimum": 1,
                            "default": 5,
                        },
                        "subpage_target": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional keywords used to prioritise which subpages to fetch.",
                        },
                        "livecrawl": {
                            "type": "string",
                            "description": "Optional livecrawl mode: 'always', 'preferred', or 'never'.",
                            "enum": ["always", "preferred", "never"],
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Find similar links tool
            types.Tool(
                name="exa_find_similar_links",
                description=(
                    "Given a URL, return a list of links with similar meaning "
                    "using Exa's findSimilar API. Useful for discovering related "
                    "articles or pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to find similar links for.",
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include the text of each similar page in the response.",
                            "default": False,
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Maximum number of similar results to return",
                            "minimum": 1,
                            "default": 3,
                        },
                    },
                    "required": ["url"],
                },
            ),
            # Answer question tool
            types.Tool(
                name="exa_answer_question",
                description=(
                    "Ask a natural‑language question and get a direct answer using "
                    "Exa's Answer API. Returns both the answer and supporting "
                    "citations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The question to answer.",
                        },
                        "include_text": {
                            "type": "boolean",
                            "description": "Whether to include full text of supporting sources in the response.",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # Research start tool
            types.Tool(
                name="exa_research_start",
                description=(
                    "Start an asynchronous research task that uses Exa's "
                    "agentic pipeline to search, reason, and synthesize an answer. "
                    "Returns a task ID which you can poll to retrieve results."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "instructions": {
                            "type": "string",
                            "description": "Natural‑language instructions describing the research task.",
                        },
                        "model": {
                            "type": "string",
                            "description": "Optional model to use for research (e.g. 'exa-research' or 'exa-research-pro').",
                        },
                        "output_schema": {
                            "type": "object",
                            "description": "Optional JSON Schema specifying the desired structured output.",
                        },
                    },
                    "required": ["instructions"],
                },
            ),
            # Research poll tool
            types.Tool(
                name="exa_research_poll",
                description=(
                    "Poll a previously created research task to check its status and "
                    "retrieve results once complete."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The ID of the research task returned by exa_research_start.",
                        }
                    },
                    "required": ["task_id"],
                },
            ),
        ]

    # Define how to call each tool
    @legacy_app.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent]:
        try:
            if name == "exa_web_search":
                # Extract required and optional parameters
                query: str | None = arguments.get("query")
                if not query:
                    raise ValueError("Argument 'query' is required")
                num_results: int = arguments.get("num_results", 3)
                include_text: bool = arguments.get("include_text", False)
                results = await exa_web_search(query=query, num_results=num_results)
                # When include_text is requested, call contents API for each result
                if include_text:
                    # Collect the URLs from the search results to fetch content in bulk
                    urls = [item.get("url") for item in results if item.get("url")]
                    try:
                        # Use the bulk contents API to enrich results in one request
                        contents = await exa_fetch_contents(urls=urls)
                        # Map fetched contents back to their original positions using order of URLs
                        url_to_content = {item.get("url"): item for item in contents}
                        enriched_results: list[dict[str, Any]] = []
                        for item in results:
                            page_url = item.get("url")
                            enriched_results.append(url_to_content.get(page_url, item))
                        results = enriched_results
                    except Exception:
                        # If the bulk fetch fails, fall back to per‑URL retrieval
                        enriched_results: list[dict[str, Any]] = []
                        for item in results:
                            try:
                                content = await exa_fetch_content(url=item.get("url"))
                                enriched_results.append(content)
                            except Exception:
                                enriched_results.append(item)
                        results = enriched_results
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(results, indent=2),
                    )
                ]
            elif name == "exa_fetch_content":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                result = await exa_fetch_content(url=url)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            elif name == "exa_find_similar_links":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                include_text: bool = arguments.get("include_text", False)
                num_results: int = arguments.get("num_results", 3)
                results = await exa_find_similar_links(
                    url=url, include_text=include_text, num_results=num_results
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(results, indent=2),
                    )
                ]
            elif name == "exa_fetch_contents":
                urls: list | None = arguments.get("urls")
                if not urls or not isinstance(urls, list):
                    raise ValueError("Argument 'urls' must be a non‑empty list")
                livecrawl: str | None = arguments.get("livecrawl")
                results = await exa_fetch_contents(urls=urls, livecrawl=livecrawl)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(results, indent=2),
                    )
                ]
            elif name == "exa_fetch_subpages":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                subpages: int = arguments.get("subpages", 5)
                subpage_target = arguments.get("subpage_target")
                # Ensure subpage_target is a list if provided
                if subpage_target and not isinstance(subpage_target, list):
                    raise ValueError("Argument 'subpage_target' must be an array of strings if provided")
                livecrawl: str | None = arguments.get("livecrawl")
                result = await exa_fetch_subpages(
                    url=url,
                    subpages=subpages,
                    subpage_target=subpage_target,
                    livecrawl=livecrawl,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            elif name == "exa_fetch_contents":
                urls: list | None = arguments.get("urls")
                if not urls or not isinstance(urls, list):
                    raise ValueError("Argument 'urls' must be a non‑empty list")
                livecrawl: str | None = arguments.get("livecrawl")
                results = await exa_fetch_contents(urls=urls, livecrawl=livecrawl)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(results, indent=2),
                    )
                ]
            elif name == "exa_fetch_subpages":
                url: str | None = arguments.get("url")
                if not url:
                    raise ValueError("Argument 'url' is required")
                subpages: int = arguments.get("subpages", 5)
                subpage_target = arguments.get("subpage_target")
                # Ensure subpage_target is a list if provided
                if subpage_target and not isinstance(subpage_target, list):
                    raise ValueError("Argument 'subpage_target' must be an array of strings if provided")
                livecrawl: str | None = arguments.get("livecrawl")
                result = await exa_fetch_subpages(
                    url=url,
                    subpages=subpages,
                    subpage_target=subpage_target,
                    livecrawl=livecrawl,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            elif name == "exa_answer_question":
                query: str | None = arguments.get("query")
                if not query:
                    raise ValueError("Argument 'query' is required")
                include_text: bool = arguments.get("include_text", False)
                result = await exa_answer_question(query=query, include_text=include_text)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            elif name == "exa_research_start":
                instructions: str | None = arguments.get("instructions")
                if not instructions:
                    raise ValueError("Argument 'instructions' is required")
                model: str | None = arguments.get("model")
                output_schema: dict | None = arguments.get("output_schema")
                result = await exa_research_start(
                    instructions=instructions,
                    model=model,
                    output_schema=output_schema,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            elif name == "exa_research_poll":
                task_id: str | None = arguments.get("task_id")
                if not task_id:
                    raise ValueError("Argument 'task_id' is required")
                result = await exa_research_poll(task_id=task_id)
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Unknown tool '{name}'",
                    )
                ]
        except Exception as e:
            logger.exception(f"Error executing tool {name}: {e}")
            return [
                types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}",
                )
            ]

    # Configure transports for SSE and Streamable HTTP
    sse = SseServerTransport(server=app)
    streamable_http_session_manager = StreamableHTTPSessionManager(
        server=app, json_response=json_response
    )

    async def handle_sse(scope: Scope, receive: Receive, send: Send) -> None:
        await sse.handle_request(scope, receive, send)

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await streamable_http_session_manager.handle_request(scope, receive, send)

    async def health(request):  # type: ignore[override]
        return Response("OK")

    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        logger.info("Application startup...")
        yield
        logger.info("Application shutting down...")

    # Assemble the ASGI application
    starlette_app = Starlette(
        debug=True,
        routes=[
            # SSE endpoint
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            # SSE posting endpoint
            Mount("/messages/", app=sse.handle_post_message),
            # Streamable HTTP endpoint for MCP
            Mount("/mcp", app=handle_streamable_http),
            # Simple health check
            Route("/health", endpoint=health, methods=["GET"]),
        ],
        lifespan=lifespan,
    )

    logger.info(f"Server starting on port {port} with dual transports:")
    logger.info(f"  - SSE endpoint: http://localhost:{port}/sse")
    logger.info(f"  - StreamableHTTP endpoint: http://localhost:{port}/mcp")

    # Run the ASGI application using uvicorn
    import uvicorn  # Imported here to avoid dependency at import time when running tests

    uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    return 0


if __name__ == "__main__":
    main()