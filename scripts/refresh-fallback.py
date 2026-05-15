"""Refresh Hermes fallback_providers from a chosen OpenRouter free model.

This script lives on the Hermes volume at /data/.hermes/scripts/refresh-fallback.py
and is invoked by .github/workflows/daily-fallback-model.yml via `railway ssh`.

Usage:
    echo '{"id": "...", "name": "...", "ok": true|false}' | refresh-fallback.py

Input is JSON on stdin (railway ssh flattens positional args without quoting,
so model names with spaces or shell-special characters need this).

If ok=false (shir-man unreachable), we keep the last-known-good entry
from /data/.hermes/fallback-model-last-known.json instead of clearing the chain.
If that file is also missing, the script aborts non-zero so the cron run
fails loudly rather than wiping a working config.

Atomic write: yaml is written to a sibling temp file and renamed — never leaves
a half-written /data/.hermes/config.yaml on disk.

If you ever lose the Hermes volume, restore this file to
/data/.hermes/scripts/refresh-fallback.py and re-seed by running it once with
the current top model from https://shir-man.com/api/free-llm/top-models.
"""
from __future__ import annotations
import sys, os, re, json, yaml, datetime, tempfile

CFG = "/data/.hermes/config.yaml"
LKG = "/data/.hermes/fallback-model-last-known.json"
MODEL_RE = re.compile(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._:-]+$")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"ERROR: stdin is not valid JSON: {e}", file=sys.stderr)
        return 4
    mid = str(payload.get("id", "")).strip()
    mnm = str(payload.get("name", "")).strip()
    ok  = bool(payload.get("ok", False))

    if not ok:
        try:
            with open(LKG) as f:
                d = json.load(f)
            mid = (d.get("id") or "").strip()
            mnm = (d.get("name") or "").strip()
        except FileNotFoundError:
            print("ERROR: fetch failed AND no last-known-good file at", LKG, file=sys.stderr)
            return 2
        if not mid:
            print("ERROR: fetch failed AND last-known-good is empty", file=sys.stderr)
            return 2
        print(f"shir-man unreachable — reusing last-known-good: {mid}")

    if not MODEL_RE.match(mid):
        print(f"ERROR: model id {mid!r} fails sanity regex", file=sys.stderr)
        return 3

    with open(CFG) as f:
        cfg = yaml.safe_load(f) or {}

    entry = {
        "provider": "openrouter",
        "model": mid,
        "base_url": "https://openrouter.ai/api/v1",
    }
    cfg["fallback_providers"] = [entry]

    fd, tmp = tempfile.mkstemp(prefix="config.yaml.", dir="/data/.hermes")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, CFG)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

    with open(LKG, "w") as f:
        json.dump({
            "id": mid,
            "name": mnm,
            "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": "shir-man.com/api/free-llm/top-models" if ok else "last-known-good",
        }, f, indent=2)

    print(f"OK fallback={mid} ({mnm or '<no name>'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
