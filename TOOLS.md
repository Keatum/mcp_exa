# Exa MCP Server Tools

This document describes each tool exposed by the Exa MCP server.  It is intended
for both AI clients (so they know which prompt words to use) and human
developers (to understand the parameters and expected behaviour of each tool).

## exa_web_search

**AI Prompt Words:** search the web, web search, find articles, get search results.

**Title:** Perform a real‑time web search

**Parameter usage:**

| Parameter    | Type    | Required | Default | Description                                                                 |
|--------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `query`      | string  | yes      | –       | Natural‑language query to search for.                                       |
| `num_results`| integer | no       | 3       | Maximum number of results to return.                                         |
| `include_text` | boolean | no    | false   | Whether to include the full text of each result instead of a snippet.       |

**Example prompt:**

> “Search the web for recent news about renewable energy and include the full text of the top 2 results.”

## exa_fetch_content

**AI Prompt Words:** read page, fetch content, get page text, extract article.

**Title:** Retrieve the full text of a single page

**Parameter usage:**

| Parameter | Type   | Required | Description                                           |
|-----------|--------|----------|-------------------------------------------------------|
| `url`     | string | yes      | The URL of the page to fetch.                         |

**Example prompt:**

> “Fetch the article text from https://example.com/interesting-post and show it to me.”

## exa_fetch_contents

**AI Prompt Words:** fetch multiple pages, bulk fetch, retrieve contents.

**Title:** Retrieve the contents of multiple pages in one call

**Parameter usage:**

| Parameter   | Type          | Required | Default | Description                                                                      |
|-------------|---------------|----------|---------|----------------------------------------------------------------------------------|
| `urls`      | array of strings | yes   | –       | A non‑empty list of URLs to fetch.                                               |
| `livecrawl` | string        | no       | –       | One of `"always"`, `"preferred"`, or `"never"` to control whether Exa crawls fresh pages. |

**Example prompt:**

> “Retrieve the contents of these pages: https://a.com and https://b.com.”

## exa_fetch_subpages

**AI Prompt Words:** crawl subpages, get subpages, explore site, fetch related pages.

**Title:** Crawl a page and its subpages

**Parameter usage:**

| Parameter       | Type              | Required | Default | Description                                                                                        |
|-----------------|-------------------|----------|---------|----------------------------------------------------------------------------------------------------|
| `url`           | string            | yes      | –       | The root URL from which to crawl subpages.                                                         |
| `subpages`      | integer           | no       | 5       | Maximum number of subpages to return.                                                              |
| `subpage_target`| array of strings  | no       | –       | Keywords used to prioritise which subpages to fetch (e.g. `["about", "news"]`).                   |
| `livecrawl`     | string            | no       | –       | One of `"always"`, `"preferred"`, or `"never"` to control whether Exa crawls fresh pages.          |

**Example prompt:**

> “Crawl https://example.com and fetch up to 3 subpages prioritising pages containing ‘about’ or ‘contact’.”

## exa_find_similar_links

**AI Prompt Words:** find similar pages, related links, similar articles.

**Title:** Discover links similar to a given page

**Parameter usage:**

| Parameter     | Type    | Required | Default | Description                                                                 |
|---------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `url`         | string  | yes      | –       | The URL to find similar links for.                                         |
| `include_text`| boolean | no       | false   | Whether to include the text of each similar page in the response.          |
| `num_results` | integer | no       | 3       | Maximum number of similar links to return.                                 |

**Example prompt:**

> “Find 5 pages similar to https://example.com/ai-announcement and include their full text.”

## exa_answer_question

**AI Prompt Words:** answer question, direct answer, summarise information, ask Exa.

**Title:** Ask a question and get a direct answer

**Parameter usage:**

| Parameter      | Type    | Required | Default | Description                                                          |
|----------------|---------|----------|---------|----------------------------------------------------------------------|
| `query`        | string  | yes      | –       | The natural‑language question to answer.                              |
| `include_text` | boolean | no       | false   | Whether to include the supporting source text in the response.        |

**Example prompt:**

> “What is the capital of France? Include the full text of your sources.”

## exa_research_start

**AI Prompt Words:** start research, deep research, initiate research task, research request.

**Title:** Start an asynchronous research task

**Parameter usage:**

| Parameter       | Type    | Required | Default | Description                                                                                         |
|-----------------|---------|----------|---------|-----------------------------------------------------------------------------------------------------|
| `instructions`  | string  | yes      | –       | Natural‑language instructions describing the research task.                                         |
| `model`         | string  | no       | –       | Which research model to use, e.g. `"exa-research"` or `"exa-research-pro"`.                         |
| `output_schema` | object  | no       | –       | A JSON Schema describing the structured output you expect.                                           |

**Example prompt:**

> “Research the impacts of climate change on coastal cities and return a structured summary.”

## exa_research_poll

**AI Prompt Words:** poll research, check research status, get research results.

**Title:** Poll for research task results

**Parameter usage:**

| Parameter | Type   | Required | Description                                                |
|-----------|--------|----------|------------------------------------------------------------|
| `task_id` | string | yes      | The ID of the research task returned by `exa_research_start`. |

**Example prompt:**

> “Check the status of my research task with ID task_123 and return any available results.”