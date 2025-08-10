# Exa MCP Server

This repository contains an MCP (Model Context Protocol) server integration for
the [Exa](https://exa.ai) API.  The goal of this server is to expose a set
of **atomic tools** that an LLM can invoke to search the web, retrieve page
contents (single pages, multiple pages or collections of subpages), discover
related pages, answer questions and run deep research tasks.  The
implementation follows the patterns used in the Klavis AI open‑source
project and is written entirely in Python.

## Features

The server exposes several tools, each designed to perform a single function
and return easily consumable JSON results:

- **`exa_web_search`** – Perform a live Exa search.  Returns a list of search
  results containing the title, URL and a short snippet.  You can specify
  how many results to return (`num_results`, default 3) and whether to
  automatically retrieve the full page text for each result (`include_text`).
  When `include_text` is `true`, the tool will call the contents API for
  each result and return the full article text instead of a snippet.
- **`exa_fetch_content`** – Retrieve the complete text of a single web page
  using Exa’s contents API.  Use this after you have a specific URL you’d
  like to read.
- **`exa_find_similar_links`** – Given a URL, discover other pages on the
  internet with similar content using Exa’s *findSimilar* endpoint.  The tool
  accepts a `url` and optional `num_results` (default 3) and `include_text`
  flags.  It returns a list of related links with titles, URLs and scores,
  optionally including the full text of each similar page.
- **`exa_answer_question`** – Ask a natural‑language question and get a direct
  answer, along with citations.  Exa performs a search and uses an LLM to
  synthesise a concise answer or detailed summary.  You can pass
  `include_text` to include the supporting source text in the response.
- **`exa_research_start`** – Kick off an asynchronous research task.  Provide
  natural‑language `instructions` and optionally choose a `model` or specify
  an `output_schema` for structured results.  The tool returns a task
  identifier you can use to poll for completion.
- **`exa_research_poll`** – Poll a previously created research task by its
  `task_id` to check its status and retrieve results.  When complete, the
  returned JSON includes the structured data and citations.

 - **`exa_fetch_contents`** – Retrieve the complete text of multiple web pages in one call.  Pass a list of URLs via the `urls` parameter and, if needed, specify the `livecrawl` mode (`"always"`, `"preferred"` or `"never"`) to control whether Exa fetches fresh content.

 - **`exa_fetch_subpages`** – Crawl beyond a main page to retrieve the content of linked subpages.  Provide a root `url`, the maximum number of subpages to crawl (`subpages`), and optionally a list of `subpage_target` keywords (e.g. `["about", "news"]`) and a `livecrawl` mode.  The response includes both the root page and the selected subpages with their full text.

## Installation

1. **Clone or copy this directory** into the `mcp_servers` folder of the
   [Klavis AI `klavis`](https://github.com/Klavis-AI/klavis) repository.  The
   directory name is arbitrary, but `exa_mcp_server` is suggested.
2. Install Python dependencies.  Inside this folder run:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your environment variables.**  Copy `.env.example` to `.env` and
   replace the placeholder API key with your own Exa API key.  You can also
   customise the port on which the server will listen.

4. **Run the server.**  Use the `server.py` entrypoint via the command line:

   ```bash
   python server.py --port 5001 --log-level INFO
   ```

   By default the server will start on port 5000 if no `--port` option is
   provided.  The server exposes two transport endpoints: Server‑Sent Events
   (SSE) at `/sse` and Streamable HTTP at `/mcp`.

5. **Integrate with your LLM.**  When you start the MCP server, you can
   configure your LLM client (e.g. Claude Desktop, Cursor or the `klavis`
   Python SDK) to point to the running server.  The LLM will discover
   all available Exa tools via the MCP `list_tools` method and invoke
   them automatically when appropriate.

## Environment Variables

The server relies on a couple of environment variables.  You can define
these in a `.env` file or export them in your shell before running the
server.

| Variable            | Description                                                           |
|---------------------|-----------------------------------------------------------------------|
| `EXA_API_KEY`       | **Required.** Your Exa API key.  You can generate one from the Exa
|                     | dashboard.                                                             |
| `EXA_MCP_SERVER_PORT` | Optional.  The port to bind the server to.  Defaults to `5000`.       |

## Security

This integration authenticates requests to Exa using the API key provided via
the `EXA_API_KEY` environment variable.  Take care to keep this key secret
and do not commit it to version control.  The server will raise an error
if the key is missing when a tool is invoked.  All tools are stateless
and only send your requests and API key to Exa’s servers.

## License

This project is released under the MIT License.  By contributing to or
using this code you agree to the terms of the MIT License as specified
in the parent repository.