import json
import pytest
import respx
import httpx


pytestmark = pytest.mark.asyncio


def _json_response(data, status_code=200):
    return httpx.Response(status_code=status_code, json=data)


@respx.mock
async def test_exa_web_search_basic(monkeypatch):
    import server
    # Mock the Exa search endpoint
    route = respx.post(server.EXA_SEARCH_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {"title": "A", "url": "https://a.com", "text": "alpha"},
                    {"title": "B", "url": "https://b.com", "summary": "bravo"},
                ]
            }
        )
    )
    results = await server.exa_web_search("hello", num_results=2)
    assert route.called
    assert len(results) == 2
    assert results[0]["title"] == "A"
    assert results[0]["snippet"] == "alpha"
    assert results[1]["snippet"] == "bravo"  # falls back to summary


@respx.mock
async def test_exa_fetch_content_single():
    import server
    route = respx.post(server.EXA_CONTENTS_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {"title": "Page", "url": "https://x.com", "text": "CONTENT"}
                ]
            }
        )
    )
    data = await server.exa_fetch_content("https://x.com")
    assert route.called
    assert data["title"] == "Page"
    assert data["text"] == "CONTENT"


@respx.mock
async def test_exa_fetch_contents_bulk():
    import server
    route = respx.post(server.EXA_CONTENTS_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {"title": "P1", "url": "https://1.com", "text": "T1"},
                    {"title": "P2", "url": "https://2.com", "text": "T2"},
                ]
            }
        )
    )
    data = await server.exa_fetch_contents(["https://1.com", "https://2.com"], livecrawl="preferred")
    assert route.called
    sent = route.calls[-1].request
    payload = json.loads(sent.content)
    assert payload["urls"] == ["https://1.com", "https://2.com"]
    assert payload["text"] is True
    assert payload["livecrawl"] == "preferred"
    assert {d["url"] for d in data} == {"https://1.com", "https://2.com"}


@respx.mock
async def test_exa_find_similar_links_without_text():
    import server
    route = respx.post(server.EXA_FIND_SIMILAR_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {"title": "Rel1", "url": "https://r1.com", "score": 0.9, "summary": "S"},
                    {"title": "Rel2", "url": "https://r2.com", "score": 0.8, "text": "FULL"},
                ]
            }
        )
    )
    out = await server.exa_find_similar_links("https://seed.com", include_text=False, num_results=2)
    assert route.called
    assert out[0]["text"] is None  # not included when include_text=False
    assert out[1]["text"] is None


@respx.mock
async def test_exa_find_similar_links_with_text():
    import server
    route = respx.post(server.EXA_FIND_SIMILAR_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {"title": "Rel", "url": "https://r.com", "score": 0.77, "text": "BODY"}
                ]
            }
        )
    )
    out = await server.exa_find_similar_links("https://seed.com", include_text=True, num_results=1)
    assert route.called
    assert out[0]["text"] == "BODY"


@respx.mock
async def test_exa_answer_question_basic():
    import server
    route = respx.post(server.EXA_ANSWER_ENDPOINT).mock(
        return_value=_json_response(
            {
                "answer": "42",
                "citations": [{"title": "Deep Thought"}],
            }
        )
    )
    out = await server.exa_answer_question("What is?", include_text=False)
    assert route.called
    assert out["answer"] == "42"
    assert "citations" in out


@respx.mock
async def test_exa_research_start_with_schema_and_model():
    import server
    route = respx.post(server.EXA_RESEARCH_TASKS_ENDPOINT).mock(
        return_value=_json_response({"id": "task_123"})
    )
    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    out = await server.exa_research_start(
        instructions="Find X",
        model="exa-research-pro",
        output_schema=schema,
    )
    assert route.called
    req_payload = json.loads(route.calls[-1].request.content)
    assert req_payload["instructions"] == "Find X"
    assert req_payload["model"] == "exa-research-pro"
    assert req_payload["output"]["schema"] == schema
    assert out["id"] == "task_123"


@respx.mock
async def test_exa_research_poll():
    import server
    route = respx.get(f"{server.EXA_RESEARCH_TASKS_ENDPOINT}/task_123").mock(
        return_value=_json_response({"id": "task_123", "status": "complete", "data": {"ok": True}})
    )
    out = await server.exa_research_poll("task_123")
    assert route.called
    assert out["status"] == "complete"
    assert out["data"]["ok"] is True


@respx.mock
async def test_exa_fetch_subpages_with_target():
    import server
    route = respx.post(server.EXA_CONTENTS_ENDPOINT).mock(
        return_value=_json_response(
            {
                "results": [
                    {
                        "title": "Root",
                        "url": "https://root.com",
                        "text": "ROOT",
                        "subpages": [
                            {"title": "About", "url": "https://root.com/about", "text": "ABOUT"},
                            {"title": "News", "url": "https://root.com/news", "text": "NEWS"},
                        ],
                    }
                ]
            }
        )
    )
    out = await server.exa_fetch_subpages(
        url="https://root.com", subpages=3, subpage_target=["about", "news"], livecrawl="always"
    )
    assert route.called
    req_payload = json.loads(route.calls[-1].request.content)
    assert req_payload["subpages"] == 3
    assert req_payload["subpage_target"] == ["about", "news"]
    assert req_payload["livecrawl"] == "always"
    assert out["page"]["title"] == "Root"
    assert len(out["subpages"]) == 2
