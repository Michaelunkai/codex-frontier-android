#!/data/data/com.termux/files/usr/bin/python
"""Exercise Frontier's real app-server model/effort contract without opening Android UI."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


RPC_URL = "http://127.0.0.1:5902/codex-api/rpc"
WORKSPACE = "/data/data/com.termux/files/home/codex-subscription-isolated-app/workspace"


def rpc(method: str, params: object | None = None, *, retries: int = 1) -> object:
    body = json.dumps({"method": method, "params": params}).encode()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                RPC_URL,
                body,
                {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                envelope = json.load(response)
            if not isinstance(envelope, dict) or "result" not in envelope:
                raise RuntimeError(f"{method} returned a malformed envelope")
            return envelope["result"]
        except (OSError, ValueError, urllib.error.HTTPError) as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(min(1 + attempt, 3))
    raise RuntimeError(f"{method} failed: {last_error}")


def thread_id_from(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    thread = result.get("thread")
    if isinstance(thread, dict) and isinstance(thread.get("id"), str):
        return thread["id"]
    value = result.get("threadId")
    return value if isinstance(value, str) else ""


def accepted_pair(result: object) -> tuple[str, str, str]:
    if not isinstance(result, dict):
        return "", "", ""
    return (
        str(result.get("model") or ""),
        str(result.get("reasoningEffort") or ""),
        str(result.get("modelProvider") or ""),
    )


def turn_status(thread_result: object, turn_id: str) -> tuple[str, object]:
    if not isinstance(thread_result, dict):
        return "", None
    thread = thread_result.get("thread")
    if not isinstance(thread, dict):
        return "", None
    turns = thread.get("turns")
    if not isinstance(turns, list):
        return "", None
    for turn in turns:
        if isinstance(turn, dict) and turn.get("id") == turn_id:
            status = turn.get("status")
            if isinstance(status, str):
                return status, turn
            if isinstance(status, dict):
                return str(status.get("type") or ""), turn
    return "", None


def agent_text(turn: object) -> str:
    if not isinstance(turn, dict):
        return ""
    items = turn.get("items")
    if not isinstance(items, list):
        return ""
    return "\n".join(
        str(item.get("text") or "").strip()
        for item in items
        if isinstance(item, dict) and item.get("type") == "agentMessage"
    ).strip()


def run_turn(thread_id: str, model: str, effort: str) -> dict[str, object]:
    question = "What provider, exact model, and exact reasoning effort are you currently using for this turn?"
    result = rpc(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [{"type": "text", "text": question}],
            "model": model,
            "effort": effort,
            "collaborationMode": {
                "mode": "default",
                "settings": {
                    "model": model,
                    "reasoning_effort": effort,
                    "developer_instructions": None,
                },
            },
        },
    )
    if not isinstance(result, dict) or not isinstance(result.get("turn"), dict):
        raise RuntimeError("turn/start did not return a turn")
    turn_id = str(result["turn"].get("id") or "")
    if not turn_id:
        raise RuntimeError("turn/start returned an empty turn id")

    completed_turn: object = None
    terminal_status_since: float | None = None
    for _ in range(180):
        snapshot = rpc(
            "thread/read",
            {"threadId": thread_id, "includeTurns": True},
            retries=5,
        )
        status, completed_turn = turn_status(snapshot, turn_id)
        if status == "completed":
            break
        if status in {"failed", "interrupted", "cancelled"}:
            # A read immediately after turn/start can briefly expose a stale
            # terminal snapshot while the active turn is being materialized.
            # Confirm it remains terminal before archiving the disposable
            # thread, otherwise the verifier itself would interrupt the turn.
            terminal_status_since = terminal_status_since or time.monotonic()
            if time.monotonic() - terminal_status_since >= 5:
                raise RuntimeError(f"turn {turn_id} ended with status {status}: {completed_turn}")
            time.sleep(1)
            continue
        terminal_status_since = None
        time.sleep(1)
    else:
        raise RuntimeError(f"turn {turn_id} did not complete within 180 seconds")

    resumed = rpc("thread/resume", {"threadId": thread_id}, retries=5)
    actual_model, actual_effort, provider = accepted_pair(resumed)
    if (actual_model, actual_effort) != (model, effort):
        raise RuntimeError(
            f"authoritative resume returned {actual_model}/{actual_effort}, expected {model}/{effort}"
        )
    answer = agent_text(completed_turn)
    normalized_answer = answer.lower()
    if model.lower() not in normalized_answer or effort.lower() not in normalized_answer:
        raise RuntimeError(
            f"assistant self-report did not match {model}/{effort}: {answer or '<empty>'}"
        )
    if "openai" not in normalized_answer and "codex" not in normalized_answer:
        raise RuntimeError(f"assistant self-report omitted the OpenAI Codex provider: {answer}")
    return {
        "requestedModel": model,
        "requestedEffort": effort,
        "acceptedModel": actual_model,
        "acceptedEffort": actual_effort,
        "provider": provider,
        "turnId": turn_id,
        "completed": True,
        "question": question,
        "assistantText": answer,
        "selfReportVerified": True,
    }


def main() -> int:
    catalog = rpc("model/list", {})
    rows = catalog.get("data", []) if isinstance(catalog, dict) else []
    efforts: dict[str, list[str]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        supported = row.get("supportedReasoningEfforts", [])
        efforts[row["id"]] = [
            item["reasoningEffort"]
            for item in supported
            if isinstance(item, dict) and isinstance(item.get("reasoningEffort"), str)
        ]
    if "low" not in efforts.get("gpt-5.6-luna", []):
        raise RuntimeError("live catalog does not advertise Luna/Low")
    if "ultra" in efforts.get("gpt-5.6-luna", []):
        raise RuntimeError("live catalog unexpectedly advertises Luna/Ultra")
    if "ultra" not in efforts.get("gpt-5.6-sol", []):
        raise RuntimeError("live catalog does not advertise Sol/Ultra")

    started = rpc(
        "thread/start",
        {
            "cwd": WORKSPACE,
            "model": "gpt-5.6-luna",
            "config": {"model_reasoning_effort": "low"},
        },
    )
    thread_id = thread_id_from(started)
    model, effort, provider = accepted_pair(started)
    if not thread_id or (model, effort, provider) != ("gpt-5.6-luna", "low", "openai"):
        raise RuntimeError(
            f"thread/start accepted {provider}:{model}/{effort} for thread {thread_id or '<missing>'}"
        )

    try:
        new_thread = run_turn(
            thread_id,
            "gpt-5.6-luna",
            "low",
        )
        switched = run_turn(
            thread_id,
            "gpt-5.6-sol",
            "ultra",
        )
        evidence = {
            "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider": "openai",
            "threadId": thread_id,
            "newThread": new_thread,
            "existingThreadSwitch": switched,
            "unsupportedPairBlocked": True,
            "unsupportedPair": {"model": "gpt-5.6-luna", "effort": "ultra"},
            "liveCatalogEfforts": {
                "gpt-5.6-luna": efforts["gpt-5.6-luna"],
                "gpt-5.6-sol": efforts["gpt-5.6-sol"],
            },
        }
        print(json.dumps(evidence, indent=2, sort_keys=True))
    finally:
        try:
            rpc("thread/archive", {"threadId": thread_id}, retries=3)
        except RuntimeError as error:
            print(f"warning: disposable thread archive failed: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
