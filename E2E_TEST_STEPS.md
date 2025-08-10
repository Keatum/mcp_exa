# End‑to‑End Test Steps for Exa MCP Server

This document outlines the steps required to demonstrate that each tool provided
by the Exa MCP server functions correctly when invoked through an MCP client.
Follow these instructions to capture a short video or a series of screenshots
that can be attached to your pull request as evidence.

## Prerequisites

1. **Run the server:** Start your Exa MCP server locally:

   ```bash
   python server.py --port 5000
   ```

2. **Set your API key:** Make sure the `EXA_API_KEY` environment variable is
   defined and contains a valid Exa API key. You can copy `.env.example` to
   `.env` and edit it accordingly.

3. **Choose a client:** Use an MCP client such as Claude Desktop, Cursor, or
   the `streamable_http_client.py` script in the Klavis repository. Configure
   the client to point at `http://localhost:5000/mcp` (for the Streamable HTTP
   transport) or `http://localhost:5000/sse` (for SSE).

## Steps

### 1. List available tools

* In your MCP client, ask the model to list its available tools, e.g. “What
  tools are available from this server?” or use the client’s UI to fetch the
  tool manifest.
* Verify that all tools (`exa_web_search`, `exa_fetch_content`, `exa_fetch_contents`,
  `exa_fetch_subpages`, `exa_find_similar_links`, `exa_answer_question`,
  `exa_research_start`, `exa_research_poll`) are listed with clear descriptions.

### 2. Perform a web search

* Prompt: “Search the web for ‘latest advancements in quantum computing’ and
  include the full text of the top result.”
* Observe the server logs or debug output to ensure that `exa_web_search` is
  called with `query="latest advancements in quantum computing"`,
  `num_results=1`, and `include_text=true`.
* Confirm that the response includes the full article text.

### 3. Retrieve single page content

* Prompt: “Fetch the contents of https://example.com.”
* Verify that `exa_fetch_content` is invoked with the correct URL and that
  the full page text is returned.

### 4. Bulk fetch multiple contents

* Prompt: “Get the contents of these pages: https://a.com, https://b.com, and
  https://c.com.”
* Ensure that `exa_fetch_contents` receives a list of URLs and returns the
  text for each page.

### 5. Crawl subpages

* Prompt: “Crawl https://example.com and fetch up to 2 subpages focusing on
  ‘about’ and ‘news’ pages.”
* Check that `exa_fetch_subpages` is called with `subpages=2` and
  `subpage_target=["about", "news"]`. Verify that both the root page and the
  subpages are returned.

### 6. Find similar links

* Prompt: “Find similar pages to https://example.com/interesting-article and
  include the full text.”
* Confirm that `exa_find_similar_links` is invoked with `include_text=true`
  and returns a list of related pages with their content.

### 7. Answer a question

* Prompt: “What are the benefits of machine learning in healthcare? Include the
  full text of your sources.”
* Observe that `exa_answer_question` is used and that the response contains
  both an answer and citations.

### 8. Start a research task

* Prompt: “Initiate a research task to summarise the history of space exploration
  with a structured output.”
* Verify that `exa_research_start` is called with the appropriate
  instructions and that a task ID is returned.

### 9. Poll a research task

* Prompt: “Check the status of my research task with ID task_123.”
* Ensure that `exa_research_poll` is called with the given `task_id` and
  returns the task’s status and results when they are ready.

## Documentation to Capture

For each of the steps above, capture the following evidence:

* The natural language prompt you used in the client.
* Logs or debug output showing the server receiving the tool invocation with
  the expected parameters.
* The final result displayed in the client UI.

These recordings or screenshots provide clear proof of correct behaviour and
should accompany your pull request.