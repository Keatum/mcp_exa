import os
import sys
import types
import pytest


@pytest.fixture(autouse=True)
def set_exa_api_key(monkeypatch):
    """Ensure a dummy EXA_API_KEY is defined for all tests by default."""
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    yield


@pytest.fixture(autouse=True)
def patch_mcp(monkeypatch):
    """Provide minimal dummy modules under the `mcp` namespace so that the
    server can be imported without the real `mcp` package installed.

    The server imports several submodules from `mcp.server` and uses
    `mcp.types.TextContent` and `mcp.types.Tool` for type annotations.  This
    fixture installs dummy modules into `sys.modules` that satisfy these
    imports and provide basic placeholder classes.  The dummy modules are
    cleaned up automatically between tests by monkeypatch.
    """
    # Create a top-level mcp module
    mcp = types.ModuleType("mcp")
    # Create submodules
    server_mod = types.ModuleType("mcp.server")
    lowlevel_mod = types.ModuleType("mcp.server.lowlevel")
    sse_mod = types.ModuleType("mcp.server.sse")
    stream_mod = types.ModuleType("mcp.server.streamable_http_manager")
    types_mod = types.ModuleType("mcp.types")

    # Define dummy classes used by server
    class DummyTool:
        def __init__(self, *args, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class DummyTextContent:
        def __init__(self, type: str, text: str):
            self.type = type
            self.text = text

    # Assign attributes
    types_mod.Tool = DummyTool
    types_mod.TextContent = DummyTextContent

    # For lowlevel.Server we just use a simple object placeholder.  Tests that
    # need more complex behaviour will monkeypatch it to a FakeServer.
    class DummyServer:
        def __init__(self, *args, **kwargs):
            pass

        def list_tools(self):
            def decorator(func):
                return func
            return decorator

        def call_tool(self):
            def decorator(func):
                return func
            return decorator

    lowlevel_mod.Server = DummyServer
    sse_mod.SseServerTransport = object
    stream_mod.StreamableHTTPSessionManager = object

    # Attach submodules to mcp namespace
    server_mod.lowlevel = lowlevel_mod
    server_mod.sse = sse_mod
    server_mod.streamable_http_manager = stream_mod

    # Make `mcp.server.lowlevel` available via attribute access
    mcp.server = server_mod
    mcp.server.lowlevel = lowlevel_mod
    mcp.server.sse = sse_mod
    mcp.server.streamable_http_manager = stream_mod
    mcp.types = types_mod

    # Register modules in sys.modules
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.server", server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.lowlevel", lowlevel_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.sse", sse_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.streamable_http_manager", stream_mod)
    monkeypatch.setitem(sys.modules, "mcp.types", types_mod)

    yield
