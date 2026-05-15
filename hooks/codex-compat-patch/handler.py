"""Hermes user hook: strip Codex-incompatible fields from Responses API payload.

Codex backend (chatgpt.com/backend-api/codex/responses) tightened validation
around 2026-05-15:

1. `extra_headers` field in body → HTTP 400 "Unsupported parameter: extra_headers"
   Hermes adds session_id / x-client-request-id under this key for correlation,
   but Codex (unlike the regular OpenAI Responses API) now rejects it.

2. Function tools with malformed JSON schema → HTTP 400 "Invalid schema for
   function ..." Two gbrain MCP tools currently ship array properties without
   the required `items` schema:
     - mcp_gbrain_extract_facts: properties.entity_hints
     - mcp_gbrain_log_ingest:    properties.pages_updated
   Codex strict-mode rejects the whole request when ANY tool fails validation.

Both upstream patches (gbrain MCP fix; Hermes Codex compat) will eventually
land. Until then, this hook surgically strips both at preflight so primary
gpt-5.5 stops falling through to fallback on every chat message.

Wrapped in defensive try/except — startup never crashes on this hook.
"""
from __future__ import annotations
import logging

log = logging.getLogger("hermes.codex-compat-patch")

BAD_TOOL_NAMES = frozenset({"mcp_gbrain_extract_facts", "mcp_gbrain_log_ingest"})


async def handle(event_type: str, context: dict) -> None:
    try:
        if event_type != "gateway:startup":
            return

        try:
            from agent.transports.codex import ResponsesApiTransport
        except Exception as e:
            log.warning("[codex-compat-patch] cannot import ResponsesApiTransport; skip. err=%s", e)
            return

        if getattr(ResponsesApiTransport, "_codex_compat_patch_applied", False):
            return

        if not hasattr(ResponsesApiTransport, "preflight_kwargs"):
            log.warning("[codex-compat-patch] preflight_kwargs missing; skip")
            return

        _orig = ResponsesApiTransport.preflight_kwargs

        def _patched(self, api_kwargs, *, allow_stream=False):
            try:
                if isinstance(api_kwargs, dict):
                    api_kwargs = dict(api_kwargs)
                    api_kwargs.pop("extra_headers", None)
                    tools = api_kwargs.get("tools")
                    if isinstance(tools, list):
                        kept = []
                        dropped = []
                        for t in tools:
                            if isinstance(t, dict) and t.get("name") in BAD_TOOL_NAMES:
                                dropped.append(t.get("name"))
                            else:
                                kept.append(t)
                        if dropped:
                            api_kwargs["tools"] = kept
            except Exception as e:
                log.warning("[codex-compat-patch] guard raised, passing through: %s", e)
            return _orig(self, api_kwargs, allow_stream=allow_stream)

        ResponsesApiTransport.preflight_kwargs = _patched
        ResponsesApiTransport._codex_compat_patch_applied = True
        log.info(
            "[codex-compat-patch] active: strip extra_headers + skip %d tool(s) with bad schemas",
            len(BAD_TOOL_NAMES),
        )
    except Exception as e:
        log.warning("[codex-compat-patch] startup hook bailed out: %s", e)
