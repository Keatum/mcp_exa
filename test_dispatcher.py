import json
import pytest


pytestmark = pytest.mark.asyncio


class FakeServer:
    """A minimal stand‑in for `mcp.server.lowlevel.Server` used in dispatcher tests.

    It records the functions decorated via `list_tools()` and `call_tool()` so
    they can be invoked directly in the test.  The last created instance is
    stored on the class for easy access.
    """

    last_instance = None

    def __init__(self, *args, **kwargs):
        type(self).last_instance = self
        self.registered_list_tools = None
        self.registered_call_tool = None

    def list_tools(self):
        def decorator(func):
            self.registered_list_tools = func
            return func
        return decorator

    def call_tool(self):
        def decorator(func):
            self.registered_call_tool = func
            return func
        return decorator


class Dummy:
    """A no‑op placeholder for SseServerTransport and StreamableHTTPSessionManager."""

    def __init__(self, *args, **kwargs):
        pass


class DummyStarlette:
    """A minimal stand‑in for starlette.applications.Starlette used in tests.

    The dispatcher tests do not exercise the ASGI app, so this class simply
    captures constructor arguments and returns an object with a dummy `routes`
    attribute.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.routes = kwargs.get("routes", [])


def patch_dispatcher(monkeypatch):
    """Patch the server module to replace MCP constructs with test doubles.

    Returns a function that takes the imported server module as input and
    applies all necessary monkeypatches.  This indirection allows each test
    to import the server after the monkeypatch fixture has prepared the
    environment.
    """

    def _apply(server):
        # Replace Server with FakeServer
        monkeypatch.setattr(server, "Server", FakeServer)
        # Replace transports with dummy objects
        monkeypatch.setattr(server, "SseServerTransport", Dummy)
        monkeypatch.setattr(server, "StreamableHTTPSessionManager", Dummy)
        # Replace Starlette and routing classes
        monkeypatch.setattr(server, "Starlette", DummyStarlette)
        monkeypatch.setattr(server, "Route", lambda *args, **kwargs: None)
        monkeypatch.setattr(server, "Mount", lambda *args, **kwargs: None)
        # Provide a dummy TextContent for return values
        class DummyTextContent:
            def __init__(self, type: str, text: str):
                self.type = type
                self.text = text
        monkeypatch.setattr(server.types, "TextContent", DummyTextContent)
        return server

    return _apply


@pytest.mark.asyncio
async def test_call_tool_web_search_with_enrichment_success(monkeypatch):
    import server
    apply = patch_dispatcher(monkeypatch)
    srv = apply(server)
    # Patch helper functions to control behaviour
    async def fake_web_search(query, num_results):
        return [{"title": "T", "url": "https://a.com", "snippet": "snip"}]

    async def fake_fetch_contents(urls, livecrawl=None):
        return [{"title": "T", "url": "https://a.com", "text": "FULL"}]

    monkeypatch.setattr(srv, "exa_web_search", fake_web_search)
    monkeypatch.setattr(srv, "exa_fetch_contents", fake_fetch_contents)
    # Build the app (creates FakeServer.last_instance)
    srv.build_mcp_server()
    call_tool_func = FakeServer.last_instance.registered_call_tool
    result = await call_tool_func("exa_web_search", {"query": "q", "num_results": 1, "include_text": True})
    # Result is a list with a single DummyTextContent. Parse JSON in text.
    data = json.loads(result[0].text)
    assert data[0]["text"] == "FULL"


@pytest.mark.asyncio
async def test_call_tool_web_search_with_enrichment_fallback(monkeypatch):
    import server
    apply = patch_dispatcher(monkeypatch)
    srv = apply(server)
    # Patch helper functions
    async def fake_web_search(query, num_results):
        return [
            {"title": "A", "url": "https://a.com", "snippet": "sa"},
            {"title": "B", "url": "https://b.com", "snippet": "sb"},
        ]

    async def fake_fetch_contents(urls, livecrawl=None):
        # Simulate failure by raising an exception
        raise Exception("bulk failure")

    async def fake_fetch_content(url):
        return {"title": "Page", "url": url, "text": f"CONTENT {url}"}

    monkeypatch.setattr(srv, "exa_web_search", fake_web_search)
    monkeypatch.setattr(srv, "exa_fetch_contents", fake_fetch_contents)
    monkeypatch.setattr(srv, "exa_fetch_content", fake_fetch_content)
    srv.build_mcp_server()
    call_tool_func = FakeServer.last_instance.registered_call_tool
    result = await call_tool_func("exa_web_search", {"query": "q", "num_results": 2, "include_text": True})
    data = json.loads(result[0].text)
    # The fallback should call exa_fetch_content for each url
    assert data[0]["text"] == "CONTENT https://a.com"
    assert data[1]["text"] == "CONTENT https://b.com"


@pytest.mark.asyncio
async def test_call_tool_subpages_invalid_target(monkeypatch):
    import server
    apply = patch_dispatcher(monkeypatch)
    srv = apply(server)
    # Build the server to register call_tool
    srv.build_mcp_server()
    call_tool_func = FakeServer.last_instance.registered_call_tool
    # Provide a non-list subpage_target
    result = await call_tool_func(
        "exa_fetch_subpages",
        {"url": "https://example.com", "subpage_target": "not-a-list"},
    )
    # Expect a ValueError reflected in the error message
    assert "subpage_target" in result[0].text


@pytest.mark.asyncio
async def test_call_tool_unknown_tool(monkeypatch):
    import server
    apply = patch_dispatcher(monkeypatch)
    srv = apply(server)
    srv.build_mcp_server()
    call_tool_func = FakeServer.last_instance.registered_call_tool
    result = await call_tool_func("nonexistent_tool", {})
    assert "Unknown tool" in result[0].text