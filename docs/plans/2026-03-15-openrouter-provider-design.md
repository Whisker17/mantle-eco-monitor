# OpenRouter Provider Design

> Design for making OpenRouter the default LLM provider for Mantle monitor AI paths.

**Goal:** Default the application LLM configuration to OpenRouter and make the shared LLM client send OpenRouter-friendly request headers while preserving the existing OpenAI-compatible `chat/completions` contract.

**Status:** Approved in discussion on 2026-03-15.

---

## Context

The current LLM integration is intentionally small:

- [config/settings.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/settings.py) exposes generic `llm_api_base`, `llm_api_key`, `llm_model`, and `llm_timeout_seconds`
- [src/services/llm.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/services/llm.py) sends a single OpenAI-compatible `POST {api_base}/chat/completions`
- higher-level services such as `daily_summary` and `bot_query` treat the LLM client as a provider-neutral transport

Right now the defaults are empty, and the client only sends `Authorization`. The requested operating mode is:

- provider: OpenRouter
- common model: `nvidia/nemotron-3-super-120b-a12b:free`

## Requirements

The approved change should:

1. make OpenRouter the default runtime target
2. default the model to `nvidia/nemotron-3-super-120b-a12b:free`
3. keep the current `chat/completions` request shape
4. add OpenRouter-friendly headers such as `HTTP-Referer` and `X-Title`
5. keep overrides possible through normal settings and environment variables

## Non-Goals

This change does not need to:

- introduce `LLM_PROVIDER`
- add provider-specific branching logic
- change higher-level prompt or orchestration logic
- use OpenRouter-specific request body extensions

## Chosen Approach

Keep the current generic `LLMClient` interface, but make it default toward OpenRouter.

The implementation will:

- set `llm_api_base` default to `https://openrouter.ai/api/v1`
- set `llm_model` default to `nvidia/nemotron-3-super-120b-a12b:free`
- add two lightweight metadata settings:
  - `llm_app_name`
  - `llm_app_url`
- send these settings as:
  - `X-Title`
  - `HTTP-Referer`

This keeps the application simple:

- OpenRouter works out of the box once `LLM_API_KEY` is present
- the higher-level services remain unchanged
- other OpenAI-compatible endpoints can still be used by overriding `LLM_API_BASE`

## Configuration

Recommended defaults:

- `LLM_API_BASE=https://openrouter.ai/api/v1`
- `LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free`
- `LLM_APP_NAME=mantle-eco-monitor`
- `LLM_APP_URL=https://github.com/Whisker17/mantle-eco-monitor`

`LLM_API_KEY` remains required at runtime.

## Client Behavior

The shared LLM client should continue to send:

- `model`
- `messages`

to:

- `POST {api_base}/chat/completions`

It should additionally send:

- `Authorization: Bearer ...`
- `HTTP-Referer: <llm_app_url>`
- `X-Title: <llm_app_name>`

No provider branching is needed. The OpenRouter headers are harmless for most OpenAI-compatible endpoints and useful for the intended default provider.

## Testing Strategy

Add focused tests for:

- default settings values for OpenRouter base URL and model
- default settings values for `llm_app_name` and `llm_app_url`
- override behavior for all four fields
- LLM client request headers:
  - `Authorization`
  - `HTTP-Referer`
  - `X-Title`

No scheduler, API, or integration behavior should need to change beyond consuming the updated defaults.
