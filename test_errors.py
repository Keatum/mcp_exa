import pytest
import respx
import httpx


pytestmark = pytest.mark.asyncio


def _json_response(data, status_code=200):
    return httpx.Response(status_code=status_code, json=data)


@respx.mock
async def test_missing_api_key_raises(monkeypatch):
    # Import server after patching environment and mcp modules
    import server
    # Temporarily clear the API key on the module
    monkeypatch.setattr(server, "EXA_API_KEY", "")
    with pytest.raises(Exception) as e:
        await server.exa_web_search("q")
    assert "EXA_API_KEY" in str(e.value)


@respx.mock
async def test_exa_fetch_contents_requires_non_empty_urls(monkeypatch):
    import server
    with pytest.raises(Exception):
        await server.exa_fetch_contents([], livecrawl=None)


@respx.mock
async def test_exa_fetch_content_no_results_raises():
    import server
    # Simulate Exa returning no results for a bad URL
    respx.post(server.EXA_CONTENTS_ENDPOINT).mock(
        return_value=httpx.Response(status_code=200, json={"results": []})
    )
    with pytest.raises(Exception) as e:
        await server.exa_fetch_content("https://missing.com")
    assert "No content returned" in str(e.value)


@respx.mock
async def test_exa_fetch_subpages_no_results_raises():
    import server
    respx.post(server.EXA_CONTENTS_ENDPOINT).mock(
        return_value=httpx.Response(status_code=200, json={"results": []})
    )
    with pytest.raises(Exception):
        await server.exa_fetch_subpages("https://root.com")


@respx.mock
async def test_http_error_bubbles_up():
    import server
    # Simulate non-2xx status
    respx.post(server.EXA_SEARCH_ENDPOINT).mock(
        return_value=httpx.Response(status_code=401)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await server.exa_web_search("q")