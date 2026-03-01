# Chatbot Implementation

## Overview

This project now includes a LangChain-based, agentic chatbot layer on top of the existing hybrid retrieval stack.

The chatbot uses:

- the existing local hybrid retriever (`Chroma` + `BM25`) for course search
- `OpenAI GPT-4.1-mini` for answer generation
- LangChain tools so the agent can choose between:
  - `CAB` retrieval for detailed operational data like meeting times and instructors
  - `bulletin` retrieval for catalog-style descriptions
- Server-Sent Events (SSE) for streaming responses to the frontend

The implementation is stateless. Each request is handled independently and no server-side conversation memory is stored.

## Main Components

### API layer

The FastAPI entrypoint is in [app.py](/Users/shawn.n/github_repos/impiricus-take-home/app.py).

It exposes:

- `POST /query`
  - streaming chatbot endpoint
  - accepts:
  ```json
  {
    "q": "question text/query",
    "department": "optional"
  }
  ```
- `POST /evaluate`
  - synchronous diagnostics endpoint
  - accepts the same request body
  - returns latency and retrieval metadata

The app loads `.env` automatically if `python-dotenv` is installed, and expects `OPENAI_API_KEY` to be present.

### Retrieval adapter

The adapter is implemented in [chatbot_agent/retrieval_adapter.py](/Users/shawn.n/github_repos/impiricus-take-home/chatbot_agent/retrieval_adapter.py).

Its role is to:

- convert the chatbot request shape (`q`, `department`) into the existing retrieval request shape
- run a deterministic retrieval pass before generation starts
- flatten retrieval hits into frontend-friendly course summaries:
  - `course_code`
  - `title`
  - `department`
  - `similarity`
  - `source`

The default retrieval depth is `8`.

### Agent and tools

The agent runner is implemented in [chatbot_agent/agent.py](/Users/shawn.n/github_repos/impiricus-take-home/chatbot_agent/agent.py), and the tool definitions are in [chatbot_agent/tools.py](/Users/shawn.n/github_repos/impiricus-take-home/chatbot_agent/tools.py).

The agent:

- uses `gpt-4.1-mini`
- is instructed to use retrieval tools before answering factual course questions
- prefers `CAB` for schedule/instructor details
- prefers `bulletin` for general catalog summaries
- avoids inventing details if retrieval is insufficient

The tool layer exposes two retrieval tools to LangChain:

- `search_cab_courses`
- `search_bulletin_courses`

### Chatbot orchestration

The request orchestration lives in [chatbot_agent/service.py](/Users/shawn.n/github_repos/impiricus-take-home/chatbot_agent/service.py).

This service is responsible for:

- running pre-agent retrieval
- formatting SSE events
- streaming token chunks as they arrive
- assembling the final response text
- measuring latency
- logging query metadata and response times

## Response Structure for Frontend

### `POST /query` response

`POST /query` returns an SSE stream with `Content-Type: text/event-stream`.

The server emits events in this order:

1. `retrieval`
2. zero or more `token`
3. `done`

If generation fails after the stream has started, the server emits:

- `error`

instead of `done`.

### Event 1: `retrieval`

This event is sent first, before answer generation starts.

Payload shape:

```json
{
  "query": "csci foundations",
  "retrieved_courses": [
    {
      "course_code": "CSCI 0111",
      "title": "Computing Foundations",
      "department": "CSCI",
      "similarity": 0.91,
      "source": "CAB"
    }
  ],
  "retrieval_count": 1
}
```

Frontend use:

- render the initial search results immediately
- show course cards, metadata, or source badges before the model finishes answering
- use `retrieval_count` for quick UI stats

### Event 2: `token`

This event streams the generated answer incrementally.

Payload shape:

```json
{
  "delta": "next text chunk"
}
```

Frontend use:

- append `delta` to the current assistant message buffer
- re-render the visible answer as chunks arrive

### Event 3: `done`

This event marks successful completion.

Payload shape:

```json
{
  "response_text": "full assembled answer",
  "latency_ms": 412,
  "retrieval_count": 8
}
```

Frontend use:

- replace or confirm the accumulated token buffer with `response_text`
- mark the message as complete
- optionally display latency or analytics

### Error event: `error`

If something fails after streaming has started, the server sends:

```json
{
  "message": "human-readable error"
}
```

Frontend use:

- stop the loading state
- show a retry UI
- preserve any already-rendered retrieval results

## Important Frontend Integration Note

Because this endpoint is a `POST` request, it should be consumed with `fetch()` streaming, not browser `EventSource`.

`EventSource` only supports `GET`, while this API expects a JSON body.

A typical frontend flow is:

1. `fetch("/query", { method: "POST", body: JSON.stringify(...) })`
2. read the response stream from `response.body`
3. parse SSE frames by splitting on blank lines
4. handle each event by its `event:` name and JSON `data:` payload

## `POST /evaluate` response

`POST /evaluate` is non-streaming and returns JSON:

```json
{
  "query": "csci foundations",
  "department": "CSCI",
  "latency_ms": 412,
  "retrieval_count": 8,
  "retrieved_courses": [
    {
      "course_code": "CSCI 0111",
      "title": "Computing Foundations",
      "department": "CSCI",
      "similarity": 0.91,
      "source": "CAB"
    }
  ],
  "model": "gpt-4.1-mini"
}
```

This endpoint is useful for:

- measuring backend latency
- inspecting retrieval output without parsing a stream
- debugging search quality during frontend development

## Logging

Each request logs:

- endpoint
- success/failure
- latency in milliseconds
- retrieval count
- department
- query text
- error message when present

No authentication is required in the current implementation.
