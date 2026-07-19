#!/data/data/com.termux/files/usr/bin/python
"""CodexApp capability runtime.

The same file is executable through command-name symlinks or as:
    codex_runtime.py codex-health --json
"""

import argparse
import base64
import concurrent.futures
import contextlib
import datetime as dt
import hashlib
import hmac
import html
from html.parser import HTMLParser
import json
import mimetypes
import os
import pathlib
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile


VERSION = "1.7.0"
COMMANDS = (
    "codex-route",
    "codex-exec",
    "codex-search",
    "codex-source",
    "codex-fetch",
    "codex-download",
    "codex-acquire",
    "codex-install",
    "codex-update",
    "codex-delete",
    "codex-restore",
    "codex-fs",
    "codex-pm",
    "codex-android",
    "codex-privilege",
    "codex-provision",
    "codex-net",
    "codex-protocol",
    "codex-media",
    "codex-ocr",
    "codex-speech",
    "codex-vault",
    "codex-memory",
    "codex-schedule",
    "codex-health",
    "codex-audit",
    "codex-undo",
    "codex-win",
    "codex-github",
    "codex-job",
    "codex-goal",
    "codex-capability",
    "codex-verify",
    "codex-recover",
    "codex-browser",
    "codex-ui",
    "codex-network",
    "codex-artifact",
    "codex-package",
    "codex-account",
    "codex-entitlement",
    "codex-todoist",
    "codex-action",
    "codex-app",
    "codex-notification",
)

PROTECTED_PACKAGES = {
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.packageinstaller",
    "com.google.android.permissioncontroller",
    "com.michaelovsky.codexapplauncher",
    "com.michaelovsky.codexnvidia.isolated",
    "com.michaelovsky.codexsubscription.isolated",
    "com.termux",
    "moe.shizuku.privileged.api",
}

ACTION_STRATEGIES = [
    "native_media_search",
    "media_browser",
    "intent_or_deep_link",
    "accessibility",
    "uiautomator",
    "vision",
    "browser",
    "windows_gateway",
]

APP_ADAPTERS = {
    "youtube_music": {
        "id": "youtube_music",
        "name": "YouTube Music",
        "version": 1,
        "officialPackage": "com.google.android.apps.youtube.music",
        "packageAliases": [
            "com.google.android.apps.youtube.music",
            "app.revanced.android.apps.youtube.music",
            "app.rvx.android.apps.youtube.music",
            "anddea.youtube.music",
        ],
        "packageProvenance": {
            "com.google.android.apps.youtube.music": "official",
            "app.revanced.android.apps.youtube.music": "user-installed-unofficial",
            "app.rvx.android.apps.youtube.music": "user-installed-unofficial",
            "anddea.youtube.music": "user-installed-unofficial",
        },
        "intents": [
            "android.media.action.MEDIA_PLAY_FROM_SEARCH",
            "android.intent.action.MAIN",
        ],
        "deepLinks": ["https://music.youtube.com/search?q={query}"],
        "actions": [
            "open",
            "search",
            "play",
            "pause",
            "resume",
            "stop",
            "next",
            "previous",
            "seek",
            "shuffle",
            "repeat",
            "now_playing",
        ],
        "verifiers": ["media_session", "foreground_or_notification"],
        "selectors": {
            "search": [
                {"contentDescription": "Search"},
                {"text": "Search"},
            ],
            "searchField": [
                {"resourceIdSuffix": "search_edit_text"},
                {"className": "android.widget.EditText"},
            ],
        },
    },
    "youtube": {
        "id": "youtube",
        "name": "YouTube",
        "version": 1,
        "officialPackage": "com.google.android.youtube",
        "packageAliases": ["com.google.android.youtube", "app.revanced.android.youtube"],
        "intents": ["android.intent.action.VIEW", "android.intent.action.MAIN"],
        "deepLinks": ["https://www.youtube.com/results?search_query={query}"],
        "actions": ["open", "search", "play", "pause", "resume", "next", "previous"],
        "verifiers": ["media_session", "foreground_or_notification"],
    },
    "todoist": {
        "id": "todoist",
        "name": "Todoist",
        "version": 1,
        "officialPackage": "com.todoist",
        "packageAliases": ["com.todoist"],
        "intents": ["android.intent.action.MAIN", "android.intent.action.VIEW"],
        "deepLinks": ["todoist://"],
        "actions": ["open", "inspect_account", "inspect_entitlement"],
        "verifiers": ["package_manager", "foreground_or_ui"],
    },
    "chrome": {
        "id": "chrome",
        "name": "Chrome",
        "version": 1,
        "officialPackage": "com.android.chrome",
        "packageAliases": ["com.android.chrome"],
        "intents": ["android.intent.action.VIEW", "android.intent.action.MAIN"],
        "deepLinks": [],
        "actions": ["open", "navigate", "search"],
        "verifiers": ["foreground_or_ui"],
    },
}


# Human labels that cannot be inferred reliably from Android package names.
# Resolution still searches every installed package, so this table improves
# common-name precision without limiting support to a fixed application list.
ANDROID_APP_ALIASES = {
    "settings": ("com.android.settings",),
    "play store": ("com.android.vending",),
    "google play": ("com.android.vending",),
    "chrome": ("com.android.chrome",),
    "google chrome": ("com.android.chrome",),
    "facebook": ("com.facebook.katana",),
    "messenger": ("com.facebook.orca",),
    "facebook messenger": ("com.facebook.orca",),
    "whatsapp": ("com.whatsapp",),
    "instagram": ("com.instagram.android",),
    "threads": ("com.instagram.barcelona",),
    "youtube": (
        "com.google.android.youtube",
        "app.revanced.android.youtube",
        "app.rvx.android.youtube",
        "anddea.youtube",
    ),
    "youtube music": (
        "com.google.android.apps.youtube.music",
        "app.revanced.android.apps.youtube.music",
        "app.rvx.android.apps.youtube.music",
        "anddea.youtube.music",
    ),
    "spotify": ("com.spotify.music",),
    "telegram": ("org.telegram.messenger",),
    "tiktok": ("com.zhiliaoapp.musically",),
    "reddit": ("com.reddit.frontpage",),
    "gmail": ("com.google.android.gm",),
    "outlook": ("com.microsoft.office.outlook",),
    "maps": ("com.google.android.apps.maps",),
    "google maps": ("com.google.android.apps.maps",),
    "photos": ("com.google.android.apps.photos", "com.sec.android.gallery3d"),
    "gallery": ("com.sec.android.gallery3d", "com.google.android.apps.photos"),
    "camera": ("com.sec.android.app.camera", "com.android.camera2"),
    "phone": ("com.samsung.android.dialer", "com.google.android.dialer"),
    "dialer": ("com.samsung.android.dialer", "com.google.android.dialer"),
    "contacts": ("com.samsung.android.app.contacts", "com.google.android.contacts"),
    "messages": ("com.samsung.android.messaging", "com.google.android.apps.messaging"),
    "files": ("com.google.android.documentsui", "com.sec.android.app.myfiles"),
    "my files": ("com.sec.android.app.myfiles", "com.google.android.documentsui"),
    "calendar": ("com.samsung.android.calendar", "com.google.android.calendar"),
    "clock": ("com.sec.android.app.clockpackage", "com.google.android.deskclock"),
    "calculator": ("com.sec.android.app.popupcalculator", "com.google.android.calculator"),
    "notes": ("com.samsung.android.app.notes", "com.google.android.keep"),
    "todoist": ("com.todoist",),
    "chatgpt": ("com.openai.chatgpt",),
    "shizuku": ("moe.shizuku.privileged.api",),
    "termux": ("com.termux",),
    "nvidia autonomy": ("com.michaelovsky.codexnvidia.isolated",),
    "codex frontier": ("com.michaelovsky.codexsubscription.isolated",),
    "codex": ("com.michaelovsky.codexapplauncher",),
}


class CommandFailure(Exception):
    def __init__(self, message, code=1, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def iso_now():
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def runtime_root(env=None):
    env = env or os.environ
    configured = env.get("CODEX_RUNTIME_ROOT")
    return pathlib.Path(configured).expanduser() if configured else pathlib.Path.home() / ".codex"


def ensure_layout(root):
    for name in (
        "audit",
        "acquisitions",
        "downloads",
        "capabilities",
        "memory",
        "quarantine",
        "task-history",
        "undo",
        "vault",
        "jobs",
        "evidence",
        "locks",
        "artifacts",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)


def atomic_write(path, content, mode="w"):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".tmp-" + uuid.uuid4().hex
    temp = path.with_name(path.name + suffix)
    try:
        if "b" in mode:
            with open(temp, mode) as stream:
                stream.write(content)
        else:
            with open(temp, mode, encoding="utf-8") as stream:
                stream.write(content)
        for attempt in range(5):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01 * (2 ** attempt))
    finally:
        if temp.exists():
            temp.unlink()


def atomic_write_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def quarantine_corrupt_record(root, path, kind):
    path = pathlib.Path(path)
    if not path.exists():
        return None
    destination = pathlib.Path(root) / "quarantine" / (
        utc_now().strftime("%Y%m%dT%H%M%S")
        + "-corrupt-"
        + str(kind)
        + "-"
        + path.name
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(path), str(destination))
    except OSError:
        return None
    return str(destination)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_path(path):
    return pathlib.Path(path).expanduser().absolute()


def command_result(ok=True, **values):
    result = {"ok": bool(ok)}
    result.update(values)
    return result


def enrich_result_envelope(result, command, started, finished, code):
    """Give every public command response the same truthful outer contract."""
    if not isinstance(result, dict):
        result = command_result(value=result)
    job = result.get("job") if isinstance(result.get("job"), dict) else {}
    verified = bool(result.get("verified", False))
    if "status" not in result:
        result["status"] = (
            "verified" if verified else
            "completed_unverified" if result.get("ok") else
            "failed"
        )
    result.setdefault("command", command)
    result.setdefault("startedAt", started.isoformat().replace("+00:00", "Z"))
    result.setdefault("finishedAt", finished.isoformat().replace("+00:00", "Z"))
    result.setdefault("jobId", result.get("jobId") or job.get("id"))
    result.setdefault("step", result.get("step") or job.get("currentStep") or job.get("step"))
    result.setdefault(
        "strategy",
        result.get("strategy") or job.get("currentStrategy") or job.get("strategy"),
    )
    try:
        result.setdefault("attempt", int(result.get("attempt") or job.get("attempt") or 1))
    except (TypeError, ValueError):
        result.setdefault("attempt", 1)
    result.setdefault("nextAction", result.get("nextAction") or job.get("nextAction"))
    result.setdefault("errorCode", None if result.get("ok") else "command_failed")
    result.setdefault("message", result.get("message") or result.get("error"))
    result.setdefault("manualActionRequired", False)
    result["verified"] = verified
    result.setdefault("exitCode", code)
    return result


def get_app_adapter(adapter_id):
    normalized = str(adapter_id).strip().lower().replace("-", "_").replace(" ", "_")
    adapter = APP_ADAPTERS.get(normalized)
    if not adapter:
        raise CommandFailure("unknown application adapter: " + str(adapter_id), code=4)
    return json.loads(json.dumps(adapter))


def dynamic_app_adapter(package):
    package = str(package or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", package):
        raise CommandFailure("invalid Android package name: " + package, code=2)
    return {
        "id": "package:" + package,
        "name": package,
        "version": 1,
        "officialPackage": package,
        "packageAliases": [package],
        "packageProvenance": {package: "user-specified"},
        "intents": ["android.intent.action.MAIN"],
        "deepLinks": [],
        "actions": ["open"],
        "verifiers": ["package_manager", "foreground_or_ui"],
    }


def resolve_app_adapter(target, context):
    try:
        return get_app_adapter(target)
    except CommandFailure:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", str(target or "")):
            return dynamic_app_adapter(target)
        resolved = automation_broker_request(
            context["root"],
            {"action": "app.resolve", "arguments": {"query": str(target or "")}},
            context["test_mode"],
        )
        package = str(resolved.get("package") or "").strip()
        if not package:
            raise CommandFailure("application resolver returned no package", code=4)
        return dynamic_app_adapter(package)


def classify_action_risk(action):
    normalized = str(action).strip().lower().replace("-", "_")
    if normalized in {
        "media.now_playing",
        "app.inspect",
        "notification.list",
        "account.inspect",
        "entitlement.inspect",
    }:
        return "read_only"
    if normalized.startswith(("purchase.", "payment.", "legal.")):
        return "financial_or_legal"
    if normalized.startswith(("credential.", "security.", "permission.grant")):
        return "credential_or_security"
    if normalized.startswith(("delete.", "package.uninstall", "message.send", "call.place")):
        return "destructive"
    if normalized.startswith(("post.", "email.send", "calendar.invite")):
        return "external_nonfinancial"
    return "reversible_local"


def normalize_action_goal(request):
    original = " ".join(str(request).split()).strip()
    lowered = original.lower()
    sequence_parts = re.split(r"\s+(?:and\s+)?then\s+", original, flags=re.IGNORECASE)
    if len(sequence_parts) > 1:
        steps = []
        inherited_target = ""
        for part in sequence_parts:
            step_text = part.strip()
            step = normalize_action_goal(step_text)
            if inherited_target and (
                step.get("action") == "ui.goal" or not str(step.get("target") or "").strip()
            ):
                contextual = normalize_action_goal(step_text + " in " + inherited_target)
                if contextual.get("action") != "ui.goal":
                    step = contextual
            steps.append(step)
            inherited_target = str(
                step.get("package") or step.get("target") or inherited_target
            )
        risk_order = {
            "read_only": 0,
            "reversible_local": 1,
            "external_nonfinancial": 2,
            "credential_or_security": 3,
            "destructive": 4,
            "financial_or_legal": 5,
        }
        risk = max(
            (step.get("risk", "reversible_local") for step in steps),
            key=lambda value: risk_order.get(value, 1),
        )
        return {
            "request": original,
            "action": "sequence",
            "target": steps[0].get("target", "android"),
            "steps": steps,
            "requiredObservableState": {"allStepsVerified": True},
            "risk": risk,
        }
    media_match = re.match(
        r"^(?:play|start|listen\s+to)\s+(.+?)\s+"
        r"(?:on|in|using)\s+(?:the\s+)?youtube\s+music(?:\s+app)?$",
        original,
        flags=re.IGNORECASE,
    )
    compound_media_match = re.match(
        r"^(?:open|launch)\s+youtube\s+music(?:\s+and\s+)?"
        r"(?:play|start|listen\s+to)\s*(.*?)$",
        original,
        flags=re.IGNORECASE,
    )
    if media_match or compound_media_match or (
        lowered in {"play music", "start music", "resume music"}
    ):
        query = (
            (media_match.group(1) if media_match else None)
            if media_match
            else (compound_media_match.group(1) if compound_media_match else "")
        )
        query = (query or "").strip()
        if query.lower() in {"music", "some music", "anything"}:
            query = ""
        query = re.sub(
            r"\s+(?:on|in|using)\s+(?:the\s+)?youtube\s+music(?:\s+app)?\s*$",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        return {
            "request": original,
            "action": "media.play",
            "target": "youtube_music",
            "query": query,
            "requiredObservableState": {
                "playbackState": "PLAYING",
                "metadataMatchesQuery": True,
                "positionAdvances": True,
            },
            "risk": classify_action_risk("media.play"),
        }
    generic_compound_media_match = re.match(
        r"^(?:open|launch)\s+(.+?)\s+and\s+"
        r"(?:play|start|listen\s+to)\s*(.*?)$",
        original,
        flags=re.IGNORECASE,
    )
    if generic_compound_media_match:
        target_name = generic_compound_media_match.group(1).strip()
        query = generic_compound_media_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = ""
        if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ):
            target = target_name
            package = target_name
        return {
            "request": original,
            "action": "media.play",
            "target": target,
            "package": package,
            "query": query,
            "requiredObservableState": {
                "playbackState": "PLAYING",
                "metadataMatchesQuery": True,
                "positionAdvances": True,
            },
            "risk": classify_action_risk("media.play"),
        }
    generic_media_match = re.match(
        r"^(?:play|start|listen\s+to)\s+(.+?)\s+"
        r"(?:on|in|using)\s+(?:the\s+)?(.+?)(?:\s+app)?$",
        original,
        flags=re.IGNORECASE,
    )
    if generic_media_match:
        query = generic_media_match.group(1).strip()
        target_name = generic_media_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = ""
        if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ):
            target = target_name
            package = target_name
        return {
            "request": original,
            "action": "media.play",
            "target": target,
            "package": package,
            "query": query,
            "requiredObservableState": {
                "playbackState": "PLAYING",
                "metadataMatchesQuery": True,
                "positionAdvances": True,
            },
            "risk": classify_action_risk("media.play"),
        }
    semantic_ui_match = re.match(
        r"^(clear(?:\s+the)?\s+text|select\s+all|copy|cut|paste|dismiss|expand|collapse)\s+"
        r"(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if semantic_ui_match:
        operation_text = semantic_ui_match.group(1).lower().strip()
        operation = {
            "clear text": "clear_text",
            "clear the text": "clear_text",
            "select all": "select_all",
        }.get(operation_text, operation_text)
        target_name = semantic_ui_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = ""
        if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ):
            target = target_name
            package = target_name
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": operation,
            "openIfNeeded": True,
            "requiredObservableState": {"actionDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    navigation_match = re.match(
        r"^(?:go\s+to|navigate\s+to|open\s+url)\s+(https?://\S+)$",
        original,
        flags=re.IGNORECASE,
    )
    if navigation_match:
        url = navigation_match.group(1)
        return {
            "request": original,
            "action": "browser.navigate",
            "target": "browser",
            "query": url,
            "requiredObservableState": {"urlVisibleOrBrowserForeground": True},
            "risk": classify_action_risk("browser.navigate"),
        }
    inspect_match = re.match(
        r"^(?:inspect|check|verify)\s+(account|entitlement)\s+(?:in|on|for)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if inspect_match:
        fact = inspect_match.group(1).lower()
        target_name = inspect_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name):
            target = target_name
        return {
            "request": original,
            "action": "app.inspect",
            "target": target,
            "fact": fact,
            "package": target_name if target == target_name else "",
            "query": "",
            "requiredObservableState": {"observedState": "known"},
            "risk": classify_action_risk("app.inspect"),
        }
    text_match = re.match(
        r"^(?:type|enter|write)\s+(.+?)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if text_match:
        text = text_match.group(1).strip().strip('"\'')
        target_name = text_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "set_text",
            "text": text,
            "query": "",
            "requiredObservableState": {"textEntryDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    scroll_match = re.match(
        r"^scroll\s+(up|down|forward|backward)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if scroll_match:
        direction = scroll_match.group(1).lower()
        target_name = scroll_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        operation = "scroll_forward" if direction in {"down", "forward"} else "scroll_backward"
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": operation,
            "query": "",
            "requiredObservableState": {"scrollDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    swipe_match = re.match(
        r"^(?:swipe|drag)\s+(up|down|left|right)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if swipe_match:
        direction = swipe_match.group(1).lower()
        target_name = swipe_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "swipe",
            "direction": direction,
            "query": "",
            "requiredObservableState": {"swipeDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    navigation_action_match = re.match(
        r"^press\s+(back|home)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if navigation_action_match:
        operation = navigation_action_match.group(1).lower()
        target_name = navigation_action_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": operation,
            "query": "",
            "requiredObservableState": {"navigationDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    global_action_match = re.match(
        r"^(?:press|open|show|display)\s+"
        r"(notifications?|notification\s+shade|quick\s+settings?|"
        r"recent\s+apps?|recents|power(?:\s+menu)?|lock\s+screen|"
        r"screenshot|split\s+screen|accessibility\s+shortcut)\s+"
        r"(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if global_action_match:
        key_text = re.sub(r"\s+", "_", global_action_match.group(1).strip().lower())
        key_text = {
            "notification": "notifications",
            "notification_shade": "notifications",
            "quick_setting": "quick_settings",
            "recent_app": "recent_apps",
            "power_menu": "power_dialog",
        }.get(key_text, key_text)
        target_name = global_action_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "global_action",
            "key": key_text,
            "query": "",
            "requiredObservableState": {"globalActionDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    ime_action_match = re.match(
        r"^(?:press|hit|send)\s+(enter|search|done|go|next|previous)"
        r"(?:\s+(?:in|on)\s+(.+))?$",
        original,
        flags=re.IGNORECASE,
    )
    if ime_action_match:
        target_name = (ime_action_match.group(2) or "").strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "ime_action",
            "query": "",
            "requiredObservableState": {"imeActionDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    media_action_match = re.match(
        r"^(pause|resume|stop|next|previous)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if media_action_match:
        operation = media_action_match.group(1).lower()
        target_name = media_action_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": operation,
            "query": "",
            "requiredObservableState": {"mediaStateChanged": True},
            "risk": classify_action_risk("app.action"),
        }
    compound_app_action_match = re.match(
        r"^(?:open|launch)\s+(.+?)\s+and\s+"
        r"(click|tap|press|long\s+press|type|enter|wait\s+(?:for|until)|scroll\s+(?:up|down|forward|backward))\s*(.*?)$",
        original,
        flags=re.IGNORECASE,
    )
    if compound_app_action_match:
        target_name = compound_app_action_match.group(1).strip()
        operation_text = compound_app_action_match.group(2).lower().strip()
        value = compound_app_action_match.group(3).strip().strip('"\'')
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        operation = "click"
        selector = None
        text = None
        if operation_text == "long press":
            operation = "long_click"
            selector = {"labelContains": value, "clickableOnly": True}
        elif operation_text in {"click", "tap", "press"}:
            selector = {"labelContains": value, "clickableOnly": True}
        elif operation_text == "type":
            operation = "set_text"
            text = value
        elif operation_text == "enter":
            operation = "ime_action"
        elif operation_text in {"wait for", "wait until"}:
            operation = "wait_for"
            selector = {"labelContains": value}
        elif operation_text.startswith("scroll "):
            operation = (
                "scroll_forward"
                if operation_text.split(" ", 1)[1] in {"down", "forward"}
                else "scroll_backward"
            )
        result = {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": operation,
            "query": "",
            "openIfNeeded": True,
            "requiredObservableState": (
                {"selectorReady": True}
                if operation == "wait_for"
                else {"actionDispatched": True}
            ),
            "risk": classify_action_risk("app.action"),
        }
        if selector:
            result["selector"] = selector
        if text is not None:
            result["text"] = text
        return result
    wait_match = re.match(
        r"^wait\s+(?:for|until)\s+(.+)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if wait_match:
        selector_text = wait_match.group(1).strip().strip('"\'')
        target_name = wait_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = target_name if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name
        ) else ""
        if package:
            target = package
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "wait_for",
            "selector": {"labelContains": selector_text},
            "query": "",
            "openIfNeeded": True,
            "requiredObservableState": {"selectorReady": True},
            "risk": classify_action_risk("app.action"),
        }
    ui_match = re.match(
        r"^(?:click|tap|press)\s+(.+?)\s+(?:in|on)\s+(.+)$",
        original,
        flags=re.IGNORECASE,
    )
    if ui_match:
        label = ui_match.group(1).strip()
        target_name = ui_match.group(2).strip()
        target = target_name.lower().replace("-", "_").replace(" ", "_")
        package = ""
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", target_name):
            target = target_name
            package = target_name
        return {
            "request": original,
            "action": "app.action",
            "target": target,
            "package": package,
            "operation": "click",
            "selector": {"labelContains": label, "clickableOnly": True},
            "query": "",
            "requiredObservableState": {"actionDispatched": True},
            "risk": classify_action_risk("app.action"),
        }
    if lowered.startswith(("open ", "launch ")):
        name = re.sub(r"^(?:open|launch)\s+", "", original, flags=re.IGNORECASE)
        target = name.lower().replace(" ", "_")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", name):
            target = name
        return {
            "request": original,
            "action": "app.open",
            "target": target,
            "query": "",
            "requiredObservableState": {"foregroundTarget": True},
            "risk": classify_action_risk("app.open"),
        }
    return {
        "request": original,
        "action": "ui.goal",
        "target": "android",
        "query": original,
        "requiredObservableState": {"goalContractSatisfied": True},
        "risk": classify_action_risk("ui.goal"),
    }


def parse_media_session_dump(text):
    sessions = []
    current = None
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        package_match = re.match(r"package=([A-Za-z0-9._]+)", line)
        if package_match:
            if current and current.get("package"):
                sessions.append(current)
            current = {
                "package": package_match.group(1),
                "playbackState": None,
                "positionMs": None,
                "title": None,
                "artist": None,
            }
            continue
        if current is None:
            continue
        state_match = re.search(
            r"state=PlaybackState\s*\{state=([A-Z_]+)\(\d+\),\s*position=(\d+)",
            line,
        )
        if state_match:
            current["playbackState"] = state_match.group(1)
            current["positionMs"] = int(state_match.group(2))
            continue
        if line.startswith("metadata:"):
            description = re.search(r"description=([^,}]+)(?:,\s*([^,}]+))?", line)
            if description:
                current["title"] = description.group(1).strip()
                if description.group(2):
                    current["artist"] = description.group(2).strip()
    if current and current.get("package"):
        sessions.append(current)
    return sessions


def _media_terms(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(token) > 1 and token not in {"play", "on", "by", "the", "music", "youtube"}
    }


def verify_media_playback(query, before, after, allowed_packages):
    allowed = set(allowed_packages or [])
    package_match = bool(after and after.get("package") in allowed)
    state_match = bool(after and after.get("playbackState") == "PLAYING")
    before_position = int((before or {}).get("positionMs") or 0)
    after_position = int((after or {}).get("positionMs") or 0)
    position_advanced = after_position > before_position
    expected_terms = _media_terms(query)
    observed_terms = _media_terms(
        " ".join(
            [
                str((after or {}).get("title") or ""),
                str((after or {}).get("artist") or ""),
            ]
        )
    )
    metadata_match = bool(expected_terms) and len(expected_terms & observed_terms) >= max(
        1, min(2, len(expected_terms))
    )
    verified = package_match and state_match and position_advanced and metadata_match
    return command_result(
        verified=verified,
        packageMatch=package_match,
        playbackStateMatch=state_match,
        positionAdvanced=position_advanced,
        metadataMatch=metadata_match,
        before=before,
        after=after,
    )


JOB_STATES = {
    "created",
    "planning",
    "running",
    "checkpointed",
    "recovering",
    "waiting_for_system_ui",
    "waiting_for_network",
    "waiting_for_credential",
    "waiting_for_external_event",
    "waiting_for_alternative",
    "verified",
    "manual_stop",
    "abandoned",
    "failed_permanently",
}


def next_sequence(root):
    path = pathlib.Path(root) / "task-history" / "sequence.json"
    value = load_json(path, {"next": 1})
    sequence = int(value.get("next", 1))
    atomic_write_json(path, {"next": sequence + 1})
    return sequence


def job_path(root, job_id):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(job_id))
    if not safe:
        raise CommandFailure("job id is empty", code=2)
    return pathlib.Path(root) / "jobs" / (safe + ".json")


def load_job(root, job_id):
    path = job_path(root, job_id)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            job = json.load(stream)
    except FileNotFoundError:
        job = None
    except (json.JSONDecodeError, OSError) as exc:
        quarantined = quarantine_corrupt_record(root, path, "job")
        raise CommandFailure(
            "job record is corrupt",
            code=6,
            details={
                "errorCode": "corrupt_job_record",
                "jobId": str(job_id),
                "quarantinePath": quarantined,
                "reason": str(exc),
            },
        ) from exc
    if not job:
        raise CommandFailure("job not found: " + str(job_id), code=4)
    return job


def save_job(root, job):
    job["updatedAt"] = iso_now()
    atomic_write_json(job_path(root, job["id"]), job)
    return job


def active_job_binding_path(root):
    return pathlib.Path(root) / "codexapp-active-job.json"


def write_active_job_binding(root, job, state=None):
    """Bind completion evidence to the one job currently allowed to finish."""
    binding = {
        "jobId": str(job.get("id", "")),
        "executionNonce": str(job.get("executionNonce", "")),
        "state": state or job.get("state"),
        "updatedAt": iso_now(),
    }
    atomic_write_json(active_job_binding_path(root), binding)
    return binding


@contextlib.contextmanager
def job_execution_lock(root, job_id):
    """Serialize side effects for one durable job across runtime processes."""
    lock_path = pathlib.Path(root) / "locks" / ("job-" + re.sub(r"[^A-Za-z0-9._-]", "_", str(job_id)) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            age = time.time() - lock_path.stat().st_mtime
        except OSError:
            age = 0
        if age > 1800:
            try:
                lock_path.unlink()
            except OSError:
                pass
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise CommandFailure(
            "job is already executing",
            code=9,
            details={"errorCode": "job_already_running", "jobId": str(job_id)},
        ) from exc
    try:
        os.write(descriptor, (str(os.getpid()) + "\n" + iso_now() + "\n").encode("utf-8"))
        os.close(descriptor)
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def parse_json_option(options, key, default=None):
    value = options.get(key)
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def new_goal_contract(text, options=None):
    options = options or {}
    normalized = normalize_action_goal(text)
    required_facts = parse_json_option(options, "required-facts", [])
    stability_explicit = "stability" in options
    return {
        "target": text.strip(),
        "targetEntity": normalized.get("target"),
        "requiredFacts": required_facts,
        "requiredObservableState": normalized.get("requiredObservableState", {}),
        "acceptedVersions": parse_json_option(options, "accepted-versions", []),
        "constraints": parse_json_option(options, "constraints", {}),
        "allowedStrategies": parse_json_option(options, "strategies", []),
        "prohibitedSubstitutions": parse_json_option(options, "prohibited", []),
        "independentVerifier": options.get("verifier", "independent-readback"),
        "requiredIndependentVerifier": options.get("verifier", "independent-readback"),
        "stabilityWindowSeconds": int(options.get("stability", 5)),
        "stabilityWindowExplicit": stability_explicit,
        "rollbackRequired": str(options.get("rollback", "true")).lower() != "false",
        "completionEvidence": "primary + independent + stability",
        "successPredicates": [
            "required facts are present in persisted evidence",
            "independent evidence uses a distinct observation path",
            "stability evidence covers the configured window when explicitly required",
            "no pending, ambiguous, or unresolved state remains",
        ],
        "nonCompletionSignals": [
            "model-claim",
            "exit-code",
            "installer-visible",
            "screenshot-only",
        ],
    }


def create_job(root, job_id, text, options=None):
    path = job_path(root, job_id)
    if path.exists():
        raise CommandFailure("job already exists: " + str(job_id), code=5)
    now = iso_now()
    normalized = normalize_action_goal(text)
    job = {
        "id": str(job_id),
        "sequence": next_sequence(root),
        "executionNonce": uuid.uuid4().hex,
        "originalRequest": text,
        "normalizedGoal": normalized,
        "goalContract": new_goal_contract(text, options),
        "state": "created",
        "manualStop": False,
        "currentStrategy": None,
        "currentStep": None,
        "checkpointId": None,
        "attempt": 0,
        "retry": {"attempt": 0, "nextAt": None},
        "strategyHistory": [],
        "tools": [],
        "artifacts": [],
        "packages": [],
        "primaryEvidence": [],
        "independentEvidence": [],
        "stabilityEvidence": [],
        "evidence": [],
        "lastError": None,
        "nextAction": "begin",
        "executionMode": "runtime-action" if normalized.get("action") != "ui.goal" else "model-orchestrated",
        "completionMarker": None,
        "createdAt": now,
        "updatedAt": now,
    }
    saved = save_job(root, job)
    write_active_job_binding(root, saved, "created")
    return saved


def is_runtime_action_job(job):
    goal = job.get("normalizedGoal") if isinstance(job, dict) else None
    return isinstance(goal, dict) and goal.get("action") not in {None, "ui.goal"}


def is_model_orchestrated_job(job):
    return not is_runtime_action_job(job)


def persist_model_continuation(job, reason, error=None):
    """Keep unresolved natural-language work active until a concrete action is bound."""
    now = iso_now()
    job["state"] = "waiting_for_alternative"
    job["nextAction"] = "model-continuation"
    job["continuationRequired"] = {
        "jobId": str(job.get("id", "")),
        "request": job.get("originalRequest") or job.get("request") or "",
        "reason": str(reason),
        "instruction": (
            "Bind the next concrete, verifiable action to this job with "
            "codex-job continue --id <job-id> --request <action>."
        ),
        "createdAt": now,
    }
    if error:
        job["continuationRequired"]["error"] = error
    job.setdefault("continuationHistory", []).append(
        {"reason": str(reason), "at": now, "error": error}
    )
    job["retry"] = {
        "attempt": int(job.get("attempt", 1)),
        "nextAt": None,
        "state": "waiting_for_alternative",
        "reason": "model-continuation-required",
    }
    return job


def add_evidence(job, bucket, value):
    if value is None or value == "":
        return
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        value = parsed if isinstance(parsed, dict) else {
            "type": "observation",
            "value": value,
        }
        value.setdefault("recordedAt", iso_now())
    else:
        value = dict(value)
        value.setdefault("recordedAt", iso_now())
    job.setdefault(bucket, []).append(value)
    job.setdefault("evidence", []).append({"bucket": bucket, **value})


def verify_job(root, job):
    def evidence_items(value):
        if not value:
            return []
        return value if isinstance(value, list) else [value]

    def evidence_is_verified(items):
        return bool(items) and all(
            isinstance(item, dict) and item.get("verified") is True
            for item in items
        )

    def evidence_contains_fact(fact):
        observations = [*primary, *independent, *stable]
        if isinstance(fact, dict):
            return any(
                all(item.get(key) == value for key, value in fact.items())
                for item in observations
                if isinstance(item, dict)
            )
        key = str(fact)
        return any(
            isinstance(item, dict) and key in item and item.get(key) not in (None, False, "")
            for item in observations
        )

    def evidence_has_unresolved_state(items):
        unresolved = {"pending", "ambiguous", "unresolved", "installer_pending", "stale_process"}
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("status", "state", "errorCode"):
                if str(item.get(key, "")).lower() in unresolved:
                    return True
            if item.get("pending") is True or item.get("ambiguous") is True:
                return True
        return False

    primary = evidence_items(job.get("primaryEvidence"))
    independent = evidence_items(job.get("independentEvidence"))
    stable = evidence_items(job.get("stabilityEvidence"))
    contract = job.get("goalContract") or {}
    if not independent:
        raise CommandFailure(
            "independent evidence required",
            code=4,
            details={"errorCode": "independent_evidence_required"},
        )
    if not primary:
        raise CommandFailure(
            "primary evidence required",
            code=4,
            details={"errorCode": "primary_evidence_required"},
        )
    if not stable:
        raise CommandFailure(
            "stability evidence required",
            code=4,
            details={"errorCode": "stability_evidence_required"},
        )
    if not evidence_is_verified(primary):
        raise CommandFailure(
            "primary evidence is not verified",
            code=4,
            details={"errorCode": "primary_evidence_unverified"},
        )
    if not evidence_is_verified(independent):
        raise CommandFailure(
            "independent evidence is not verified",
            code=4,
            details={"errorCode": "independent_evidence_unverified"},
        )
    if not evidence_is_verified(stable):
        raise CommandFailure(
            "stability evidence is not verified",
            code=4,
            details={"errorCode": "stability_evidence_unverified"},
        )
    primary_types = {item.get("type") for item in primary}
    independent_types = {item.get("type") for item in independent}
    if primary_types & independent_types:
        raise CommandFailure(
            "independent evidence must use a different observation path",
            code=4,
            details={"errorCode": "independent_evidence_not_distinct"},
        )
    required_facts = contract.get("requiredFacts") or []
    missing_facts = [fact for fact in required_facts if not evidence_contains_fact(fact)]
    if missing_facts:
        raise CommandFailure(
            "required goal facts are not evidenced",
            code=4,
            details={
                "errorCode": "required_facts_missing",
                "missingFacts": missing_facts,
            },
        )
    if evidence_has_unresolved_state([*primary, *independent, *stable]):
        raise CommandFailure(
            "unresolved state remains in completion evidence",
            code=4,
            details={"errorCode": "unresolved_state_present"},
        )
    if contract.get("stabilityWindowExplicit"):
        required_ms = max(0, int(float(contract.get("stabilityWindowSeconds", 0)) * 1000))
        measured_ms = max(
            [
                int(item.get("durationMs", 0) or 0)
                for item in stable
                if isinstance(item, dict)
            ]
            or [0]
        )
        measured_ms = max(
            measured_ms,
            max(
                [
                    int(float(item.get("stableForSeconds", 0) or 0) * 1000)
                    for item in stable
                    if isinstance(item, dict)
                ]
                or [0]
            ),
        )
        if measured_ms < required_ms:
            raise CommandFailure(
                "stability window is not evidenced",
                code=4,
                details={
                    "errorCode": "stability_window_unproven",
                    "requiredMs": required_ms,
                    "measuredMs": measured_ms,
                },
            )
    if job.get("manualStop") or job.get("state") in {"manual_stop", "abandoned"}:
        raise CommandFailure(
            "manual stop or abandonment prevents verification",
            code=4,
            details={"errorCode": "job_not_active"},
        )
    if not job.get("executionNonce"):
        # Migrate jobs created before execution binding was introduced.
        job["executionNonce"] = uuid.uuid4().hex
    evidence = {
        "jobId": job["id"],
        "executionNonce": job.get("executionNonce"),
        "verifiedAt": iso_now(),
        "primary": primary,
        "independent": independent,
        "stability": stable,
        "contract": contract,
        "verificationSource": "codex-runtime-evidence-gate",
    }
    evidence_id = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    evidence["evidenceId"] = evidence_id
    atomic_write_json(pathlib.Path(root) / "evidence" / (job["id"] + ".json"), evidence)
    shared_evidence = pathlib.Path("/sdcard/Download/codexapp-goal-evidence.json")
    try:
        atomic_write_json(shared_evidence, evidence)
    except OSError:
        pass
    try:
        atomic_write_json(pathlib.Path(root) / "codexapp-goal-evidence.json", evidence)
    except OSError:
        pass
    marker = pathlib.Path(root) / "codexapp-goal-verified"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(marker, evidence_id + "\n")
    except OSError:
        pass
    job["state"] = "verified"
    job["nextAction"] = None
    job["lastError"] = None
    job["verifiedAt"] = evidence["verifiedAt"]
    job["goalVerifiedEvidenceId"] = evidence_id
    job["completionMarker"] = str(marker)
    saved = save_job(root, job)
    write_active_job_binding(root, saved, "verified")
    return saved


def capability_path(root, name):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(name))
    return pathlib.Path(root) / "capabilities" / (safe + ".json")


def capability_history_path(root, name):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(name))
    return pathlib.Path(root) / "capabilities" / "history" / (
        safe + "-" + utc_now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex + ".json"
    )


def preserve_capability_version(root, capability):
    if not capability:
        return None
    path = capability_history_path(root, capability.get("name", "unknown"))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, capability)
    return str(path)


def load_capabilities(root):
    result = []
    for path in sorted(pathlib.Path(root).glob("capabilities/*.json")):
        if path.name.startswith(("sequence", "manifest")):
            continue
        value = load_json(path, None)
        if value:
            result.append(value)
    return result


def inspect_artifact(path):
    path = canonical_path(path)
    if not path.exists() or not path.is_file():
        raise CommandFailure("artifact does not exist", code=4)
    return command_result(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        bytes=path.stat().st_size,
        readable=os.access(path, os.R_OK),
        sha256=sha256_file(path),
        contentType=mimetypes.guess_type(str(path))[0] or "application/octet-stream",
    )


def artifact_record_path(root, artifact_id):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(artifact_id)).strip("._")
    if not safe:
        raise CommandFailure("artifact id is empty", code=2)
    return pathlib.Path(root) / "artifacts" / (safe + ".json")


def load_artifact_record(root, artifact_id):
    record = load_json(artifact_record_path(root, artifact_id), None)
    if not isinstance(record, dict):
        raise CommandFailure(
            "artifact record not found: " + str(artifact_id),
            code=4,
            details={"errorCode": "artifact_record_missing"},
        )
    return record


def stage_artifact(root, target, artifact_id=None):
    target = canonical_path(target)
    inspection = inspect_artifact(target)
    if target.is_symlink():
        raise CommandFailure(
            "refusing to stage a symbolic-link artifact",
            code=3,
            details={"errorCode": "artifact_symlink_refused", "path": str(target)},
        )
    artifact_id = artifact_id or ("artifact-" + uuid.uuid4().hex[:16])
    staged_dir = pathlib.Path(root) / "artifacts" / "staged" / re.sub(
        r"[^A-Za-z0-9._-]", "_", str(artifact_id)
    )
    staged = staged_dir / target.name
    staged_dir.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copy2(str(target), str(staged))
        staged_inspection = inspect_artifact(staged)
        if staged_inspection["sha256"].lower() != inspection["sha256"].lower():
            raise CommandFailure(
                "staged artifact checksum mismatch",
                code=6,
                details={
                    "errorCode": "staged_checksum_mismatch",
                    "sourceSha256": inspection["sha256"],
                    "stagedSha256": staged_inspection["sha256"],
                },
            )
        record = {
            "artifactId": artifact_id,
            "state": "staged",
            "sourcePath": str(target),
            "stagedPath": str(staged),
            "name": target.name,
            "extension": target.suffix.lower(),
            "bytes": staged_inspection["bytes"],
            "sha256": staged_inspection["sha256"],
            "contentType": staged_inspection["contentType"],
            "createdAt": iso_now(),
            "updatedAt": iso_now(),
        }
        atomic_write_json(artifact_record_path(root, artifact_id), record)
        return command_result(
            artifactId=artifact_id,
            state="staged",
            verified=True,
            artifact=record,
            primaryEvidence={
                "type": "artifact-stage-copy",
                "verified": True,
                "sourcePath": str(target),
                "stagedPath": str(staged),
                "sha256": inspection["sha256"],
            },
            independentEvidence={
                "type": "staged-filesystem-hash",
                "verified": True,
                "path": str(staged),
                "sha256": staged_inspection["sha256"],
            },
        )
    except Exception:
        if staged_dir.exists():
            shutil.rmtree(staged_dir, ignore_errors=True)
        raise


def activate_staged_artifact(root, artifact_id, target):
    record = load_artifact_record(root, artifact_id)
    staged = canonical_path(record.get("stagedPath", ""))
    if not staged.exists() or not staged.is_file():
        raise CommandFailure(
            "staged artifact is unavailable",
            code=4,
            details={"errorCode": "staged_artifact_missing", "artifactId": artifact_id},
        )
    staged_hash = sha256_file(staged)
    expected_hash = str(record.get("sha256", "")).lower()
    if not expected_hash or staged_hash.lower() != expected_hash:
        raise CommandFailure(
            "staged artifact checksum no longer matches",
            code=6,
            details={
                "errorCode": "staged_checksum_mismatch",
                "expectedSha256": expected_hash,
                "actualSha256": staged_hash,
            },
        )
    target = canonical_path(target)
    if not allowed_delete_target(root, target):
        raise CommandFailure(
            "refusing out-of-scope artifact activation target",
            code=3,
            details={"errorCode": "artifact_target_out_of_scope", "target": str(target)},
        )
    if target == staged:
        raise CommandFailure("activation target cannot be the staged artifact", code=3)
    target.parent.mkdir(parents=True, exist_ok=True)
    activation_id = uuid.uuid4().hex[:12]
    previous = None
    if target.exists():
        previous = target.with_name(target.name + ".previous-" + activation_id)
        shutil.copy2(str(target), str(previous))
    temporary = target.with_name(target.name + ".activate-" + activation_id)
    try:
        shutil.copy2(str(staged), str(temporary))
        os.replace(str(temporary), str(target))
        active_hash = sha256_file(target)
        if active_hash.lower() != expected_hash:
            raise CommandFailure(
                "activated artifact checksum mismatch",
                code=6,
                details={
                    "errorCode": "activation_checksum_mismatch",
                    "expectedSha256": expected_hash,
                    "actualSha256": active_hash,
                },
            )
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if previous and pathlib.Path(previous).exists():
            os.replace(str(previous), str(target))
        raise
    record.update(
        {
            "state": "active",
            "targetPath": str(target),
            "previousPath": str(previous) if previous else None,
            "activatedAt": iso_now(),
            "updatedAt": iso_now(),
        }
    )
    atomic_write_json(artifact_record_path(root, artifact_id), record)
    return command_result(
        artifactId=artifact_id,
        state="active",
        targetPath=str(target),
        previousPath=str(previous) if previous else None,
        verified=True,
        primaryEvidence={
            "type": "artifact-activation-copy",
            "verified": True,
            "targetPath": str(target),
        },
        independentEvidence={
            "type": "activated-filesystem-hash",
            "verified": True,
            "path": str(target),
            "sha256": active_hash,
        },
        rollbackAvailable=bool(previous),
    )


def restore_staged_artifact(root, artifact_id):
    record = load_artifact_record(root, artifact_id)
    previous = record.get("previousPath")
    target = record.get("targetPath")
    if not previous or not target:
        raise CommandFailure(
            "artifact has no preserved activation to restore",
            code=4,
            details={"errorCode": "artifact_rollback_unavailable"},
        )
    previous_path = canonical_path(previous)
    target_path = canonical_path(target)
    if not previous_path.exists() or not previous_path.is_file():
        raise CommandFailure(
            "preserved artifact activation is unavailable",
            code=4,
            details={"errorCode": "artifact_previous_missing"},
        )
    current_backup = target_path.with_name(target_path.name + ".rolled-forward-" + uuid.uuid4().hex[:12])
    if target_path.exists():
        shutil.copy2(str(target_path), str(current_backup))
    temporary = target_path.with_name(target_path.name + ".restore-" + uuid.uuid4().hex[:12])
    try:
        shutil.copy2(str(previous_path), str(temporary))
        os.replace(str(temporary), str(target_path))
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if current_backup.exists():
            os.replace(str(current_backup), str(target_path))
        raise
    restored_hash = sha256_file(target_path)
    record.update(
        {
            "state": "restored",
            "restoredAt": iso_now(),
            "updatedAt": iso_now(),
            "restoredSha256": restored_hash,
            "rolledForwardPath": str(current_backup) if current_backup.exists() else None,
        }
    )
    atomic_write_json(artifact_record_path(root, artifact_id), record)
    return command_result(
        artifactId=artifact_id,
        state="restored",
        targetPath=str(target_path),
        restoredPath=str(previous_path),
        rolledForwardPath=str(current_backup) if current_backup.exists() else None,
        verified=True,
        primaryEvidence={"type": "artifact-restore-copy", "verified": True},
        independentEvidence={
            "type": "restored-filesystem-hash",
            "verified": True,
            "path": str(target_path),
            "sha256": restored_hash,
        },
    )


def inspect_apk_metadata(path, context):
    """Inspect APK identity before installation when the platform inspector exists."""
    path = canonical_path(path)
    if path.suffix.lower() != ".apk":
        return {"available": False, "reason": "not-a-single-apk"}
    if context.get("test_mode"):
        return {
            "available": True,
            "package": context.get("expected_package"),
            "version": VERSION,
            "versionCode": 140,
            "permissions": [],
            "abis": [],
            "simulated": True,
        }
    inspector = next(
        (
            candidate
            for candidate in ("aapt", "aapt2", "apkanalyzer")
            if shutil.which(candidate)
        ),
        None,
    )
    if not inspector:
        return {
            "available": False,
            "reason": "apk-inspector-unavailable",
            "path": str(path),
        }
    command = (
        [inspector, "dump", "badging", str(path)]
        if pathlib.Path(inspector).name.lower().startswith(("aapt",))
        else [inspector, "manifest", "print", str(path)]
    )
    result = run_process(command, timeout=45)
    if not result["ok"]:
        raise CommandFailure(
            "APK metadata inspection failed",
            code=6,
            details={"errorCode": "apk_metadata_invalid", "result": result},
        )
    text = result.get("stdout", "")
    package_match = re.search(
        r"package:\s+name='([^']+)'\s+versionCode='([^']+)'\s+versionName='([^']*)'",
        text,
    )
    if not package_match:
        raise CommandFailure(
            "APK metadata did not contain package identity",
            code=6,
            details={"errorCode": "apk_identity_missing", "inspector": inspector},
        )
    permissions = re.findall(r"uses-permission: name='([^']+)'", text)
    abis_match = re.search(r"native-code:((?:\s+'[^']+')+)", text)
    abis = re.findall(r"'([^']+)'", abis_match.group(1)) if abis_match else []
    launch_match = re.search(r"launchable-activity: name='([^']+)'", text)
    sdk = re.search(r"sdkVersion:'([^']+)'", text)
    target_sdk = re.search(r"targetSdkVersion:'([^']+)'", text)
    metadata = {
        "available": True,
        "inspector": inspector,
        "package": package_match.group(1),
        "versionCode": int(package_match.group(2)) if package_match.group(2).isdigit() else package_match.group(2),
        "version": package_match.group(3),
        "minSdk": sdk.group(1) if sdk else None,
        "targetSdk": target_sdk.group(1) if target_sdk else None,
        "abis": abis,
        "permissions": permissions,
        "launchActivity": launch_match.group(1) if launch_match else None,
    }
    signer_tool = shutil.which("apksigner")
    if signer_tool:
        signature = run_process(
            [signer_tool, "verify", "--print-certs", str(path)],
            timeout=45,
        )
        if not signature["ok"]:
            raise CommandFailure(
                "APK signature verification failed",
                code=6,
                details={"errorCode": "apk_signature_invalid", "result": signature},
            )
        digest = re.search(
            r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)",
            signature.get("stdout", ""),
        )
        metadata["signer"] = digest.group(1).replace(":", "").lower() if digest else None
        metadata["signatureVerified"] = bool(digest)
    else:
        metadata["signatureVerified"] = False
        metadata["signatureReason"] = "apksigner-unavailable"
    return metadata


def package_inspection(package, context):
    expected_version = context.get("expected_version")
    if context["test_mode"]:
        return {
            "package": package,
            "version": expected_version or VERSION,
            "versionCode": 140,
            "installed": True,
            "enabled": True,
            "signer": "test-signer",
            "source": "test-package-manager",
        }
    result = run_privileged(["pm", "path", package], test_mode=False)
    path_output = "\n".join(
        value for value in (result.get("stdout", ""), result.get("stderr", "")) if value
    )
    installed_paths = [
        line.split("package:", 1)[1].strip()
        for line in path_output.splitlines()
        if line.strip().startswith("package:")
    ]
    if not result["ok"] or not installed_paths:
        raise CommandFailure("package is not installed: " + package, code=4, details=result)
    dumpsys = run_privileged(["dumpsys", "package", package], test_mode=False)
    text = "\n".join(
        value for value in (dumpsys.get("stdout", ""), dumpsys.get("stderr", "")) if value
    )
    version = None
    version_code = None
    version_match = re.search(r"versionName=([^\s]+)", text)
    code_match = re.search(r"versionCode=(\d+)", text)
    if version_match:
        version = version_match.group(1)
    if code_match:
        version_code = int(code_match.group(1))
    permissions = sorted(set(re.findall(r"requested permissions:\s*(.*?)(?:\n\s*install permissions:|\n\s*User )", text, re.S)[0].split())) if re.search(r"requested permissions:\s*(.*?)(?:\n\s*install permissions:|\n\s*User )", text, re.S) else []
    flags_match = re.search(r"pkgFlags=([^\n]+)", text)
    launch_match = re.search(r"(?:android\.intent\.action\.MAIN|android\.intent\.category\.LAUNCHER).*?([A-Za-z][A-Za-z0-9_.$]+/[A-Za-z][A-Za-z0-9_.$]+)", text, re.S)
    signer_match = re.search(r"(?:signatures|signingDetails).*?(?:sha256|SHA-256)[=: ]+([0-9A-Fa-f:]{32,})", text, re.S)
    signer = signer_match.group(1).replace(":", "").lower() if signer_match else None
    signature_source = "dumpsys-package" if signer else None
    installed_path = installed_paths[0]
    if not signer and installed_path and shutil.which("apksigner"):
        signature = run_process(
            [shutil.which("apksigner"), "verify", "--print-certs", installed_path],
            timeout=45,
        )
        digest = re.search(
            r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)",
            signature.get("stdout", ""),
        )
        if signature.get("ok") and digest:
            signer = digest.group(1).replace(":", "").lower()
            signature_source = "apksigner-installed-path"
    if expected_version and version != expected_version:
        raise CommandFailure(
            "installed package version mismatch",
            code=6,
            details={"expectedVersion": expected_version, "actualVersion": version},
        )
    enabled_match = re.search(r"\benabled=(\d+)\b", text)
    enabled_state = int(enabled_match.group(1)) if enabled_match else 0
    return {
        "package": package,
        "version": version,
        "versionCode": version_code,
        "installed": True,
        "enabled": enabled_state in {0, 1},
        "path": installed_path,
        "permissions": permissions,
        "flags": flags_match.group(1).strip() if flags_match else None,
        "launchActivity": launch_match.group(1) if launch_match else None,
        "signer": signer,
        "signatureVerified": bool(signer),
        "signerReadbackSource": signature_source,
        "signerReadbackAvailable": bool(signer),
        "signerReadbackReason": None if signer else "installed-signer-digest-unavailable",
        "raw": text[:12000],
    }


def artifact_identity(inspection):
    """Return comparable identity fields for a single APK or split set."""
    if not isinstance(inspection, dict):
        return {}
    if inspection.get("type") == "split-apk-set":
        artifacts = [
            item for item in inspection.get("artifacts", [])
            if isinstance(item, dict) and item.get("available")
        ]
        packages = sorted({str(item.get("package")) for item in artifacts if item.get("package")})
        versions = [item for item in artifacts if item.get("version") is not None]
        version_codes = [item for item in artifacts if item.get("versionCode") is not None]
        signers = sorted({str(item.get("signer")) for item in artifacts if item.get("signer")})
        base = next(
            (item for item in artifacts if pathlib.Path(str(item.get("path", ""))).name.lower() == "base.apk"),
            artifacts[0] if artifacts else {},
        )
        return {
            "package": inspection.get("package") or (packages[0] if len(packages) == 1 else None),
            "version": inspection.get("version") or base.get("version"),
            "versionCode": inspection.get("versionCode") if inspection.get("versionCode") is not None else base.get("versionCode"),
            "signer": inspection.get("signer") or (signers[0] if len(signers) == 1 else None),
            "available": bool(artifacts),
            "versionConsistent": len({str(item.get("version")) for item in versions}) <= 1,
            "versionCodeConsistent": len({str(item.get("versionCode")) for item in version_codes}) <= 1,
        }
    return {
        "package": inspection.get("package"),
        "version": inspection.get("version"),
        "versionCode": inspection.get("versionCode"),
        "signer": inspection.get("signer"),
        "available": bool(inspection.get("available")),
        "versionConsistent": True,
        "versionCodeConsistent": True,
    }


def verify_installed_artifact(artifact_inspection, package, context):
    """Bind package-manager readback to the artifact identity without trusting exit codes."""
    identity = artifact_identity(artifact_inspection)
    package = str(package or identity.get("package") or "").strip()
    if not package:
        return {
            "verified": False,
            "installed": False,
            "errorCode": "artifact_package_unavailable",
            "reason": "artifact metadata did not expose a package identity",
            "artifactPackageReadback": {"verified": False, "expected": None, "actual": None},
            "artifactVersionReadback": {"verified": False},
            "artifactSignerReadback": {"verified": False, "reason": "package-identity-unavailable"},
        }
    inspection_context = dict(context)
    inspection_context.pop("expected_version", None)
    try:
        installed = package_inspection(package, inspection_context)
    except CommandFailure as exc:
        return {
            "verified": False,
            "installed": False,
            "package": package,
            "errorCode": exc.details.get("errorCode", "package_readback_failed"),
            "reason": str(exc),
            "details": dict(exc.details),
            "artifactPackageReadback": {"verified": False, "expected": package, "actual": None},
            "artifactVersionReadback": {"verified": False},
            "artifactSignerReadback": {"verified": False, "reason": "package-readback-failed"},
        }
    package_match = installed.get("package") == package
    expected_version = identity.get("version")
    expected_version_code = identity.get("versionCode")
    version_match = expected_version is None or installed.get("version") == expected_version
    version_code_match = expected_version_code is None or installed.get("versionCode") == expected_version_code
    expected_signer = str(identity.get("signer") or "").replace(":", "").lower()
    actual_signer = str(installed.get("signer") or "").replace(":", "").lower()
    if expected_signer:
        signer_match = bool(actual_signer) and actual_signer == expected_signer
        signer_reason = None if actual_signer else "installed-signer-digest-unavailable"
    else:
        signer_match = True
        signer_reason = "artifact-signer-unavailable"
    verified = bool(
        installed.get("installed")
        and package_match
        and version_match
        and version_code_match
        and signer_match
        and identity.get("versionConsistent", True)
        and identity.get("versionCodeConsistent", True)
    )
    error_code = None
    if not package_match:
        error_code = "artifact_package_readback_mismatch"
    elif not version_match or not version_code_match:
        error_code = "artifact_version_readback_mismatch"
    elif not signer_match:
        error_code = "artifact_signer_readback_unavailable" if not actual_signer else "artifact_signer_readback_mismatch"
    elif not identity.get("versionConsistent", True) or not identity.get("versionCodeConsistent", True):
        error_code = "artifact_split_version_inconsistent"
    return {
        "verified": verified,
        "installed": bool(installed.get("installed")),
        "package": package,
        "version": installed.get("version"),
        "versionCode": installed.get("versionCode"),
        "signer": installed.get("signer"),
        "errorCode": error_code,
        "artifactPackageReadback": {
            "type": "package-manager-identity",
            "verified": package_match,
            "expected": package,
            "actual": installed.get("package"),
        },
        "artifactVersionReadback": {
            "type": "package-manager-version",
            "verified": version_match and version_code_match,
            "expectedVersion": expected_version,
            "actualVersion": installed.get("version"),
            "expectedVersionCode": expected_version_code,
            "actualVersionCode": installed.get("versionCode"),
        },
        "artifactSignerReadback": {
            "type": "package-manager-signer",
            "verified": signer_match,
            "expected": expected_signer or None,
            "actual": actual_signer or None,
            "available": bool(actual_signer),
            "reason": signer_reason,
        },
        "primaryEvidence": {"type": "pm-path-and-package-readback", "verified": bool(installed.get("installed")), "path": installed.get("path")},
        "independentEvidence": {"type": "dumpsys-package-readback", "verified": package_match and version_match and version_code_match, "package": installed.get("package"), "version": installed.get("version"), "versionCode": installed.get("versionCode")},
        "packageVerification": installed,
    }


def finalize_install_verification(target, result, artifact_inspection, context):
    """Persist a truthful install state and attach artifact-to-package evidence."""
    inspection = result.get("artifactInspection") or artifact_inspection
    if inspection:
        result["artifactInspection"] = inspection
    identity = artifact_identity(inspection)
    package = str(context.get("expected_package") or identity.get("package") or "").strip()
    if package:
        verification = verify_installed_artifact(inspection, package, context)
        result["packageVerification"] = verification
        result["verified"] = bool(verification.get("verified"))
        installation_id = result.get("installationId")
        if installation_id:
            write_installation_state(
                context["root"],
                installation_id,
                "verified" if verification.get("verified") else "installed_unverified",
                packageVerification=verification,
                verified=bool(verification.get("verified")),
                verificationRequired=True,
            )
    elif result.get("installationId"):
        result["verified"] = False
        result["verificationRequired"] = True
        result["verificationErrorCode"] = "artifact_package_unavailable"
        write_installation_state(
            context["root"],
            result["installationId"],
            "installed_unverified",
            verified=False,
            verificationRequired=True,
            reason="artifact-package-identity-unavailable",
        )
    return result


def run_process(arguments, timeout=120, input_text=None, env=None):
    try:
        completed = subprocess.run(
            arguments,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandFailure(
            "command timed out",
            code=124,
            details={"stdout": exc.stdout or "", "stderr": exc.stderr or ""},
        )
    except FileNotFoundError:
        raise CommandFailure("executable not found: " + str(arguments[0]), code=127)
    return {
        "ok": completed.returncode == 0,
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "arguments": list(arguments),
    }


def write_receipt(root, command, args, started, code, result):
    finished = utc_now()
    receipt = {
        "id": uuid.uuid4().hex,
        "runtimeVersion": VERSION,
        "command": command,
        "arguments": list(args),
        "startedAt": started.isoformat().replace("+00:00", "Z"),
        "finishedAt": finished.isoformat().replace("+00:00", "Z"),
        "durationMs": int((finished - started).total_seconds() * 1000),
        "exitCode": code,
        "result": result,
    }
    atomic_write_json(root / "audit" / (receipt["id"] + ".json"), receipt)
    atomic_write_json(root / "task-history" / "latest.json", receipt)
    return receipt


def rank_sources(sources):
    ranked = []
    for source in sources:
        item = dict(source)
        url = str(item.get("url", ""))
        host = urllib.parse.urlparse(url).hostname or ""
        score = int(item.get("providerScore", 0) or 0)
        reasons = list(item.get("providerReasons", []))
        if url.startswith("https://"):
            score += 30
            reasons.append("https")
        if item.get("sha256"):
            score += 30
            reasons.append("checksum")
        if item.get("signature"):
            score += 20
            reasons.append("signature")
        if host in {
            "github.com",
            "objects.githubusercontent.com",
            "f-droid.org",
            "play.google.com",
        }:
            score += 15
            reasons.append("recognized-distributor")
        if "/releases/" in url or "/download/" in url:
            score += 5
            reasons.append("release-artifact")
        if url.startswith("http://"):
            score -= 25
            reasons.append("plaintext-http")
        item["score"] = score
        item["reasons"] = reasons
        ranked.append(item)
    return sorted(ranked, key=lambda entry: (-entry["score"], entry.get("url", "")))


def sign_gateway_request(secret, timestamp, nonce, body):
    canonical = timestamp + "\n" + nonce + "\n" + body
    secret_bytes = secret.encode("utf-8")
    try:
        decoded = base64.b64decode(secret, validate=True)
        if len(decoded) >= 32:
            secret_bytes = decoded
    except (ValueError, TypeError):
        pass
    return hmac.new(
        secret_bytes, canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def validate_runtime(candidate):
    candidate = pathlib.Path(candidate)
    manifest_path = candidate / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not manifest.get("version"):
        raise ValueError("runtime manifest lacks version")
    payload = candidate / "codex_runtime.py"
    expected = manifest.get("sha256")
    if expected and (not payload.exists() or sha256_file(payload) != expected):
        raise ValueError("runtime payload checksum mismatch")
    return manifest


def activate_runtime(root, candidate):
    root = pathlib.Path(root)
    candidate = pathlib.Path(candidate).resolve()
    validate_runtime(candidate)
    root.mkdir(parents=True, exist_ok=True)
    current = root / "current"
    previous = root / "previous"
    old_target = current.resolve() if current.exists() or current.is_symlink() else None
    staged = root / (".current-" + uuid.uuid4().hex)

    def link_or_copy(source, destination):
        try:
            os.symlink(source, destination, target_is_directory=True)
            return "symlink"
        except OSError:
            shutil.copytree(source, destination)
            return "copy"

    def remove_path(path):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)

    try:
        link_or_copy(candidate, staged)
        if old_target:
            remove_path(previous)
            link_or_copy(old_target, previous)
        remove_path(current)
        os.replace(staged, current)
    finally:
        if staged.exists() or staged.is_symlink():
            remove_path(staged)
    return candidate


def allowed_delete_target(root, target):
    target = canonical_path(target)
    root = canonical_path(root)
    anchor = pathlib.Path(target.anchor)
    if target == anchor or target == root:
        return False
    home = canonical_path(pathlib.Path.home())
    shared_roots = [
        canonical_path("/sdcard"),
        canonical_path("/storage/emulated/0"),
    ]
    allowed_roots = [root, home] + shared_roots
    for allowed in allowed_roots:
        try:
            target.relative_to(allowed)
            return target != allowed
        except ValueError:
            continue
    return False


def quarantine_path(root, target):
    stamp = utc_now().strftime("%Y%m%dT%H%M%S")
    return root / "quarantine" / (stamp + "-" + uuid.uuid4().hex + "-" + target.name)


def delete_to_quarantine(root, target):
    target = canonical_path(target)
    if not allowed_delete_target(root, target):
        raise CommandFailure("refusing dangerous or out-of-scope delete", code=3)
    if not target.exists() and not target.is_symlink():
        raise CommandFailure("delete target does not exist", code=4)
    destination = quarantine_path(root, target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(destination))
    undo_id = uuid.uuid4().hex
    record = {
        "id": undo_id,
        "action": "restore-path",
        "originalPath": str(target),
        "quarantinePath": str(destination),
        "createdAt": iso_now(),
    }
    atomic_write_json(root / "undo" / (undo_id + ".json"), record)
    return command_result(
        undoId=undo_id,
        deleted=str(target),
        quarantinePath=str(destination),
    )


def restore_undo(root, undo_id):
    record_path = root / "undo" / (undo_id + ".json")
    record = load_json(record_path, None)
    if not record:
        raise CommandFailure("undo record not found", code=4)
    source = pathlib.Path(record["quarantinePath"])
    destination = pathlib.Path(record["originalPath"])
    if not source.exists():
        raise CommandFailure("quarantined content no longer exists", code=4)
    if destination.exists():
        raise CommandFailure("restore destination already exists", code=5)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    record["restoredAt"] = iso_now()
    atomic_write_json(record_path, record)
    return command_result(restored=str(destination), undoId=undo_id)


def parse_options(args):
    positional = []
    options = {}
    index = 0
    while index < len(args):
        value = args[index]
        if value == "--":
            positional.extend(args[index + 1 :])
            break
        if value.startswith("--"):
            key = value[2:]
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                options[key] = args[index + 1]
                index += 2
            else:
                options[key] = True
                index += 1
        else:
            positional.append(value)
            index += 1
    return positional, options


def handle_route(args, context):
    text = " ".join(args).lower()
    routes = (
        (("download", "checksum", "fetch artifact"), "codex-download"),
        (("search", "find", "look up"), "codex-search"),
        (("install", "apk", "package"), "codex-install"),
        (("delete", "remove file"), "codex-delete"),
        (("remember", "memory"), "codex-memory"),
        (("schedule", "hourly", "daily"), "codex-schedule"),
        (("screenshot", "tap", "swipe", "android"), "codex-android"),
        (("windows", "powershell", "pc"), "codex-win"),
    )
    for terms, command in routes:
        if any(term in text for term in terms):
            return command_result(command=command, confidence=0.8, input=" ".join(args))
    return command_result(command="codex-exec", confidence=0.35, input=" ".join(args))


def handle_exec(args, context):
    positional, options = parse_options(args)
    if not positional:
        raise CommandFailure("usage: codex-exec [--retries N] [--timeout S] -- command")
    retries = int(options.get("retries", 0))
    timeout = int(options.get("timeout", 120))
    last = None
    for attempt in range(retries + 1):
        last = run_process(positional, timeout=timeout)
        last["attempt"] = attempt + 1
        if last["ok"]:
            return last
        if attempt < retries:
            time.sleep(min(2 ** attempt, 5))
    raise CommandFailure("command failed", code=last["exitCode"], details=last)


def safe_response_headers(headers):
    """Return useful response metadata without persisting credential-bearing headers."""
    blocked = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).lower() not in blocked
    }


def fetch_http(url, timeout=30, retries=3, maximum=2 * 1024 * 1024):
    """Fetch bounded content with retry metadata while preserving redirect results."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        source = pathlib.Path(urllib.request.url2pathname(parsed.path))
        body = source.read_bytes()[:maximum]
        return {
            "body": body,
            "status": 200,
            "headers": {},
            "finalUrl": url,
            "attempts": 1,
            "contentType": mimetypes.guess_type(str(source))[0] or "",
        }
    last_error = None
    for attempt in range(1, max(1, retries) + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 CodexAppCapabilityRuntime/" + VERSION},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(maximum)
                headers = safe_response_headers(response.headers)
                return {
                    "body": body,
                    "status": int(getattr(response, "status", 200) or 200),
                    "headers": headers,
                    "finalUrl": response.geturl(),
                    "attempts": attempt,
                    "contentType": response.headers.get("Content-Type", ""),
                }
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise CommandFailure(
                    "HTTP fetch failed",
                    code=8,
                    details={
                        "errorCode": "http_status",
                        "status": int(exc.code),
                        "url": url,
                    },
                ) from exc
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        if attempt < max(1, retries):
            time.sleep(min(2 ** (attempt - 1), 8))
    raise CommandFailure(
        "HTTP fetch failed after retries",
        code=8,
        details={
            "errorCode": "http_retry_exhausted",
            "url": url,
            "attempts": max(1, retries),
            "reason": str(last_error),
        },
    )


class _LinkMetadataParser(HTMLParser):
    """Extract bounded visible links and JSON metadata without executing page scripts."""

    def __init__(self, base_url, limit=100):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.limit = max(1, min(int(limit), 500))
        self.links = []
        self._anchor = None
        self._script = None
        self.json_blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "a" and len(self.links) < self.limit:
            href = str(attrs.get("href") or "").strip()
            if href:
                self._anchor = {
                    "url": urllib.parse.urljoin(self.base_url, href),
                    "text": "",
                    "download": bool(attrs.get("download") is not None),
                    "rel": str(attrs.get("rel") or ""),
                }
        if tag == "script" and str(attrs.get("type") or "").lower() in {
            "application/json",
            "application/ld+json",
        }:
            self._script = []

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["text"] += str(data)
        if self._script is not None:
            self._script.append(str(data))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = re.sub(r"\s+", " ", self._anchor["text"]).strip()[:500]
            self.links.append(self._anchor)
            self._anchor = None
        if tag == "script" and self._script is not None:
            content = "".join(self._script).strip()
            if content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, (dict, list)):
                        self.json_blocks.append(parsed)
                except json.JSONDecodeError:
                    pass
            self._script = None


def extract_html_metadata(body, base_url, limit=100):
    parser = _LinkMetadataParser(base_url, limit=limit)
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        # Malformed HTML is still useful as text; return the parsed prefix safely.
        pass
    keywords = ("download", "apk", "premium", "pro", "release", "install")
    candidates = [
        link
        for link in parser.links
        if link["download"]
        or any(word in (link["url"] + " " + link["text"]).lower() for word in keywords)
    ]
    return {
        "links": parser.links,
        "downloadCandidates": candidates[: min(len(candidates), 100)],
        "jsonMetadata": parser.json_blocks[:20],
    }


def parse_search_provider_results(body, count, provider):
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    links = []
    if provider in {"duckduckgo", "jina-duckduckgo"}:
        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
        )
        for href, title in pattern.findall(text):
            title = re.sub(r"<[^>]+>", "", title)
            parsed = urllib.parse.urlparse(html.unescape(href))
            query_values = urllib.parse.parse_qs(parsed.query)
            actual = query_values.get("uddg", [html.unescape(href)])[0]
            links.append({"title": html.unescape(title).strip(), "url": actual})
            if len(links) >= count:
                break
    elif provider == "google":
        for href in re.findall(r'href="/url\?q=([^&"]+)', text, flags=re.I):
            actual = urllib.parse.unquote(html.unescape(href))
            if not actual.startswith(("http://", "https://")):
                continue
            if any(item.get("url") == actual for item in links):
                continue
            links.append({"title": "Google result", "url": actual})
            if len(links) >= count:
                break
    if not links and provider == "jina-duckduckgo":
        for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text):
            links.append({"title": html.unescape(title).strip(), "url": url})
            if len(links) >= count:
                break
    return links[:count]


def search_web_response(query, count, timeout=25, retries=3, include_raw=False):
    encoded = urllib.parse.quote_plus(query)
    providers = (
        ("duckduckgo", "https://html.duckduckgo.com/html/?q=" + encoded),
        ("jina-duckduckgo", "https://r.jina.ai/http://duckduckgo.com/html/?q=" + encoded),
        ("google", "https://www.google.com/search?q=" + encoded),
    )
    provider_attempts = []
    last_error = None
    for provider, url in providers:
        try:
            response = fetch_http(
                url,
                timeout=timeout,
                retries=retries,
                maximum=2 * 1024 * 1024,
            )
            body = response["body"]
            links = parse_search_provider_results(body, count, provider)
            provider_attempts.append(
                {
                    "provider": provider,
                    "url": url,
                    "status": response.get("status"),
                    "attempts": response.get("attempts", 1),
                    "resultCount": len(links),
                }
            )
            if not links:
                continue
            result = dict(response)
            result.pop("body", None)
            result["provider"] = provider
            result["providerAttempts"] = provider_attempts
            result["results"] = links
            if include_raw:
                result["rawHtml"] = body[:512 * 1024]
            return result
        except CommandFailure as exc:
            last_error = exc
            provider_attempts.append(
                {
                    "provider": provider,
                    "url": url,
                    "status": exc.details.get("status"),
                    "attempts": exc.details.get("attempts", 1),
                    "errorCode": exc.details.get("errorCode", "search_provider_failed"),
                }
            )
    if last_error:
        last_error.details["providerAttempts"] = provider_attempts
        raise last_error
    return {
        "status": 200,
        "headers": {},
        "finalUrl": "",
        "attempts": sum(item.get("attempts", 1) for item in provider_attempts),
        "provider": provider_attempts[-1]["provider"] if provider_attempts else None,
        "providerAttempts": provider_attempts,
        "results": [],
    }


def search_web(query, count):
    """Compatibility wrapper retained for callers that expect only result links."""
    return search_web_response(query, count)["results"]


def split_filter_values(value):
    return [item.strip().lower() for item in re.split(r"[,\n]", str(value or "")) if item.strip()]


def search_result_matches(result, domains=None, terms=None):
    parsed = urllib.parse.urlparse(str(result.get("url") or ""))
    host = (parsed.hostname or "").lower().rstrip(".")
    if domains and not any(host == domain or host.endswith("." + domain) for domain in domains):
        return False
    haystack = (str(result.get("title") or "") + " " + str(result.get("url") or "")).lower()
    return not terms or all(term in haystack for term in terms)


def handle_search(args, context):
    positional, options = parse_options(args)
    query = " ".join(positional).strip()
    if not query:
        raise CommandFailure("usage: codex-search [--count N] <query>", code=2)
    count = max(1, min(int(options.get("count", 8)), 25))
    domains = split_filter_values(options.get("domain"))
    terms = split_filter_values(options.get("contains") or options.get("keyword"))
    effective_query = query
    if domains:
        effective_query += " " + " ".join("site:" + domain for domain in domains)
    if context["test_mode"]:
        result_url = "https://" + (domains[0] if domains else "example.test") + "/?q=" + urllib.parse.quote(query)
        response = {
            "status": 200,
            "headers": {},
            "finalUrl": "https://example.test/",
            "attempts": 1,
            "results": [{"title": query, "url": result_url}],
        }
    else:
        response = search_web_response(
            effective_query,
            max(count, min(count * 3, 25)),
            timeout=max(1, min(int(options.get("timeout", 25)), 120)),
            retries=max(1, min(int(options.get("retries", 3)), 8)),
            include_raw=bool(options.get("raw")),
        )
    results = [
        dict(item, rank=index + 1)
        for index, item in enumerate(
            item for item in response.get("results", [])
            if search_result_matches(item, domains, terms)
        )
    ][:count]
    return command_result(
        query=query,
        effectiveQuery=effective_query,
        filters={"domains": domains, "contains": terms},
        results=results,
        count=len(results),
        status=response.get("status"),
        headers=response.get("headers", {}),
        finalUrl=response.get("finalUrl"),
        attempts=response.get("attempts", 1),
        provider=response.get("provider"),
        providerAttempts=response.get("providerAttempts", []),
        **({"rawHtml": response.get("rawHtml", "")} if options.get("raw") else {}),
    )


def handle_source(args, context):
    positional, options = parse_options(args)
    if positional and positional[0].lower() == "github":
        if len(positional) < 2:
            raise CommandFailure(
                "usage: codex-source github <owner/repository> [--asset-regex pattern] [--abi abi]",
                code=2,
            )
        return resolve_github_release_sources(
            positional[1],
            asset_regex=options.get("asset-regex"),
            abi=options.get("abi"),
            timeout=options.get("timeout", 30),
            retries=options.get("retries", 3),
        )
    sources = []
    for value in args:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                sources.append(parsed)
            elif isinstance(parsed, list):
                sources.extend(parsed)
        except json.JSONDecodeError:
            sources.append({"url": value})
    if not sources:
        raise CommandFailure("usage: codex-source <url-or-json> ...", code=2)
    return command_result(sources=rank_sources(sources))


GITHUB_REPOSITORY_PATTERN = re.compile(
    r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.I,
)


def normalize_github_repository(value):
    match = GITHUB_REPOSITORY_PATTERN.match(str(value or "").strip())
    if not match:
        raise CommandFailure(
            "GitHub repository must be owner/repository or a github.com repository URL",
            code=2,
            details={"errorCode": "github_repository_invalid"},
        )
    return match.group(1) + "/" + match.group(2)


def github_asset_digest(asset):
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:") and re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return digest.split(":", 1)[1]
    return None


def score_github_asset(asset, abi=None):
    name = str(asset.get("name") or "")
    lowered = name.lower()
    score = 0
    reasons = []
    if lowered.endswith(".apk"):
        score += 80
        reasons.append("apk")
    elif lowered.endswith((".apks", ".xapk")):
        score += 45
        reasons.append("android-package-bundle")
    elif lowered.endswith((".zip", ".tar.gz", ".tgz")):
        score -= 30
        reasons.append("archive-not-direct-apk")
    if any(term in lowered for term in ("source", "sources", "symbols", "mapping", "checksum")):
        score -= 80
        reasons.append("non-install-asset")
    normalized_abi = re.sub(r"[^a-z0-9]", "", str(abi or "").lower())
    normalized_name = re.sub(r"[^a-z0-9]", "", lowered)
    if normalized_abi and normalized_abi in normalized_name:
        score += 35
        reasons.append("requested-abi")
    elif normalized_abi and any(term in lowered for term in ("universal", "noarch", "all")):
        score += 15
        reasons.append("universal-abi")
    if "fdroid" in lowered:
        score -= 5
        reasons.append("alternate-distribution-build")
    if "release" in lowered or "stable" in lowered:
        score += 5
        reasons.append("release-name")
    if github_asset_digest(asset):
        score += 35
        reasons.append("upstream-sha256")
    return score, reasons


def github_asset_matches_abi(asset_name, abi=None):
    requested = re.sub(r"[^a-z0-9]", "", str(abi or "").lower())
    if not requested:
        return True
    lowered = str(asset_name or "").lower()
    patterns = (
        ("arm64v8a", r"(?<![a-z0-9])(?:arm64(?:[-_]?v8a)?|aarch64)(?![a-z0-9])"),
        ("armeabiv7a", r"armeabi[-_]?v7a"),
        ("x8664", r"x86[-_]?64"),
        ("armeabi", r"armeabi(?![-_]?v7a)"),
        ("x86", r"(?<![a-z0-9])x86(?![-_]?64)"),
    )
    detected = {name for name, pattern in patterns if re.search(pattern, lowered)}
    return not detected or requested in detected


def resolve_github_release_sources(
    repository,
    asset_regex=None,
    abi=None,
    timeout=30,
    retries=3,
):
    repository = normalize_github_repository(repository)
    owner, repo = repository.split("/", 1)
    api_url = "https://api.github.com/repos/{}/{}/releases/latest".format(
        urllib.parse.quote(owner, safe=""),
        urllib.parse.quote(repo, safe=""),
    )
    try:
        timeout = max(1, min(int(timeout), 120))
        retries = max(1, min(int(retries), 8))
    except (TypeError, ValueError):
        raise CommandFailure("timeout and retries must be integers", code=2)
    try:
        matcher = re.compile(str(asset_regex), re.I) if asset_regex else None
    except re.error as exc:
        raise CommandFailure(
            "asset regex is invalid",
            code=2,
            details={"errorCode": "github_asset_regex_invalid", "reason": str(exc)},
        ) from exc
    response = fetch_http(api_url, timeout=timeout, retries=retries, maximum=2 * 1024 * 1024)
    try:
        release = json.loads(response["body"].decode("utf-8", "replace"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandFailure(
            "GitHub latest release response is not valid JSON",
            code=6,
            details={"errorCode": "github_release_json_invalid", "apiUrl": api_url},
        ) from exc
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise CommandFailure(
            "GitHub latest stable release is unavailable",
            code=4,
            details={"errorCode": "github_release_unavailable", "apiUrl": api_url},
        )
    sources = []
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("state") not in {None, "uploaded"}:
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not name or not url.startswith("https://github.com/"):
            continue
        if matcher and not matcher.search(name):
            continue
        if not github_asset_matches_abi(name, abi=abi):
            continue
        provider_score, provider_reasons = score_github_asset(asset, abi=abi)
        source = {
            "url": url,
            "title": name,
            "assetName": name,
            "sourceType": "github-release-asset",
            "provider": "github-release",
            "repository": repository,
            "tag": release.get("tag_name"),
            "publishedAt": release.get("published_at"),
            "contentType": asset.get("content_type"),
            "bytes": asset.get("size"),
            "downloadCount": asset.get("download_count"),
            "providerScore": provider_score,
            "providerReasons": provider_reasons,
        }
        digest = github_asset_digest(asset)
        if digest:
            source["sha256"] = digest
            source["checksumSource"] = "upstream-release-digest"
        sources.append(source)
    ranked = rank_sources(sources)
    if not ranked:
        raise CommandFailure(
            "GitHub release has no matching downloadable assets",
            code=4,
            details={
                "errorCode": "github_release_assets_empty",
                "repository": repository,
                "tag": release.get("tag_name"),
                "assetRegex": asset_regex,
                "abi": abi,
            },
        )
    return command_result(
        provider="github-release",
        repository=repository,
        apiUrl=api_url,
        release={
            "tag": release.get("tag_name"),
            "name": release.get("name"),
            "url": release.get("html_url"),
            "publishedAt": release.get("published_at"),
            "createdAt": release.get("created_at"),
            "draft": False,
            "prerelease": False,
        },
        filters={"assetRegex": asset_regex, "abi": abi},
        response={
            "status": response.get("status"),
            "finalUrl": response.get("finalUrl", api_url),
            "attempts": response.get("attempts", 1),
            "headers": response.get("headers", {}),
        },
        sources=ranked,
        count=len(ranked),
    )


def strip_html(body):
    body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", body)
    body = re.sub(r"(?s)<[^>]+>", "\n", body)
    lines = [html.unescape(line).strip() for line in body.splitlines()]
    return "\n".join(line for line in lines if line)


def handle_fetch(args, context):
    positional, options = parse_options(args)
    if not positional:
        raise CommandFailure("usage: codex-fetch [--max N] <url>", code=2)
    maximum = max(1, min(int(options.get("max", 20000)), 2 * 1024 * 1024))
    response = fetch_http(
        positional[0],
        timeout=max(1, min(int(options.get("timeout", 30)), 120)),
        retries=max(1, min(int(options.get("retries", 3)), 8)),
        maximum=maximum,
    )
    content_type = response.get("contentType", "")
    body = response["body"]
    text = body.decode("utf-8", "replace")
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        text = strip_html(text)
    metadata = extract_html_metadata(body.decode("utf-8", "replace"), response.get("finalUrl", positional[0]))
    return command_result(
        url=positional[0],
        finalUrl=response.get("finalUrl", positional[0]),
        status=response.get("status"),
        headers=response.get("headers", {}),
        attempts=response.get("attempts", 1),
        bytes=len(body),
        contentType=content_type,
        text=text[:maximum],
        links=metadata["links"],
        downloadCandidates=metadata["downloadCandidates"],
        jsonMetadata=metadata["jsonMetadata"],
    )


DOWNLOAD_MAX_BYTES = 8 * 1024 * 1024 * 1024


def _copy_stream_bounded(source, output, existing_bytes=0, maximum=DOWNLOAD_MAX_BYTES):
    written = int(existing_bytes)
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        if written + len(chunk) > maximum:
            raise CommandFailure(
                "download exceeds the configured size limit",
                code=7,
                details={
                    "errorCode": "download_size_limit",
                    "maximumBytes": maximum,
                    "bytesBeforeLimit": written,
                },
            )
        output.write(chunk)
        written += len(chunk)
    return written


def copy_url_to_part(url, part, timeout=600, retries=3, maximum=DOWNLOAD_MAX_BYTES):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        source = pathlib.Path(urllib.request.url2pathname(parsed.path))
        offset = part.stat().st_size if part.exists() else 0
        with open(source, "rb") as input_stream, open(part, "ab" if offset else "wb") as output:
            input_stream.seek(offset)
            total = _copy_stream_bounded(input_stream, output, offset, maximum)
        return {
            "status": 200,
            "resumed": bool(offset),
            "attempt": 1,
            "finalUrl": url,
            "headers": {},
            "contentType": "",
            "contentLength": str(max(0, total - offset)),
            "contentRange": "",
            "etag": "",
            "lastModified": "",
        }
    last_error = None
    for attempt in range(1, max(1, retries) + 1):
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "Mozilla/5.0 CodexAppCapabilityRuntime/" + VERSION}
        if offset:
            headers["Range"] = "bytes={}-".format(offset)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                content_range = response.headers.get("Content-Range", "")
                range_match = re.match(r"^bytes\s+(\d+)-", content_range)
                append = bool(
                    offset
                    and status == 206
                    and range_match
                    and int(range_match.group(1)) == offset
                )
                if offset and status == 206 and not append:
                    raise CommandFailure(
                        "download range response mismatch",
                        code=8,
                        details={"offset": offset, "contentRange": content_range},
                    )
                if status < 200 or status >= 300:
                    raise CommandFailure(
                        "download returned a non-success HTTP status",
                        code=8,
                        details={
                            "errorCode": "download_http_status",
                            "status": status,
                            "finalUrl": response.geturl(),
                            "headers": safe_response_headers(response.headers),
                        },
                    )
                content_length = response.headers.get("Content-Length", "")
                try:
                    declared = int(content_length) if content_length else None
                except ValueError:
                    declared = None
                expected_total = (offset + declared) if append and declared is not None else declared
                if expected_total is not None and expected_total > maximum:
                    raise CommandFailure(
                        "download exceeds the configured size limit",
                        code=7,
                        details={
                            "errorCode": "download_size_limit",
                            "maximumBytes": maximum,
                            "declaredBytes": expected_total,
                        },
                    )
                with open(part, "ab" if append else "wb") as output:
                    _copy_stream_bounded(
                        response,
                        output,
                        offset if append else 0,
                        maximum,
                    )
                return {
                    "status": status,
                    "resumed": append,
                    "attempt": attempt,
                    "finalUrl": response.geturl(),
                    "headers": safe_response_headers(response.headers),
                    "contentType": response.headers.get("Content-Type", ""),
                    "contentLength": response.headers.get("Content-Length", ""),
                    "contentRange": content_range,
                    "etag": response.headers.get("ETag", ""),
                    "lastModified": response.headers.get("Last-Modified", ""),
                }
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(min(2 ** (attempt - 1), 8))
    raise CommandFailure(
        "download failed after retries",
        code=8,
        details={"url": url, "retries": max(1, retries), "error": str(last_error)},
    )


def validate_downloaded_artifact(path, transfer=None, extension=None):
    """Reject obvious error pages and unsafe archives before finalizing a download."""
    path = canonical_path(path)
    extension = str(extension or path.suffix).lower()
    known_archive = extension in {".apk", ".apks", ".xapk", ".zip"}
    if not known_archive:
        return {
            "artifactType": "generic",
            "contentValidated": True,
            "contentType": (transfer or {}).get("contentType", ""),
        }
    with open(path, "rb") as stream:
        header = stream.read(512)
    text_header = header.decode("utf-8", "ignore").lstrip().lower()
    if text_header.startswith(("<!doctype html", "<html", "{\"error", "{\"message")):
        raise CommandFailure(
            "downloaded artifact is an error page, not an archive",
            code=6,
            details={"errorCode": "artifact_content_type_mismatch", "path": str(path)},
        )
    if not zipfile.is_zipfile(path):
        raise CommandFailure(
            "downloaded artifact is not a valid ZIP/APK archive",
            code=6,
            details={"errorCode": "artifact_archive_invalid", "path": str(path)},
        )
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 2048:
            raise CommandFailure(
                "archive contains too many entries",
                code=3,
                details={"errorCode": "archive_entry_limit"},
            )
        total_size = 0
        root = path.parent.resolve()
        for member in members:
            candidate = (root / member.filename).resolve()
            if candidate != root and root not in candidate.parents:
                raise CommandFailure(
                    "archive contains unsafe path",
                    code=3,
                    details={"errorCode": "archive_path_traversal", "entry": member.filename},
                )
            total_size += max(0, int(member.file_size))
            if total_size > 1024 * 1024 * 1024:
                raise CommandFailure(
                    "archive exceeds extraction limit",
                    code=3,
                    details={"errorCode": "archive_size_limit"},
                )
    return {
        "artifactType": "android-package" if extension in {".apk", ".apks", ".xapk"} else "archive",
        "contentValidated": True,
        "contentType": (transfer or {}).get("contentType", ""),
        "archiveEntries": len(members),
    }


def find_download_duplicate(root, digest, maximum_records=4096):
    """Find prior content by digest without trusting a single acquisition URL."""
    digest = str(digest or "").lower()
    if not digest:
        return None
    candidates = []
    for directory in (pathlib.Path(root) / "downloads", pathlib.Path(root) / "acquisitions"):
        candidates.extend(sorted(directory.glob("*.json")))
    for path in candidates[:maximum_records]:
        record = load_json(path, None)
        if not isinstance(record, dict):
            continue
        if str(record.get("sha256", "")).lower() != digest:
            continue
        return {
            "id": record.get("id") or path.stem,
            "recordPath": str(path),
            "output": record.get("output"),
            "url": record.get("url"),
            "sha256": digest,
        }
    return None


def download_artifact(
    root,
    url,
    output=None,
    expected_sha256=None,
    retries=3,
    maximum=DOWNLOAD_MAX_BYTES,
    timeout=600,
):
    parsed = urllib.parse.urlparse(url)
    name = pathlib.Path(parsed.path).name or ("download-" + uuid.uuid4().hex)
    destination = canonical_path(output or (pathlib.Path("/sdcard/Download") / name))
    if destination.exists() and destination.is_symlink():
        raise CommandFailure(
            "download output cannot be a symbolic link",
            code=3,
            details={"errorCode": "download_output_symlink_refused", "path": str(destination)},
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    completed = False
    try:
        transfer = copy_url_to_part(
            url,
            part,
            timeout=timeout,
            retries=retries,
            maximum=maximum,
        )
        digest = sha256_file(part)
        size = part.stat().st_size
        if size <= 0:
            raise CommandFailure("download produced an empty artifact", code=7)
        try:
            validation = validate_downloaded_artifact(part, transfer, destination.suffix)
        except CommandFailure as exc:
            quarantined = quarantine_path(root, destination)
            quarantined.parent.mkdir(parents=True, exist_ok=True)
            if part.exists():
                shutil.move(str(part), str(quarantined))
            exc.details.setdefault("quarantinePath", str(quarantined))
            raise
        if expected_sha256 and not hmac.compare_digest(
            digest.lower(), expected_sha256.lower()
        ):
            quarantined = quarantine_path(root, destination)
            quarantined.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(part), str(quarantined))
            raise CommandFailure(
                "download checksum mismatch",
                code=6,
                details={
                    "ok": False,
                    "expectedSha256": expected_sha256.lower(),
                    "actualSha256": digest,
                    "quarantinePath": str(quarantined),
                },
            )
        os.replace(part, destination)
        completed = True
        result = command_result(
            url=url,
            output=str(destination),
            timeoutSeconds=timeout,
            bytes=size,
            sha256=digest,
            transfer=transfer,
            artifactType=validation["artifactType"],
            contentValidated=validation["contentValidated"],
            provenance={
                "url": url,
                "sha256": digest,
                "bytes": size,
                "contentType": transfer.get("contentType", ""),
                "finalUrl": transfer.get("finalUrl", url),
                "artifactType": validation["artifactType"],
                "contentValidated": validation["contentValidated"],
            },
        )
        duplicate = find_download_duplicate(root, digest)
        if duplicate:
            result["duplicate"] = True
            result["duplicateOf"] = duplicate
        download_id = uuid.uuid4().hex
        provenance = dict(result)
        provenance.update(
            {
                "id": download_id,
                "recordType": "download-provenance",
                "recordedAt": iso_now(),
                "timeoutSeconds": timeout,
            }
        )
        atomic_write_json(root / "downloads" / (download_id + ".json"), provenance)
        result["downloadId"] = download_id
        return result
    except CommandFailure as exc:
        if exc.details.get("errorCode") == "download_size_limit" and part.exists():
            quarantined = quarantine_path(root, destination)
            quarantined.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(part), str(quarantined))
            exc.details.setdefault("quarantinePath", str(quarantined))
        raise
    finally:
        if completed and part.exists():
            part.unlink()


def discard_download_partial(url, output=None):
    parsed = urllib.parse.urlparse(url)
    name = pathlib.Path(parsed.path).name
    if not output and not name:
        return {"removed": False, "reason": "destination-name-unavailable"}
    destination = canonical_path(output or (pathlib.Path("/sdcard/Download") / name))
    part = destination.with_name(destination.name + ".part")
    if not part.exists() and not part.is_symlink():
        return {"removed": False, "path": str(part), "reason": "not-present"}
    if part.is_dir() and not part.is_symlink():
        raise CommandFailure(
            "download partial path is a directory",
            code=3,
            details={"errorCode": "download_partial_directory", "path": str(part)},
        )
    part.unlink()
    return {"removed": True, "path": str(part)}


def handle_download(args, context):
    positional, options = parse_options(args)
    if not positional:
        raise CommandFailure(
            "usage: codex-download <url> [output] [--output path] [--sha256 digest] [--retries N] [--timeout N] [--max-bytes N]",
            code=2,
        )
    if len(positional) > 2:
        raise CommandFailure(
            "codex-download accepts one URL and at most one positional output path",
            code=2,
        )
    try:
        timeout = max(1, min(int(options.get("timeout", 600)), 3600))
    except (TypeError, ValueError):
        raise CommandFailure("timeout must be an integer", code=2)
    return download_artifact(
        context["root"],
        positional[0],
        output=options.get("output") or (positional[1] if len(positional) == 2 else None),
        expected_sha256=options.get("sha256"),
        retries=max(1, min(int(options.get("retries", 3)), 8)),
        maximum=max(1, min(int(options.get("max-bytes", DOWNLOAD_MAX_BYTES)), DOWNLOAD_MAX_BYTES)),
        timeout=timeout,
    )


def collect_acquisition_sources(query, options, context):
    count = max(1, min(int(options.get("count", 8)), 10))
    search_args = ["--count", str(count)]
    for key in ("domain", "contains", "keyword"):
        if options.get(key):
            search_args.extend(["--" + key, str(options[key])])
    search_args.extend(query.split())
    search = handle_search(search_args, context)
    candidates = []
    seen = set()
    for item in search.get("results", []):
        source = dict(item)
        url = str(source.get("url") or "")
        if url and url not in seen:
            source["sourceType"] = "search-result"
            candidates.append(source)
            seen.add(url)
        if context["test_mode"] or not url:
            continue
        try:
            response = fetch_http(url, timeout=10, retries=1, maximum=512 * 1024)
            metadata = extract_html_metadata(
                response["body"].decode("utf-8", "replace"),
                response.get("finalUrl", url),
                limit=50,
            )
        except (CommandFailure, OSError, ValueError):
            continue
        for candidate in metadata.get("downloadCandidates", []):
            candidate = dict(candidate)
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url or candidate_url in seen:
                continue
            candidate["sourceType"] = "page-download-candidate"
            candidate["discoveredFrom"] = url
            candidates.append(candidate)
            seen.add(candidate_url)
    return search, rank_sources(candidates)


def handle_acquire(args, context):
    positional, options = parse_options(args)
    query = str(options.get("query") or "").strip()
    github_repository = str(options.get("github") or "").strip()
    attempts = []
    search = None
    ranked_sources = []
    release_resolution = None
    if github_repository:
        release_resolution = resolve_github_release_sources(
            github_repository,
            asset_regex=options.get("asset-regex"),
            abi=options.get("abi"),
            timeout=options.get("timeout", 30),
            retries=options.get("retries", 3),
        )
        ranked_sources = release_resolution["sources"]
        result = None
        for source in ranked_sources:
            source_url = str(source.get("url") or "")
            try:
                result = download_artifact(
                    context["root"],
                    source_url,
                    output=options.get("output"),
                    expected_sha256=source.get("sha256") or options.get("sha256"),
                    retries=max(1, min(int(options.get("retries", 3)), 8)),
                    maximum=max(
                        1,
                        min(int(options.get("max-bytes", DOWNLOAD_MAX_BYTES)), DOWNLOAD_MAX_BYTES),
                    ),
                    timeout=max(1, min(int(options.get("timeout", 600)), 3600)),
                )
                attempts.append({"url": source_url, "ok": True, "source": source})
                result["selectedSource"] = source
                break
            except CommandFailure as exc:
                partial_reset = discard_download_partial(
                    source_url,
                    output=options.get("output"),
                )
                attempts.append(
                    {
                        "url": source_url,
                        "ok": False,
                        "errorCode": exc.details.get("errorCode", "acquisition_failed"),
                        "message": str(exc),
                        "source": source,
                        "partialReset": partial_reset,
                    }
                )
        if result is None:
            raise CommandFailure(
                "all GitHub release assets failed",
                code=8,
                details={
                    "errorCode": "github_release_assets_exhausted",
                    "repository": github_repository,
                    "release": release_resolution.get("release"),
                    "sources": ranked_sources,
                    "attempts": attempts,
                },
            )
        result["githubRepository"] = release_resolution["repository"]
        result["githubRelease"] = release_resolution["release"]
        result["sourceCandidates"] = ranked_sources
        result["acquisitionAttempts"] = attempts
    elif query:
        search, ranked_sources = collect_acquisition_sources(query, options, context)
        if not ranked_sources:
            raise CommandFailure(
                "acquisition search returned no usable sources",
                code=4,
                details={
                    "errorCode": "acquisition_sources_empty",
                    "query": query,
                    "search": search,
                },
            )
        result = None
        for source in ranked_sources:
            source_url = str(source.get("url") or "")
            try:
                result = download_artifact(
                    context["root"],
                    source_url,
                    output=options.get("output"),
                    expected_sha256=source.get("sha256") or options.get("sha256"),
                    retries=max(1, min(int(options.get("retries", 3)), 8)),
                    maximum=max(
                        1,
                        min(int(options.get("max-bytes", DOWNLOAD_MAX_BYTES)), DOWNLOAD_MAX_BYTES),
                    ),
                    timeout=max(1, min(int(options.get("timeout", 600)), 3600)),
                )
                attempts.append({"url": source_url, "ok": True, "source": source})
                result["selectedSource"] = source
                break
            except CommandFailure as exc:
                attempts.append(
                    {
                        "url": source_url,
                        "ok": False,
                        "errorCode": exc.details.get("errorCode", "acquisition_failed"),
                        "message": str(exc),
                        "source": source,
                    }
                )
        if result is None:
            raise CommandFailure(
                "all acquisition sources failed",
                code=8,
                details={
                    "errorCode": "acquisition_sources_exhausted",
                    "query": query,
                    "search": search,
                    "sources": ranked_sources,
                    "attempts": attempts,
                },
            )
        result["acquisitionQuery"] = query
        result["sourceCandidates"] = ranked_sources
        result["acquisitionAttempts"] = attempts
    else:
        if not positional:
            raise CommandFailure(
                "usage: codex-acquire <url> [--output path], --query <query>, or --github <owner/repository>",
                code=2,
            )
        result = handle_download(args, context)
    acquisition = dict(result)
    acquisition["id"] = uuid.uuid4().hex
    acquisition["acquiredAt"] = iso_now()
    atomic_write_json(
        context["root"] / "acquisitions" / (acquisition["id"] + ".json"),
        acquisition,
    )
    result["acquisitionId"] = acquisition["id"]
    return result


def privilege_candidates(command):
    quoted = subprocess.list2cmdline(command)
    candidates = []
    if shutil.which("su"):
        candidates.append(("root", ["su", "-c", quoted]))
    for rish in (
        pathlib.Path.home() / ".local/bin/rish",
        pathlib.Path("/sdcard/Android/data/moe.shizuku.privileged.api/start.sh"),
    ):
        if rish.exists():
            candidates.append(("shizuku", [str(rish), "-c", quoted]))
    candidates.append(("termux", command))
    return candidates


def run_privileged(command, timeout=180, test_mode=False):
    if test_mode:
        return command_result(
            backend="test", exitCode=0, stdout="", stderr="", arguments=command
        )
    failures = []
    for backend, candidate in privilege_candidates(command):
        result = run_process(candidate, timeout=timeout)
        result["backend"] = backend
        if result["ok"]:
            return result
        failures.append(result)
    raise CommandFailure("all privilege backends failed", details={"attempts": failures})


def write_installation_state(root, installation_id, state, **values):
    record = load_json(root / "installations" / (installation_id + ".json"), {})
    record.update(
        {
            "installationId": installation_id,
            "state": state,
            "updatedAt": iso_now(),
        }
    )
    record.update(values)
    atomic_write_json(root / "installations" / (installation_id + ".json"), record)
    return record


def stage_package_manager_files(paths, context):
    """Copy private Termux artifacts to shell-readable staging and return cleanup state."""
    if context.get("test_mode"):
        return [str(path) for path in paths], {"shared": [], "shell": [], "directories": []}
    staging_id = "codex-install-" + uuid.uuid4().hex
    shared_dir = pathlib.Path("/sdcard/Download") / ("." + staging_id)
    shell_dir = pathlib.Path("/data/local/tmp") / staging_id
    shared_dir.mkdir(parents=True, exist_ok=False)
    run_privileged(["mkdir", "-p", str(shell_dir)], timeout=60, test_mode=False)
    shared_paths = []
    shell_paths = []
    try:
        for index, source in enumerate(paths):
            source = canonical_path(source)
            safe_name = "{:03d}-{}".format(index, source.name)
            shared_path = shared_dir / safe_name
            shell_path = shell_dir / safe_name
            shutil.copy2(str(source), str(shared_path))
            shared_paths.append(shared_path)
            run_privileged(["cp", str(shared_path), str(shell_path)], timeout=120, test_mode=False)
            run_privileged(["chmod", "644", str(shell_path)], timeout=60, test_mode=False)
            shell_paths.append(shell_path)
        return [str(path) for path in shell_paths], {
            "shared": shared_paths,
            "shell": shell_paths,
            "directories": [shared_dir, shell_dir],
        }
    except Exception:
        cleanup_package_manager_staging({
            "shared": shared_paths,
            "shell": shell_paths,
            "directories": [shared_dir, shell_dir],
        })
        raise


def cleanup_package_manager_staging(state):
    for path in state.get("shell", []):
        try:
            run_privileged(["rm", "-f", str(path)], timeout=60, test_mode=False)
        except Exception:
            pass
    directories = state.get("directories", [])
    if len(directories) > 1:
        try:
            run_privileged(["rmdir", str(directories[1])], timeout=60, test_mode=False)
        except Exception:
            pass
    for path in state.get("shared", []):
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass
    if directories:
        try:
            pathlib.Path(directories[0]).rmdir()
        except FileNotFoundError:
            pass


def install_artifact(target, context, replace=True):
    target = canonical_path(target)
    if not target.exists():
        raise CommandFailure("install target does not exist", code=4)
    installation_id = "install-" + uuid.uuid4().hex[:16]
    write_installation_state(
        context["root"],
        installation_id,
        "inspect_existing",
        target=str(target),
        replace=bool(replace),
    )
    extension = target.suffix.lower()
    if extension == ".apk":
        write_installation_state(context["root"], installation_id, "stage_artifact")
        metadata = inspect_apk_metadata(target, context)
        write_installation_state(
            context["root"],
            installation_id,
            "validate_artifact",
            artifactInspection=metadata,
        )
        if metadata.get("available") and metadata.get("package") and not context.get("expected_package"):
            context["expected_package"] = metadata["package"]
        write_installation_state(context["root"], installation_id, "prepare_install")
        write_installation_state(context["root"], installation_id, "install_silent")
        staged_paths, staging_state = stage_package_manager_files([target], context)
        command = ["pm", "install"]
        if replace:
            command.append("-r")
        command.append(staged_paths[0])
        try:
            result = run_privileged(command, test_mode=context["test_mode"])
        except CommandFailure as exc:
            write_installation_state(
                context["root"],
                installation_id,
                "rollback_required",
                errorCode=exc.details.get("errorCode", "install_failed"),
                error=str(exc),
            )
            raise
        finally:
            cleanup_package_manager_staging(staging_state)
        result["artifactInspection"] = metadata
        result["stagedForPackageManager"] = True
        result["stagingCleaned"] = True
        result["installationId"] = installation_id
        write_installation_state(
            context["root"],
            installation_id,
            "readback_package" if result.get("ok") else "rollback_required",
            result=result,
        )
        return result
    if extension in {".apks", ".xapk", ".zip"}:
        unpack = context["root"] / "acquisitions" / ("unpack-" + uuid.uuid4().hex)
        unpack.mkdir(parents=True)
        try:
            with zipfile.ZipFile(target) as archive:
                members = archive.infolist()
                if len(members) > 2048:
                    raise CommandFailure("archive contains too many entries", code=3)
                total_size = 0
                for member in members:
                    member_path = (unpack / member.filename).resolve()
                    if member_path != unpack.resolve() and unpack.resolve() not in member_path.parents:
                        raise CommandFailure("archive contains unsafe path", code=3)
                    total_size += max(0, int(member.file_size))
                    if total_size > 1024 * 1024 * 1024:
                        raise CommandFailure("archive exceeds extraction limit", code=3)
                archive.extractall(unpack)
            apks = sorted(str(path) for path in unpack.rglob("*.apk"))
            if not apks:
                raise CommandFailure("archive contains no APK files", code=5)
            split_metadata = []
            for apk in apks:
                metadata = inspect_apk_metadata(apk, context)
                split_metadata.append({"path": apk, **metadata})
            available_metadata = [item for item in split_metadata if item.get("available")]
            package_names = {
                str(item.get("package"))
                for item in available_metadata
                if item.get("package")
            }
            expected_package = str(context.get("expected_package") or "").strip()
            if expected_package and package_names and package_names != {expected_package}:
                raise CommandFailure(
                    "split APK package identity mismatch",
                    code=6,
                    details={
                        "errorCode": "split_package_name_mismatch",
                        "expectedPackage": expected_package,
                        "packages": sorted(package_names),
                        "artifacts": split_metadata,
                    },
                )
            if len(package_names) > 1:
                raise CommandFailure(
                    "split APKs contain multiple package identities",
                    code=6,
                    details={
                        "errorCode": "split_package_set_mismatch",
                        "packages": sorted(package_names),
                        "artifacts": split_metadata,
                    },
                )
            if len(package_names) == 1 and not context.get("expected_package"):
                context["expected_package"] = sorted(package_names)[0]
            signers = {
                str(item.get("signer"))
                for item in available_metadata
                if item.get("signer")
            }
            if len(signers) > 1:
                raise CommandFailure(
                    "split APK signer identities do not match",
                    code=6,
                    details={
                        "errorCode": "split_signer_mismatch",
                        "signers": sorted(signers),
                        "artifacts": split_metadata,
                    },
                )
            write_installation_state(
                context["root"],
                installation_id,
                "validate_artifact",
                artifactInspection={"type": "split-apk-set", "artifacts": split_metadata},
            )
            write_installation_state(context["root"], installation_id, "install_silent")
            staged_apks, staging_state = stage_package_manager_files(apks, context)
            try:
                result = run_privileged(
                    ["pm", "install-multiple", "-r", *staged_apks],
                    test_mode=context["test_mode"],
                )
            except CommandFailure as exc:
                write_installation_state(
                    context["root"],
                    installation_id,
                    "rollback_required",
                    errorCode=exc.details.get("errorCode", "split_install_failed"),
                    error=str(exc),
                )
                raise
            finally:
                cleanup_package_manager_staging(staging_state)
            result["installationId"] = installation_id
            result["stagedForPackageManager"] = True
            result["stagingCleaned"] = True
            result["artifactInspection"] = {
                "type": "split-apk-set",
                "artifacts": split_metadata,
                "package": sorted(package_names)[0] if package_names else None,
                "signer": sorted(signers)[0] if len(signers) == 1 else None,
                "identityConsistent": len(package_names) <= 1,
                "signerConsistent": len(signers) <= 1,
            }
            write_installation_state(
                context["root"],
                installation_id,
                "readback_package" if result.get("ok") else "rollback_required",
                result=result,
            )
            return result
        finally:
            shutil.rmtree(unpack, ignore_errors=True)
    if extension == ".deb":
        return run_process(["dpkg", "-i", str(target)], timeout=300)
    if extension in {".sh", ".py"}:
        destination = pathlib.Path.home() / ".local/bin" / target.stem
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        destination.chmod(0o700)
        return command_result(installed=str(destination), kind="executable")
    raise CommandFailure("unsupported install artifact type: " + extension, code=3)


def validate_apk_install_options(target, options, context):
    """Apply the same package, signer, and digest preflight to every APK route."""
    artifact_inspection = (
        inspect_apk_metadata(target, context)
        if str(target).lower().endswith(".apk")
        else None
    )
    if options.get("package") and artifact_inspection and artifact_inspection.get("available"):
        if artifact_inspection.get("package") != options["package"]:
            raise CommandFailure(
                "APK package identity mismatch",
                code=6,
                details={
                    "errorCode": "package_name_mismatch",
                    "expectedPackage": options["package"],
                    "actualPackage": artifact_inspection.get("package"),
                    "artifactInspection": artifact_inspection,
                },
            )
    if options.get("signer") and artifact_inspection and artifact_inspection.get("available"):
        actual_signer = str(artifact_inspection.get("signer") or "").replace(":", "").lower()
        expected_signer = str(options["signer"]).replace(":", "").lower()
        if not artifact_inspection.get("signatureVerified") or actual_signer != expected_signer:
            raise CommandFailure(
                "APK signer identity mismatch",
                code=6,
                details={
                    "errorCode": "signer_mismatch",
                    "expectedSigner": expected_signer,
                    "actualSigner": actual_signer,
                    "artifactInspection": artifact_inspection,
                },
            )
    expected_sha256 = options.get("sha256")
    if expected_sha256 and pathlib.Path(target).is_file():
        actual_sha256 = sha256_file(target).lower()
        if actual_sha256 != str(expected_sha256).lower():
            raise CommandFailure(
                "APK checksum mismatch",
                code=6,
                details={
                    "errorCode": "checksum_mismatch",
                    "expectedSha256": str(expected_sha256).lower(),
                    "actualSha256": actual_sha256,
                },
            )
    return artifact_inspection


def handle_install(args, context):
    positional, options = parse_options(args)
    if not positional:
        raise CommandFailure(
            "usage: codex-install <artifact-or-url> [--package name] [--signer sha256] [--sha256 digest] [--retries N]",
            code=2,
        )
    target = positional[0]
    acquired = None
    if urllib.parse.urlparse(target).scheme in {"http", "https", "file"}:
        acquired = download_artifact(
            context["root"],
            target,
            output=options.get("output"),
            expected_sha256=options.get("sha256"),
            retries=max(1, min(int(options.get("retries", 3)), 8)),
        )
        target = acquired["output"]
    context["expected_package"] = options.get("package")
    artifact_inspection = validate_apk_install_options(target, options, context)
    if artifact_inspection and artifact_inspection.get("available") and not context.get("expected_package"):
        context["expected_package"] = artifact_inspection.get("package")
    result = install_artifact(target, context, replace=True)
    result["target"] = str(target)
    if acquired:
        result["acquisition"] = acquired
    return finalize_install_verification(target, result, artifact_inspection, context)


def handle_update(args, context):
    result = handle_install(args, context)
    result["updated"] = result.get("target")
    return result


def handle_delete(args, context):
    if not args:
        raise CommandFailure("usage: codex-delete <path>", code=2)
    return delete_to_quarantine(context["root"], args[0])


def handle_restore(args, context):
    if not args:
        raise CommandFailure("usage: codex-restore <undo-id>", code=2)
    return restore_undo(context["root"], args[0])


def handle_fs(args, context):
    if not args:
        raise CommandFailure("usage: codex-fs <list|stat|hash|copy|move> ...", code=2)
    action = args[0]
    if action == "list":
        target = canonical_path(args[1] if len(args) > 1 else ".")
        return command_result(entries=[entry.name for entry in sorted(target.iterdir())])
    if action == "stat" and len(args) > 1:
        target = canonical_path(args[1])
        stat = target.stat()
        return command_result(
            path=str(target),
            bytes=stat.st_size,
            modifiedAt=dt.datetime.fromtimestamp(
                stat.st_mtime, dt.timezone.utc
            ).isoformat(),
            directory=target.is_dir(),
        )
    if action == "hash" and len(args) > 1:
        target = canonical_path(args[1])
        return command_result(path=str(target), sha256=sha256_file(target))
    if action in {"copy", "move"} and len(args) > 2:
        source = canonical_path(args[1])
        destination = canonical_path(args[2])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if action == "copy":
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        else:
            shutil.move(str(source), str(destination))
        return command_result(action=action, source=str(source), destination=str(destination))
    raise CommandFailure("invalid codex-fs operation", code=2)


def handle_pm(args, context):
    if not args:
        raise CommandFailure("usage: codex-pm <pm arguments>", code=2)
    if args[0] in {"uninstall", "disable-user"}:
        package = next((value for value in reversed(args) if not value.startswith("-")), "")
        if package in PROTECTED_PACKAGES:
            raise CommandFailure("refusing protected package operation: " + package, code=3)
    return run_privileged(["pm", *args], test_mode=context["test_mode"])


def combined_process_output(result):
    return "\n".join(
        value for value in (result.get("stdout", ""), result.get("stderr", "")) if value
    )


def normalize_app_query(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower())).strip()


def android_package_inventory(context):
    result = run_privileged(
        ["pm", "list", "packages"], test_mode=context["test_mode"]
    )
    packages = sorted(
        {
            line.split("package:", 1)[1].strip()
            for line in combined_process_output(result).splitlines()
            if line.strip().startswith("package:")
            and line.split("package:", 1)[1].strip()
        }
    )
    if not context["test_mode"] and not packages:
        raise CommandFailure(
            "Android package inventory returned no packages",
            code=5,
            details={"errorCode": "package_inventory_empty", "result": result},
        )
    return packages, result


def android_launchable_components(context):
    result = run_privileged(
        [
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        ],
        timeout=60,
        test_mode=context["test_mode"],
    )
    components = {}
    for component in re.findall(
        r"^\s*([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)\s*$",
        combined_process_output(result),
        re.MULTILINE,
    ):
        components.setdefault(component.split("/", 1)[0], component)
    return components, result


def android_package_paths(context):
    result = run_privileged(
        ["pm", "list", "packages", "-f"],
        timeout=60,
        test_mode=context["test_mode"],
    )
    paths = {}
    for line in combined_process_output(result).splitlines():
        match = re.match(r"^package:(.+)=([A-Za-z][A-Za-z0-9_.$]+)$", line.strip())
        if match:
            paths[match.group(2)] = match.group(1)
    return paths, result


def android_label_cache_path(context):
    return pathlib.Path(context["root"]) / "android" / "app-label-index.json"


def load_android_label_index(context):
    value = load_json(android_label_cache_path(context), {})
    return value if isinstance(value, dict) and value.get("version") == 1 else {}


def inspect_android_apk_label(package, apk_path, component, inspector):
    result = run_process([inspector, "dump", "badging", apk_path], timeout=30)
    output = result.get("stdout", "")
    label_match = re.search(r"^application-label:'([^']*)'", output, re.MULTILINE)
    if not result.get("ok") or not label_match:
        return package, None
    return package, {
        "package": package,
        "label": html.unescape(label_match.group(1)).strip(),
        "component": component,
        "apkPath": apk_path,
    }


def build_android_label_index(context, refresh=False):
    existing = load_android_label_index(context)
    if existing and not refresh:
        return existing
    if context["test_mode"]:
        entries = {
            package: {
                "package": package,
                "label": label.title(),
                "component": package + "/.MainActivity",
                "apkPath": "/test/" + package + ".apk",
            }
            for label, packages in ANDROID_APP_ALIASES.items()
            for package in packages[:1]
        }
        return {"version": 1, "generatedAt": iso_now(), "entries": entries}
    inspector = shutil.which("aapt") or shutil.which("aapt2")
    if not inspector:
        raise CommandFailure("aapt is required for Android label indexing", code=5)
    components, component_result = android_launchable_components(context)
    paths, path_result = android_package_paths(context)
    work = [
        (package, paths[package], component, inspector)
        for package, component in components.items()
        if package in paths
    ]
    entries = {}
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(inspect_android_apk_label, *item): item[0]
            for item in work
        }
        for future in concurrent.futures.as_completed(futures):
            package = futures[future]
            try:
                _, entry = future.result()
            except Exception as exc:
                failures.append({"package": package, "error": str(exc)})
                continue
            if entry and entry.get("label"):
                entries[package] = entry
            else:
                failures.append({"package": package, "error": "label-unavailable"})
    index = {
        "version": 1,
        "generatedAt": iso_now(),
        "inspector": inspector,
        "launchableCount": len(components),
        "indexedCount": len(entries),
        "failedCount": len(failures),
        "entries": dict(sorted(entries.items())),
        "failures": failures,
        "evidence": {
            "componentsBackend": component_result.get("backend"),
            "pathsBackend": path_result.get("backend"),
        },
    }
    atomic_write_json(android_label_cache_path(context), index)
    return index


def android_launcher_component(package, context):
    if context["test_mode"]:
        return package + "/.MainActivity", command_result(
            backend="test", simulated=True
        )
    commands = (
        [
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            package,
        ],
        [
            "pm",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            package,
        ],
    )
    attempts = []
    component_pattern = re.compile(
        r"^([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)$", re.MULTILINE
    )
    for command in commands:
        try:
            result = run_privileged(command, timeout=30, test_mode=False)
        except CommandFailure as exc:
            attempts.append({"command": command, "error": str(exc)})
            continue
        output = combined_process_output(result)
        matches = component_pattern.findall(output)
        component = next(
            (value for value in reversed(matches) if value.split("/", 1)[0] == package),
            None,
        )
        attempts.append(
            {
                "command": command,
                "ok": bool(component),
                "backend": result.get("backend"),
            }
        )
        if component:
            return component, result
    return None, command_result(ok=False, attempts=attempts)


def android_package_score(package, normalized_query, compact_query):
    lowered = package.lower()
    segments = [part for part in re.split(r"[._-]+", lowered) if part]
    last = segments[-1] if segments else lowered
    tokens = normalized_query.split()
    score = 0
    if lowered == normalized_query or lowered == compact_query:
        score = max(score, 8000)
    if last == compact_query:
        score = max(score, 7000)
    if compact_query in segments:
        score = max(score, 6200)
    if compact_query and compact_query in last:
        score = max(score, 5400 - abs(len(last) - len(compact_query)))
    if compact_query and compact_query in lowered.replace(".", ""):
        score = max(score, 4800 - abs(len(lowered) - len(compact_query)))
    if tokens and all(any(token in segment for segment in segments) for token in tokens):
        score = max(score, 4200 + 25 * len(tokens))
    if tokens and any(token in lowered for token in tokens):
        score = max(score, 1800 + 10 * sum(token in lowered for token in tokens))
    return score


def android_label_score(label, normalized_query):
    normalized_label = normalize_app_query(label)
    compact_label = normalized_label.replace(" ", "")
    compact_query = normalized_query.replace(" ", "")
    if normalized_label == normalized_query:
        return 9000
    if compact_label == compact_query:
        return 8800
    if normalized_label.startswith(normalized_query + " "):
        return 8400
    query_tokens = normalized_query.split()
    if query_tokens and all(token in normalized_label.split() for token in query_tokens):
        return 8000 + 20 * len(query_tokens)
    if normalized_query and normalized_query in normalized_label:
        return 7600
    return 0


def resolve_android_app(query, context, require_launchable=True):
    query = str(query or "").strip()
    normalized = normalize_app_query(query)
    compact = normalized.replace(" ", "")
    if not normalized:
        raise CommandFailure("application name or package is required", code=2)
    packages, inventory_result = android_package_inventory(context)
    installed = set(packages)
    scored = {}
    exact_package = query if query in installed else None
    if exact_package:
        scored[exact_package] = 10000
    for index, package in enumerate(ANDROID_APP_ALIASES.get(normalized, ())):
        if package in installed:
            scored[package] = max(scored.get(package, 0), 9500 - index)
    for package in packages:
        score = android_package_score(package, normalized, compact)
        if score:
            scored[package] = max(scored.get(package, 0), score)
    label_index = load_android_label_index(context)
    label_scores = {}
    for package, entry in label_index.get("entries", {}).items():
        if package not in installed:
            continue
        score = android_label_score(entry.get("label", ""), normalized)
        if score:
            scored[package] = max(scored.get(package, 0), score)
            label_scores[package] = score
    ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    if (not ranked or ranked[0][1] < 4000) and not context["test_mode"]:
        label_index = build_android_label_index(context, refresh=True)
        for package, entry in label_index.get("entries", {}).items():
            if package not in installed:
                continue
            score = android_label_score(entry.get("label", ""), normalized)
            if score:
                scored[package] = max(scored.get(package, 0), score)
                label_scores[package] = score
        ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        raise CommandFailure(
            "no installed Android package matches: " + query,
            code=4,
            details={"errorCode": "app_not_found", "query": query},
        )
    launcher_attempts = []
    for package, score in ranked[:30]:
        component = None
        component_evidence = None
        if require_launchable:
            component, component_evidence = android_launcher_component(package, context)
            launcher_attempts.append(
                {"package": package, "component": component, "score": score}
            )
            if not component:
                continue
        return {
            "query": query,
            "package": package,
            "component": component,
            "score": score,
            "label": (label_index.get("entries", {}).get(package) or {}).get("label"),
            "matchedByLabel": package in label_scores,
            "alternatives": [
                {"package": candidate, "score": candidate_score}
                for candidate, candidate_score in ranked[:8]
                if candidate != package
            ],
            "inventoryCount": len(packages),
            "inventoryBackend": inventory_result.get("backend"),
            "componentEvidence": component_evidence,
        }
    raise CommandFailure(
        "matching packages are installed but none has a launcher activity: " + query,
        code=4,
        details={
            "errorCode": "app_not_launchable",
            "query": query,
            "candidates": launcher_attempts,
        },
    )


def android_foreground(context):
    if context["test_mode"]:
        return {
            "package": None,
            "component": None,
            "source": "test",
            "raw": "",
        }
    observations = []
    for command, source in (
        (["dumpsys", "window", "windows"], "dumpsys-window"),
        (["dumpsys", "activity", "activities"], "dumpsys-activity"),
    ):
        try:
            result = run_privileged(command, timeout=30, test_mode=False)
        except CommandFailure:
            continue
        output = combined_process_output(result)
        observations.append(output)
        patterns = (
            r"mCurrentFocus=.*?\s([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)",
            r"mFocusedApp=.*?\s([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)",
            r"topResumedActivity=.*?\s([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)",
            r"mResumedActivity=.*?\s([A-Za-z][A-Za-z0-9_.$]*/[A-Za-z0-9_.$]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                component = match.group(1)
                return {
                    "package": component.split("/", 1)[0],
                    "component": component,
                    "source": source,
                    "raw": match.group(0),
                }
    return {
        "package": None,
        "component": None,
        "source": None,
        "raw": "\n".join(observations)[-4000:],
    }


def wait_for_android_package(package, context, timeout=12.0, poll=0.35):
    deadline = time.monotonic() + max(0.0, float(timeout))
    observations = []
    while True:
        foreground = android_foreground(context)
        observations.append(
            {
                "at": iso_now(),
                "package": foreground.get("package"),
                "component": foreground.get("component"),
            }
        )
        if foreground.get("package") == package:
            return foreground, observations
        if time.monotonic() >= deadline:
            return foreground, observations
        time.sleep(max(0.1, min(float(poll), 2.0)))


def launch_android_app(query, context, timeout=15.0):
    resolved = resolve_android_app(query, context, require_launchable=True)
    package = resolved["package"]
    component = resolved["component"]
    before = android_foreground(context)
    attempts = []
    commands = (
        ["am", "start", "-W", "-n", component],
        ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
    )
    last_foreground = before
    observations = []
    for command in commands:
        try:
            result = run_privileged(
                command,
                timeout=max(30, int(float(timeout)) + 10),
                test_mode=context["test_mode"],
            )
            attempts.append(
                {
                    "command": command,
                    "ok": result.get("ok") is True,
                    "backend": result.get("backend"),
                    "output": combined_process_output(result)[-1200:],
                }
            )
        except CommandFailure as exc:
            attempts.append({"command": command, "ok": False, "error": str(exc)})
            continue
        if context["test_mode"]:
            break
        last_foreground, observations = wait_for_android_package(
            package, context, timeout=timeout, poll=0.35
        )
        if last_foreground.get("package") == package:
            break
    verified = bool(
        not context["test_mode"] and last_foreground.get("package") == package
    )
    stable = None
    if verified:
        time.sleep(0.35)
        stable = android_foreground(context)
        verified = stable.get("package") == package
    return command_result(
        verified=verified,
        status="verified" if verified else "launch_not_foreground_verified",
        query=query,
        package=package,
        component=component,
        resolution={key: value for key, value in resolved.items() if key != "componentEvidence"},
        before=before,
        foreground=last_foreground,
        attempts=attempts,
        primaryEvidence={
            "type": "launcher-component-start",
            "verified": any(item.get("ok") for item in attempts),
            "component": component,
        },
        independentEvidence={
            "type": "foreground-package-readback",
            "verified": last_foreground.get("package") == package,
            "expectedPackage": package,
            "actualPackage": last_foreground.get("package"),
        },
        stabilityEvidence={
            "type": "repeat-foreground-readback",
            "verified": bool(stable and stable.get("package") == package),
            "package": stable.get("package") if stable else None,
            "durationMs": 350 if stable else 0,
        },
        observations=observations[-12:],
    )


def parse_android_bounds(value):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(value or ""))
    if not match:
        return None, None
    left, top, right, bottom = (int(part) for part in match.groups())
    bounds = {"left": left, "top": top, "right": right, "bottom": bottom}
    center = {"x": (left + right) // 2, "y": (top + bottom) // 2}
    return bounds, center


def parse_android_ui_xml(xml_text):
    start = xml_text.find("<?xml")
    end = xml_text.rfind("</hierarchy>")
    if start < 0 or end < 0:
        raise CommandFailure(
            "UI Automator returned no XML hierarchy",
            code=5,
            details={"errorCode": "ui_xml_missing"},
        )
    source = xml_text[start : end + len("</hierarchy>")]
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise CommandFailure(
            "UI Automator returned invalid XML",
            code=5,
            details={"errorCode": "ui_xml_invalid", "message": str(exc)},
        ) from exc
    elements = []
    boolean_fields = (
        "checkable",
        "checked",
        "clickable",
        "enabled",
        "focusable",
        "focused",
        "scrollable",
        "long-clickable",
        "password",
        "selected",
    )
    for index, node in enumerate(root.iter("node")):
        attributes = node.attrib
        bounds, center = parse_android_bounds(attributes.get("bounds"))
        password = attributes.get("password") == "true"
        element = {
            "index": index,
            "text": "" if password else attributes.get("text", ""),
            "contentDescription": attributes.get("content-desc", ""),
            "resourceId": attributes.get("resource-id", ""),
            "className": attributes.get("class", ""),
            "package": attributes.get("package", ""),
            "bounds": bounds,
            "center": center,
        }
        for field in boolean_fields:
            output_name = "longClickable" if field == "long-clickable" else field
            element[output_name] = attributes.get(field) == "true"
        class_name = element["className"].lower()
        element["editable"] = bool(
            class_name.endswith("edittext")
            or (element["focusable"] and "text" in class_name and element["enabled"])
        )
        elements.append(element)
    return {
        "xml": source,
        "sourceHash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "elements": elements,
        "elementCount": len(elements),
        "packages": sorted({item["package"] for item in elements if item["package"]}),
    }


def capture_android_ui(context, timeout=18):
    if context["test_mode"]:
        return parse_android_ui_xml("<?xml version='1.0'?><hierarchy rotation='0'/>")
    remote = "/sdcard/Download/.codex-frontier-ui-" + uuid.uuid4().hex + ".xml"
    attempts = []
    try:
        for command in (
            ["uiautomator", "dump", "--compressed", remote],
            ["uiautomator", "dump", remote],
        ):
            try:
                dump_result = run_privileged(command, timeout=timeout, test_mode=False)
                attempts.append(
                    {
                        "command": command,
                        "ok": dump_result.get("ok") is True,
                        "output": combined_process_output(dump_result)[-800:],
                    }
                )
                # Some Android builds return from `uiautomator dump` just
                # before MediaProvider makes the completed file readable.
                # Poll the exact unique path rather than treating that race as
                # a failed hierarchy capture.
                read_deadline = time.monotonic() + min(max(float(timeout) / 2, 3.0), 8.0)
                read_error = None
                while time.monotonic() <= read_deadline:
                    try:
                        # Termux has direct read access to shared storage. This
                        # avoids rish implementations that do not relay native
                        # command stdout through a captured subprocess pipe.
                        read_output = pathlib.Path(remote).read_text(
                            encoding="utf-8", errors="replace"
                        )
                        if "</hierarchy>" in read_output:
                            hierarchy = parse_android_ui_xml(read_output)
                            hierarchy["backend"] = dump_result.get("backend")
                            hierarchy["attempts"] = attempts
                            hierarchy["capturedAt"] = iso_now()
                            return hierarchy
                    except OSError as exc:
                        read_error = str(exc)
                    time.sleep(0.25)
                raise CommandFailure(
                    "UI hierarchy file did not become readable",
                    code=5,
                    details={"errorCode": "ui_file_read_timeout", "error": read_error},
                )
            except CommandFailure as exc:
                attempts.append({"command": command, "ok": False, "error": str(exc)})
        raise CommandFailure(
            "unable to capture Android UI hierarchy",
            code=5,
            details={"errorCode": "ui_capture_failed", "attempts": attempts},
        )
    finally:
        try:
            pathlib.Path(remote).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            try:
                run_privileged(["rm", "-f", remote], timeout=10, test_mode=False)
            except CommandFailure:
                pass


def option_boolean(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise CommandFailure("invalid boolean option: " + str(value), code=2)


def ui_selector_from_options(options, prefix=""):
    selector_key = prefix + "selector"
    selector = {}
    if options.get(selector_key):
        try:
            selector = json.loads(options[selector_key])
        except json.JSONDecodeError as exc:
            raise CommandFailure(selector_key + " must be valid JSON", code=2) from exc
        if not isinstance(selector, dict):
            raise CommandFailure(selector_key + " must be a JSON object", code=2)
    mappings = {
        "text": "text",
        "contains": "contains",
        "text-contains": "textContains",
        "text-regex": "textRegex",
        "description": "contentDescription",
        "desc": "contentDescription",
        "description-contains": "descriptionContains",
        "desc-contains": "descriptionContains",
        "resource-id": "resourceId",
        "id": "resourceId",
        "id-contains": "resourceIdContains",
        "class": "className",
        "class-contains": "classContains",
        "package": "package",
    }
    for option_name, selector_name in mappings.items():
        key = prefix + option_name
        if options.get(key) is not None:
            selector[selector_name] = options[key]
    for name in (
        "clickable",
        "enabled",
        "focusable",
        "focused",
        "scrollable",
        "selected",
        "checked",
        "editable",
    ):
        key = prefix + name
        if options.get(key) is not None:
            selector[name] = option_boolean(options[key])
    index_key = prefix + "index"
    if options.get(index_key) is not None:
        selector["matchIndex"] = int(options[index_key])
    return selector


def ui_element_matches(element, selector):
    def exact(field, value):
        return str(element.get(field, "")).casefold() == str(value).casefold()

    def contains(field, value):
        return str(value).casefold() in str(element.get(field, "")).casefold()

    exact_fields = {
        "text": "text",
        "contentDescription": "contentDescription",
        "resourceId": "resourceId",
        "className": "className",
        "package": "package",
    }
    contains_fields = {
        "textContains": "text",
        "descriptionContains": "contentDescription",
        "resourceIdContains": "resourceId",
        "classContains": "className",
    }
    for selector_name, element_name in exact_fields.items():
        if selector_name in selector and not exact(element_name, selector[selector_name]):
            return False
    for selector_name, element_name in contains_fields.items():
        if selector_name in selector and not contains(element_name, selector[selector_name]):
            return False
    if selector.get("contains") is not None:
        needle = str(selector["contains"]).casefold()
        haystack = " ".join(
            str(element.get(field, ""))
            for field in ("text", "contentDescription", "resourceId", "className")
        ).casefold()
        if needle not in haystack:
            return False
    if selector.get("textRegex") is not None:
        try:
            if not re.search(str(selector["textRegex"]), str(element.get("text", "")), re.I):
                return False
        except re.error as exc:
            raise CommandFailure("invalid selector text regex", code=2) from exc
    for field in (
        "clickable",
        "enabled",
        "focusable",
        "focused",
        "scrollable",
        "selected",
        "checked",
        "editable",
    ):
        if field in selector and bool(element.get(field)) != bool(selector[field]):
            return False
    return True


def select_ui_elements(elements, selector):
    matches = [item for item in elements if ui_element_matches(item, selector)]
    if "matchIndex" in selector:
        index = int(selector["matchIndex"])
        if index < 0:
            index += len(matches)
        return [matches[index]] if 0 <= index < len(matches) else []
    return matches


def compact_ui_elements(elements, limit=120):
    meaningful = [
        item
        for item in elements
        if item.get("text")
        or item.get("contentDescription")
        or item.get("resourceId")
        or item.get("clickable")
        or item.get("editable")
        or item.get("scrollable")
    ]
    return meaningful[: max(1, min(int(limit), 500))]


def wait_for_android_element(selector, context, timeout=12.0, poll=0.5, absent=False):
    deadline = time.monotonic() + max(0.0, float(timeout))
    attempts = 0
    last_hierarchy = None
    while True:
        attempts += 1
        last_hierarchy = capture_android_ui(context)
        matches = select_ui_elements(last_hierarchy["elements"], selector)
        satisfied = not matches if absent else bool(matches)
        if satisfied:
            return last_hierarchy, matches, attempts
        if time.monotonic() >= deadline:
            return last_hierarchy, matches, attempts
        time.sleep(max(0.1, min(float(poll), 2.0)))


def semantic_android_action(action, options, context):
    selector = ui_selector_from_options(options)
    if not selector:
        raise CommandFailure(action + " requires a selector", code=2)
    timeout = max(0.0, min(float(options.get("timeout", 12)), 60.0))
    poll = max(0.1, min(float(options.get("poll", 0.5)), 2.0))
    before, matches, attempts = wait_for_android_element(
        selector, context, timeout=timeout, poll=poll
    )
    if not matches:
        raise CommandFailure(
            "UI element was not found",
            code=4,
            details={
                "errorCode": "ui_element_not_found",
                "selector": selector,
                "attempts": attempts,
                "packages": before.get("packages", []),
            },
        )
    target = matches[0]
    center = target.get("center")
    if not center:
        raise CommandFailure("matched UI element has no usable bounds", code=5)
    if action in {"tap-element", "click"}:
        command = ["input", "tap", str(center["x"]), str(center["y"])]
    else:
        duration = max(350, min(int(options.get("duration", 800)), 5000))
        command = [
            "input",
            "swipe",
            str(center["x"]),
            str(center["y"]),
            str(center["x"]),
            str(center["y"]),
            str(duration),
        ]
    input_result = run_privileged(command, timeout=30, test_mode=context["test_mode"])
    after_selector = ui_selector_from_options(options, prefix="after-")
    after = None
    after_matches = []
    if after_selector:
        after, after_matches, _ = wait_for_android_element(
            after_selector,
            context,
            timeout=max(0.0, min(float(options.get("after-timeout", timeout)), 60.0)),
            poll=poll,
        )
        verified = bool(after_matches)
    else:
        time.sleep(0.25 if not context["test_mode"] else 0)
        try:
            after = capture_android_ui(context)
            verified = after.get("sourceHash") != before.get("sourceHash")
        except CommandFailure:
            verified = False
    return command_result(
        verified=verified,
        status="verified" if verified else "action_completed_unverified",
        action=action,
        selector=selector,
        target=target,
        inputBackend=input_result.get("backend"),
        hierarchyChanged=bool(
            after and after.get("sourceHash") != before.get("sourceHash")
        ),
        afterSelector=after_selector or None,
        afterMatches=after_matches[:5],
        primaryEvidence={
            "type": "semantic-element-bounds-action",
            "verified": input_result.get("ok") is True,
            "bounds": target.get("bounds"),
        },
        independentEvidence={
            "type": "post-action-ui-readback",
            "verified": verified,
            "hierarchyChanged": bool(
                after and after.get("sourceHash") != before.get("sourceHash")
            ),
        },
    )


def encode_android_input_text(value):
    # Android's `input text` represents spaces as %s. Quoting is still applied
    # by the privilege transport, so punctuation remains a single argument.
    return str(value).replace("%", "%25").replace(" ", "%s")


def type_into_android_element(options, context):
    value = options.get("value")
    if value is None:
        raise CommandFailure("type-into requires --value", code=2)
    selector = ui_selector_from_options(options)
    if not selector:
        selector = {"editable": True, "focused": True}
    timeout = max(0.0, min(float(options.get("timeout", 12)), 60.0))
    before, matches, attempts = wait_for_android_element(
        selector, context, timeout=timeout, poll=0.5
    )
    if not matches and selector.get("focused"):
        selector = {key: item for key, item in selector.items() if key != "focused"}
        before, matches, attempts = wait_for_android_element(
            selector, context, timeout=0, poll=0.5
        )
    if not matches:
        raise CommandFailure(
            "editable UI element was not found",
            code=4,
            details={"errorCode": "editable_element_not_found", "selector": selector},
        )
    target = matches[0]
    center = target.get("center")
    if not center:
        raise CommandFailure("editable UI element has no usable bounds", code=5)
    command_results = [
        run_privileged(
            ["input", "tap", str(center["x"]), str(center["y"])],
            timeout=30,
            test_mode=context["test_mode"],
        )
    ]
    if option_boolean(options.get("clear"), False):
        command_results.append(
            run_privileged(
                ["input", "keycombination", "113", "29"],
                timeout=30,
                test_mode=context["test_mode"],
            )
        )
        command_results.append(
            run_privileged(
                ["input", "keyevent", "KEYCODE_DEL"],
                timeout=30,
                test_mode=context["test_mode"],
            )
        )
    local_clipboard = pathlib.Path(__file__).resolve().parent / "termux-clipboard-set"
    use_clipboard = option_boolean(options.get("clipboard"), False) or any(
        ord(character) > 127 for character in str(value)
    )
    input_method = "android-input-text"
    if use_clipboard and local_clipboard.exists() and not context["test_mode"]:
        clipboard_result = run_process(
            [str(local_clipboard)], timeout=30, input_text=str(value)
        )
        if clipboard_result.get("ok"):
            command_results.append(clipboard_result)
            command_results.append(
                run_privileged(
                    ["input", "keyevent", "KEYCODE_PASTE"],
                    timeout=30,
                    test_mode=False,
                )
            )
            input_method = "termux-api-clipboard-paste"
        else:
            command_results.append(
                run_privileged(
                    ["input", "text", encode_android_input_text(value)],
                    timeout=30,
                    test_mode=False,
                )
            )
    else:
        command_results.append(
            run_privileged(
                ["input", "text", encode_android_input_text(value)],
                timeout=30,
                test_mode=context["test_mode"],
            )
        )
    if option_boolean(options.get("submit"), False):
        command_results.append(
            run_privileged(
                ["input", "keyevent", "KEYCODE_ENTER"],
                timeout=30,
                test_mode=context["test_mode"],
            )
        )
    time.sleep(0.25 if not context["test_mode"] else 0)
    try:
        after = capture_android_ui(context)
        changed = after.get("sourceHash") != before.get("sourceHash")
        value_visible = any(
            str(value).casefold() in str(item.get("text", "")).casefold()
            for item in after.get("elements", [])
            if not item.get("password")
        )
    except CommandFailure:
        after = None
        changed = False
        value_visible = False
    verified = bool(value_visible or changed)
    return command_result(
        verified=verified,
        status="verified" if verified else "text_injected_unverified",
        selector=selector,
        target=target,
        textLength=len(str(value)),
        inputMethod=input_method,
        submitted=option_boolean(options.get("submit"), False),
        hierarchyChanged=changed,
        valueVisible=value_visible,
        primaryEvidence={
            "type": "focused-input-injection",
            "verified": all(item.get("ok") is True for item in command_results),
            "commandCount": len(command_results),
        },
        independentEvidence={
            "type": "post-input-ui-readback",
            "verified": verified,
            "valueVisible": value_visible,
            "hierarchyChanged": changed,
        },
    )


def android_screen_size(context):
    result = run_privileged(["wm", "size"], timeout=30, test_mode=context["test_mode"])
    match = re.search(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", combined_process_output(result))
    if not match:
        if context["test_mode"]:
            return 1080, 2400
        raise CommandFailure("unable to read Android display size", code=5)
    return int(match.group(1)), int(match.group(2))


def scroll_android(direction, options, context):
    width, height = android_screen_size(context)
    direction = str(direction or "down").lower()
    duration = max(100, min(int(options.get("duration", 450)), 5000))
    x = width // 2
    y = height // 2
    if direction == "down":
        coordinates = (x, int(height * 0.78), x, int(height * 0.28))
    elif direction == "up":
        coordinates = (x, int(height * 0.28), x, int(height * 0.78))
    elif direction == "right":
        coordinates = (int(width * 0.78), y, int(width * 0.22), y)
    elif direction == "left":
        coordinates = (int(width * 0.22), y, int(width * 0.78), y)
    else:
        raise CommandFailure("scroll direction must be up, down, left, or right", code=2)
    before = capture_android_ui(context)
    result = run_privileged(
        ["input", "swipe", *(str(value) for value in coordinates), str(duration)],
        timeout=30,
        test_mode=context["test_mode"],
    )
    time.sleep(0.25 if not context["test_mode"] else 0)
    after = capture_android_ui(context)
    changed = after.get("sourceHash") != before.get("sourceHash")
    return command_result(
        verified=changed,
        status="verified" if changed else "scroll_completed_unverified",
        direction=direction,
        coordinates=coordinates,
        durationMs=duration,
        display={"width": width, "height": height},
        primaryEvidence={"type": "display-relative-swipe", "verified": result.get("ok") is True},
        independentEvidence={"type": "post-scroll-ui-readback", "verified": changed},
    )


def wait_for_android_ui_stable(context, timeout=15.0, stable_for=1.0, poll=0.35):
    deadline = time.monotonic() + max(0.0, float(timeout))
    stable_since = None
    previous_hash = None
    captures = 0
    last = None
    while True:
        last = capture_android_ui(context)
        captures += 1
        current_hash = last.get("sourceHash")
        now = time.monotonic()
        if current_hash == previous_hash:
            stable_since = stable_since if stable_since is not None else now
            if now - stable_since >= max(0.0, float(stable_for)):
                return last, captures, now - stable_since
        else:
            previous_hash = current_hash
            stable_since = now
        if now >= deadline:
            return last, captures, max(0.0, now - (stable_since or now))
        time.sleep(max(0.1, min(float(poll), 2.0)))


def take_android_screenshot(context, output=None):
    destination = canonical_path(
        output
        or (
            pathlib.Path(context["root"])
            / "evidence"
            / "screenshots"
            / (utc_now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".png")
        )
    )
    shared_destination = str(destination).startswith("/sdcard/")
    remote = str(destination) if shared_destination else (
        "/sdcard/Download/.codex-frontier-screenshot-" + uuid.uuid4().hex + ".png"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run_privileged(
            ["screencap", "-p", remote], timeout=30, test_mode=context["test_mode"]
        )
        if context["test_mode"]:
            return command_result(
                verified=False,
                simulated=True,
                output=str(destination),
                backend=result.get("backend"),
            )
        source = pathlib.Path(remote)
        deadline = time.monotonic() + 5.0
        while time.monotonic() <= deadline and (
            not source.exists() or source.stat().st_size < 8
        ):
            time.sleep(0.1)
        if not source.exists() or source.stat().st_size < 8:
            raise CommandFailure("Android screenshot was not created", code=5)
        if not shared_destination:
            shutil.copy2(str(source), str(destination))
        with open(destination, "rb") as stream:
            header = stream.read(8)
        verified = header == b"\x89PNG\r\n\x1a\n"
        return command_result(
            verified=verified,
            status="verified" if verified else "screenshot_invalid",
            output=str(destination),
            bytes=destination.stat().st_size,
            sha256=sha256_file(destination),
            backend=result.get("backend"),
            temporarySharedFileCleaned=not shared_destination,
        )
    finally:
        if not shared_destination:
            try:
                pathlib.Path(remote).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                try:
                    run_privileged(["rm", "-f", remote], timeout=10, test_mode=False)
                except CommandFailure:
                    pass


def android_sequence_step_arguments(step):
    if not isinstance(step, dict):
        raise CommandFailure("every Android sequence step must be an object", code=2)
    action = str(step.get("action") or "").strip()
    if not action or action == "sequence":
        raise CommandFailure("Android sequence step has an invalid action", code=2)
    arguments = [action]
    if isinstance(step.get("args"), list):
        arguments.extend(str(value) for value in step["args"])
        return arguments
    if step.get("target") is not None:
        arguments.append(str(step["target"]))
    options = step.get("options") if isinstance(step.get("options"), dict) else {}
    for key, value in step.items():
        if key in {"action", "args", "target", "options"}:
            continue
        options.setdefault(key, value)
    for key, value in options.items():
        option = "--" + str(key).replace("_", "-")
        if value is True:
            arguments.append(option)
        elif value is False or value is None:
            if value is False:
                arguments.extend([option, "false"])
        else:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, separators=(",", ":"))
            arguments.extend([option, str(value)])
    return arguments


def execute_android_sequence(steps, context, continue_on_error=False):
    if not isinstance(steps, list) or not steps:
        raise CommandFailure("Android sequence requires a non-empty JSON array", code=2)
    if len(steps) > 100:
        raise CommandFailure("Android sequence exceeds the 100-step limit", code=2)
    records = []
    for index, step in enumerate(steps):
        arguments = android_sequence_step_arguments(step)
        try:
            result = handle_android(arguments, context)
            records.append(
                {
                    "index": index,
                    "arguments": arguments,
                    "ok": result.get("ok") is True,
                    "verified": result.get("verified") is True,
                    "result": result,
                }
            )
            if not result.get("ok") and not continue_on_error:
                break
        except CommandFailure as exc:
            records.append(
                {
                    "index": index,
                    "arguments": arguments,
                    "ok": False,
                    "verified": False,
                    "error": str(exc),
                    "details": exc.details,
                }
            )
            if not continue_on_error:
                break
    complete = len(records) == len(steps) and all(item.get("ok") for item in records)
    verified = complete and all(item.get("verified") for item in records)
    return command_result(
        ok=complete,
        verified=verified,
        status="verified" if verified else "sequence_incomplete_or_unverified",
        requestedSteps=len(steps),
        completedSteps=sum(item.get("ok") is True for item in records),
        records=records,
        primaryEvidence={
            "type": "bounded-android-sequence",
            "verified": complete,
            "requestedSteps": len(steps),
            "completedSteps": sum(item.get("ok") is True for item in records),
        },
        independentEvidence={
            "type": "per-step-verification",
            "verified": verified,
            "verifiedSteps": sum(item.get("verified") is True for item in records),
        },
    )


def guard_android_shell_command(command):
    lowered = [str(value).lower() for value in command]
    protected = next((value for value in command if value in PROTECTED_PACKAGES), None)
    if not protected:
        return
    destructive = (
        lowered[:2] in (["am", "force-stop"], ["pm", "uninstall"], ["pm", "clear"])
        or "disable-user" in lowered
        or "uninstall" in lowered
    )
    if destructive:
        raise CommandFailure("refusing protected package operation: " + protected, code=3)


def handle_android(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-android <resolve|open|launch|focus|wait-package|elements|find|wait-element|tap-element|longtap-element|type-into|scroll|tap|swipe|text|key|back|home|recents|notifications|quick-settings|screenshot|dump|packages|app-info|url|settings|shell|force-stop> ...",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    if action == "capabilities":
        api_commands = sorted(
            path.name
            for path in pathlib.Path(__file__).resolve().parent.glob("termux-*")
            if path.exists()
        )
        api_package = run_privileged(
            ["pm", "path", "com.termux.api"], test_mode=context["test_mode"]
        )
        privilege = run_privileged(["id"], test_mode=context["test_mode"])
        return command_result(
            verified=bool(api_package.get("ok") and privilege.get("ok")),
            androidBackend=privilege.get("backend"),
            uiAutomator=True,
            semanticActions=[
                "index-apps",
                "resolve",
                "open",
                "focus",
                "wait-package",
                "elements",
                "find",
                "wait-element",
                "wait-stable",
                "tap-element",
                "longtap-element",
                "type-into",
                "scroll",
                "sequence",
            ],
            rawActions=[
                "tap",
                "swipe",
                "text",
                "key",
                "back",
                "home",
                "recents",
                "notifications",
                "quick-settings",
                "screenshot",
                "url",
                "settings",
                "shell",
            ],
            termuxApiInstalled="package:" in combined_process_output(api_package),
            termuxApiCommands=api_commands,
            termuxApiCommandCount=len(api_commands),
        )
    if action == "index-apps":
        index = build_android_label_index(
            context, refresh=option_boolean(options.get("refresh"), False)
        )
        verified = int(index.get("indexedCount", len(index.get("entries", {})))) > 0
        return command_result(
            verified=verified,
            status="verified" if verified else "label_index_empty",
            generatedAt=index.get("generatedAt"),
            launchableCount=index.get("launchableCount"),
            indexedCount=index.get("indexedCount", len(index.get("entries", {}))),
            failedCount=index.get("failedCount", 0),
            indexPath=str(android_label_cache_path(context)),
        )
    if action == "sequence":
        encoded = options.get("steps")
        if options.get("file"):
            try:
                encoded = canonical_path(options["file"]).read_text(encoding="utf-8")
            except OSError as exc:
                raise CommandFailure("unable to read Android sequence file", code=4) from exc
        if not encoded:
            raise CommandFailure("sequence requires --steps JSON or --file", code=2)
        try:
            steps = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise CommandFailure("Android sequence must be valid JSON", code=2) from exc
        return execute_android_sequence(
            steps,
            context,
            continue_on_error=option_boolean(options.get("continue-on-error"), False),
        )
    if action == "resolve":
        return command_result(
            verified=True,
            **resolve_android_app(" ".join(positional), context, require_launchable=True),
        )
    if action in {"open", "launch"}:
        if not positional:
            raise CommandFailure(action + " requires an app name or package", code=2)
        return launch_android_app(
            " ".join(positional),
            context,
            timeout=max(1.0, min(float(options.get("timeout", 15)), 60.0)),
        )
    if action in {"focus", "current"}:
        foreground = android_foreground(context)
        return command_result(
            verified=bool(foreground.get("package")), foreground=foreground
        )
    if action == "wait-package":
        if not positional:
            raise CommandFailure("wait-package requires an app name or package", code=2)
        query = " ".join(positional)
        resolved = resolve_android_app(query, context, require_launchable=False)
        foreground, observations = wait_for_android_package(
            resolved["package"],
            context,
            timeout=max(0.0, min(float(options.get("timeout", 15)), 120.0)),
            poll=max(0.1, min(float(options.get("poll", 0.5)), 2.0)),
        )
        verified = foreground.get("package") == resolved["package"]
        return command_result(
            verified=verified,
            status="verified" if verified else "package_wait_timeout",
            expectedPackage=resolved["package"],
            foreground=foreground,
            observations=observations[-20:],
        )
    if action in {"elements", "find", "wait-element"} or (
        action == "dump" and not positional
    ):
        selector = ui_selector_from_options(options)
        timeout = max(0.0, min(float(options.get("timeout", 0)), 60.0))
        absent = option_boolean(options.get("absent"), False)
        if action in {"find", "wait-element"} and not selector:
            raise CommandFailure(action + " requires a selector", code=2)
        if action == "wait-element" or (action == "find" and timeout > 0):
            hierarchy, matches, attempts = wait_for_android_element(
                selector,
                context,
                timeout=timeout or (12.0 if action == "wait-element" else 0.0),
                poll=max(0.1, min(float(options.get("poll", 0.5)), 2.0)),
                absent=absent,
            )
            verified = not matches if absent else bool(matches)
        else:
            hierarchy = capture_android_ui(context)
            matches = select_ui_elements(hierarchy["elements"], selector) if selector else hierarchy["elements"]
            attempts = 1
            verified = bool(matches) if selector else True
        return command_result(
            verified=verified,
            status="verified" if verified else "element_wait_timeout",
            selector=selector or None,
            absent=absent,
            attempts=attempts,
            packages=hierarchy["packages"],
            elementCount=hierarchy["elementCount"],
            sourceHash=hierarchy["sourceHash"],
            matches=(
                matches[: max(1, min(int(options.get("limit", 120)), 500))]
                if selector
                else compact_ui_elements(matches, options.get("limit", 120))
            ),
            matchCount=len(matches),
            temporaryHierarchyCleaned=True,
        )
    if action in {"wait-stable", "stabilize"}:
        requested_stability = max(
            0.0, min(float(options.get("stable-for", 1.0)), 10.0)
        )
        hierarchy, captures, stable_seconds = wait_for_android_ui_stable(
            context,
            timeout=max(0.5, min(float(options.get("timeout", 15)), 120.0)),
            stable_for=requested_stability,
            poll=max(0.1, min(float(options.get("poll", 0.35)), 2.0)),
        )
        verified = stable_seconds >= requested_stability
        return command_result(
            verified=verified,
            status="verified" if verified else "ui_stability_timeout",
            stableForSeconds=stable_seconds,
            requestedStableSeconds=requested_stability,
            captures=captures,
            sourceHash=hierarchy.get("sourceHash"),
            packages=hierarchy.get("packages"),
            temporaryHierarchyCleaned=True,
        )
    if action in {"tap-element", "click", "longtap-element", "long-click"}:
        normalized_action = "tap-element" if action in {"tap-element", "click"} else "longtap-element"
        return semantic_android_action(normalized_action, options, context)
    if action == "type-into":
        return type_into_android_element(options, context)
    if action == "scroll":
        direction = positional[0] if positional else options.get("direction", "down")
        return scroll_android(direction, options, context)
    if action == "screenshot":
        output = positional[0] if positional else options.get("output")
        return take_android_screenshot(context, output)
    if action == "app-info":
        if not positional:
            raise CommandFailure("app-info requires a package", code=2)
        query = " ".join(positional)
        package = query
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", query):
            package = resolve_android_app(query, context, require_launchable=False)["package"]
        return command_result(verified=True, **package_inspection(package, context))
    if action == "url":
        if not positional:
            raise CommandFailure("url requires a URI", code=2)
        return run_privileged(
            ["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", positional[0]],
            timeout=60,
            test_mode=context["test_mode"],
        )
    if action in {"back", "home", "recents", "notifications", "quick-settings"}:
        keyevents = {
            "back": ["input", "keyevent", "KEYCODE_BACK"],
            "home": ["input", "keyevent", "KEYCODE_HOME"],
            "recents": ["input", "keyevent", "KEYCODE_APP_SWITCH"],
            "notifications": ["cmd", "statusbar", "expand-notifications"],
            "quick-settings": ["cmd", "statusbar", "expand-settings"],
        }
        return run_privileged(keyevents[action], timeout=30, test_mode=context["test_mode"])
    if action == "force-stop" and positional and positional[0] in PROTECTED_PACKAGES:
        raise CommandFailure("refusing protected package operation: " + positional[0], code=3)
    mapping = {
        "packages": ["pm", "list", "packages", *args[1:]],
        "force-stop": ["am", "force-stop", args[1]] if len(args) > 1 else None,
        "tap": ["input", "tap", *args[1:]],
        "swipe": ["input", "swipe", *args[1:]],
        "text": ["input", "text", encode_android_input_text(" ".join(args[1:]))]
        if len(args) > 1
        else None,
        "key": ["input", "keyevent", *args[1:]],
        "keyevent": ["input", "keyevent", *args[1:]],
        "dump": ["uiautomator", "dump", args[1]] if len(args) > 1 else None,
    }
    if action == "shell":
        command = args[1:]
        guard_android_shell_command(command)
    elif action == "settings":
        command = ["settings", *args[1:]]
    else:
        command = mapping.get(action)
    if not command:
        raise CommandFailure("invalid codex-android action", code=2)
    return run_privileged(command, test_mode=context["test_mode"])


def handle_privilege(args, context):
    if args and args[0] == "status":
        candidates = [
            {"backend": name, "available": shutil.which(command[0]) is not None}
            for name, command in privilege_candidates(["true"])
        ]
        return command_result(backends=candidates)
    if not args:
        raise CommandFailure("usage: codex-privilege status|<command>", code=2)
    return run_privileged(args, test_mode=context["test_mode"])


def handle_provision(args, context):
    if not args:
        raise CommandFailure("usage: codex-provision <package> ...", code=2)
    if context["test_mode"]:
        return command_result(packages=args, backend="test")
    result = run_process(["pkg", "install", "-y", *args], timeout=900)
    if not result["ok"]:
        raise CommandFailure("package provisioning failed", result["exitCode"], result)
    result["packages"] = args
    return result


def handle_net(args, context):
    if not args:
        raise CommandFailure("usage: codex-net <get|head|dns|ping|tls|port|service|route|proxy> ...", code=2)
    action = args[0]
    if action == "get" and len(args) > 1:
        return handle_fetch(args[1:], context)
    if action == "head" and len(args) > 1:
        request = urllib.request.Request(args[1], method="HEAD")
        with urllib.request.urlopen(request, timeout=20) as response:
            return command_result(
                url=args[1], status=response.status, headers=dict(response.headers)
            )
    if action == "dns" and len(args) > 1:
        return command_result(host=args[1], addresses=socket.gethostbyname_ex(args[1])[2])
    if action == "ping" and len(args) > 1:
        return run_process(["ping", "-c", "3", args[1]], timeout=20)
    if action == "route" and len(args) > 1:
        host = args[1]
        if context["test_mode"]:
            return command_result(
                host=host,
                route=None,
                verified=False,
                diagnostic="route",
                reason="test mode does not inspect the device route table",
            )
        result = run_process(["ip", "route", "get", host], timeout=20)
        if not result.get("ok"):
            fallback = run_process(["ip", "route"], timeout=20)
            return command_result(
                host=host,
                route=fallback.get("stdout", "").strip(),
                routeQuery=result.get("stdout", "").strip(),
                verified=fallback.get("ok") is True,
                primaryEvidence={"type": "ip-route-get", "verified": result.get("ok") is True, "result": result},
                independentEvidence={"type": "ip-route-table", "verified": fallback.get("ok") is True, "result": fallback},
            )
        return command_result(
            host=host,
            route=result.get("stdout", "").strip(),
            verified=True,
            primaryEvidence={"type": "ip-route-get", "verified": True, "result": result},
            independentEvidence={"type": "route-output-readback", "verified": bool(result.get("stdout", "").strip())},
        )
    if action in {"tls", "port", "service"} and len(args) > 1:
        host = args[1]
        try:
            port = int(args[2]) if len(args) > 2 else 443 if action == "tls" else 80
        except ValueError as exc:
            raise CommandFailure("network port must be an integer", code=2) from exc
        if not 1 <= port <= 65535:
            raise CommandFailure("network port is out of range", code=2)
        if context["test_mode"]:
            return command_result(
                host=host,
                port=port,
                reachable=False,
                verified=False,
                diagnostic="port" if action == "service" else action,
                reason="test mode does not open network sockets",
            )
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=10) as raw:
                if action in {"port", "service"}:
                    return command_result(
                        host=host,
                        port=port,
                        service=host + ":" + str(port) if action == "service" else None,
                        reachable=True,
                        verified=True,
                        durationMs=int((time.monotonic() - started) * 1000),
                    )
                tls_context = ssl.create_default_context()
                with tls_context.wrap_socket(raw, server_hostname=host) as connection:
                    certificate = connection.getpeercert()
                    return command_result(
                        host=host,
                        port=port,
                        reachable=True,
                        verified=True,
                        tlsVerified=True,
                        protocol=connection.version(),
                        cipher=connection.cipher(),
                        peerCertificate={
                            "subject": certificate.get("subject"),
                            "issuer": certificate.get("issuer"),
                            "notBefore": certificate.get("notBefore"),
                            "notAfter": certificate.get("notAfter"),
                        },
                        durationMs=int((time.monotonic() - started) * 1000),
                    )
        except (OSError, ssl.SSLError) as exc:
            raise CommandFailure(
                "network {} diagnostic failed".format(action),
                code=8,
                details={
                    "errorCode": "{}_failed".format(action),
                    "host": host,
                    "port": port,
                    "error": str(exc),
                },
            ) from exc
    if action == "proxy":
        proxies = {}
        for scheme, value in urllib.request.getproxies().items():
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme and parsed.hostname:
                host = parsed.hostname
                if parsed.port:
                    host += ":" + str(parsed.port)
                proxies[scheme] = parsed.scheme + "://" + host
            else:
                proxies[scheme] = "configured"
        return command_result(proxies=proxies, proxyConfigured=bool(proxies), verified=True)
    raise CommandFailure("invalid codex-net action", code=2)


def handle_protocol(args, context):
    if len(args) < 2 or args[0] != "open":
        raise CommandFailure("usage: codex-protocol open <uri>", code=2)
    return run_privileged(
        ["am", "start", "-a", "android.intent.action.VIEW", "-d", args[1]],
        test_mode=context["test_mode"],
    )


def automation_broker_request(root, payload, test_mode=False, timeout=20):
    request = {
        "requestId": uuid.uuid4().hex,
        "jobId": payload.pop("jobId", None),
        "idempotencyKey": payload.pop("idempotencyKey", uuid.uuid4().hex),
        **payload,
    }
    if test_mode:
        return command_result(
            status="simulated",
            request=request,
            primaryEvidence={"type": "test-broker", "action": request.get("action")},
            independentEvidence={"type": "test-readback"},
            verified=False,
        )
    config = load_json(pathlib.Path(root) / "automation" / "broker.json", None)
    if not config or not config.get("token"):
        raise CommandFailure("Android automation broker is not configured", code=5)
    request["token"] = config["token"]
    encoded = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        with socket.create_connection(
            (config.get("host", "127.0.0.1"), int(config.get("port", 18767))),
            timeout=timeout,
        ) as connection:
            connection.sendall(encoded)
            connection.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                block = connection.recv(65536)
                if not block:
                    break
                chunks.append(block)
                if sum(map(len, chunks)) > 1024 * 1024:
                    raise CommandFailure("automation broker response too large", code=7)
    except (OSError, ValueError) as exc:
        raise CommandFailure(
            "Android automation broker unavailable: " + str(exc),
            code=5,
        ) from exc
    try:
        response = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandFailure("invalid automation broker response", code=7) from exc
    if not response.get("ok"):
        raise CommandFailure(
            response.get("message") or response.get("error") or "automation action failed",
            code=int(response.get("exitCode", 1)),
            details=response,
        )
    return response


def handle_media(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-media <open|search|play|pause|resume|stop|next|previous|seek|now-playing|volume|route|photo|audio> ...",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    adapter_query = str(options.get("app") or "youtube_music").strip()
    adapter_id = adapter_query.replace("-", "_").replace(" ", "_")
    media_actions = {
        "open",
        "search",
        "play",
        "pause",
        "resume",
        "stop",
        "next",
        "previous",
        "seek",
        "shuffle",
        "repeat",
        "now-playing",
        "route",
    }
    adapter = None
    if action in media_actions:
        try:
            adapter = get_app_adapter(adapter_id)
        except CommandFailure:
            # Resolve arbitrary installed media apps by package or visible
            # application label, while retaining the built-in adapter path.
            adapter = resolve_app_adapter(adapter_query, context)
    query = str(options.get("query") or " ".join(positional)).strip()
    if action == "open":
        result = automation_broker_request(
            context["root"],
            {
                "jobId": context.get("job_id"),
                "action": "app.open",
                "arguments": {"adapter": adapter},
            },
            context["test_mode"],
        )
        result.update(
            {
                "operation": action,
                "adapter": adapter_id,
                "risk": classify_action_risk("app.open"),
            }
        )
        return result
    if action in {
        "search",
        "pause",
        "resume",
        "stop",
        "next",
        "previous",
        "seek",
        "shuffle",
        "repeat",
        "now-playing",
        "route",
    } or (action == "play" and (options.get("app") or options.get("query"))):
        broker_action = "media.now_playing" if action == "now-playing" else "media.control"
        if action in {"search"} or (action == "play" and query):
            broker_action = "media.search_play"
        result = automation_broker_request(
            context["root"],
            {
                "jobId": context.get("job_id"),
                "action": broker_action,
                "arguments": {
                    "operation": action,
                    "query": query,
                    "adapter": adapter,
                    "stabilityWindowMs": int(options.get("stability-window-ms", 2500)),
                },
            },
            context["test_mode"],
        )
        result.update(
            {
                "operation": action,
                "query": query,
                "adapter": adapter.get("id", adapter_id) if adapter else adapter_id,
                "adapterQuery": adapter_query,
                "risk": classify_action_risk(
                    "media.now_playing" if action == "now-playing" else "media." + action
                ),
            }
        )
        return result
    commands = {
        "photo": ["termux-camera-photo", *(args[1:] or ["/sdcard/Download/codex-photo.jpg"])],
        "audio": ["termux-microphone-record", *args[1:]],
        "volume": ["termux-volume", *args[1:]],
        "play": ["termux-media-player", "play", *args[1:]],
    }
    command = commands.get(action)
    if not command:
        raise CommandFailure("invalid codex-media action", code=2)
    return run_process(command, timeout=300)


def _set_action_evidence(job, result):
    for bucket, default_type in (
        ("primaryEvidence", "primary-action"),
        ("independentEvidence", "independent-readback"),
        ("stabilityEvidence", "stability-readback"),
    ):
        raw = result.get(bucket)
        if raw in (None, "", False):
            continue
        items = raw if isinstance(raw, list) else [raw]
        normalized = []
        for item in items:
            if isinstance(item, dict):
                evidence = dict(item)
            else:
                evidence = {"value": item}
            evidence.setdefault("type", default_type)
            # Preserve evidence-level verification. The aggregate result may be
            # false while a primary observation is still valid, or true while a
            # diagnostic item remains explicitly unverified.
            evidence.setdefault("verified", bool(result.get("verified")))
            normalized.append(evidence)
        job[bucket] = []
        for evidence in normalized:
            add_evidence(job, bucket, evidence)


def schedule_job_retry(job, reason):
    attempt = max(1, int(job.get("attempt", 1)))
    delay = min(300, max(5, 2 ** min(attempt, 7)))
    next_at = utc_now() + dt.timedelta(seconds=delay)
    job["retry"] = {
        "attempt": attempt,
        "delaySeconds": delay,
        "nextAt": next_at.isoformat().replace("+00:00", "Z"),
        "reason": reason,
    }
    return job["retry"]


def advance_job_strategy(job):
    current = job.get("currentStrategy") or job.get("strategy")
    try:
        index = ACTION_STRATEGIES.index(current)
    except ValueError:
        index = -1
    if index + 1 < len(ACTION_STRATEGIES):
        job["currentStrategy"] = ACTION_STRATEGIES[index + 1]
        job["strategy"] = ACTION_STRATEGIES[index + 1]
        return ACTION_STRATEGIES[index + 1]
    job["strategyExhausted"] = True
    return current


def mark_strategy_failure(job, reason):
    failed_strategy = job.get("currentStrategy") or job.get("strategy")
    strategy = advance_job_strategy(job)
    if job.get("strategyExhausted"):
        job["state"] = "failed_permanently"
        job["nextAction"] = None
        job["retry"] = {
            "attempt": int(job.get("attempt", 1)),
            "nextAt": None,
            "reason": "strategies-exhausted",
        }
    else:
        if reason == "action-failed":
            job["state"] = "recovering"
            job["nextAction"] = "retry-or-switch-strategy"
        else:
            job["state"] = "checkpointed"
            job["nextAction"] = "recover-verification"
    job.setdefault("strategyFailures", []).append(
        {
            "strategy": failed_strategy,
            "nextStrategy": strategy,
            "reason": reason,
            "at": iso_now(),
        }
    )
    return strategy


def classify_recovery_state(error):
    """Map an evidenced failure to a persisted wait state for automatic recovery."""
    details = getattr(error, "details", {}) or {}
    code = str(details.get("errorCode", "")).lower()
    text = str(error).lower()
    combined = code + " " + text
    if any(token in combined for token in (
        "network", "timeout", "timed out", "dns", "tls", "connection", "broker_unavailable",
    )):
        return "waiting_for_network"
    if any(token in combined for token in (
        "installer", "package_installer", "system_ui", "ui_pending", "permission_dialog",
    )):
        return "waiting_for_system_ui"
    if any(token in combined for token in (
        "credential", "authentication", "unauthorized", "login", "2fa", "mfa", "password",
    )):
        return "waiting_for_credential"
    if any(token in combined for token in (
        "external_event", "user_action", "awaiting_user", "device_confirmation",
    )):
        return "waiting_for_external_event"
    if any(token in combined for token in (
        "alternative", "source_exhausted", "unsupported", "no_compatible_route",
    )):
        return "waiting_for_alternative"
    return None


def apply_recovery_state(job, error, default_action):
    state = classify_recovery_state(error)
    if not state or job.get("strategyExhausted"):
        return None
    job["state"] = state
    job["waitingReason"] = str(getattr(error, "details", {}).get("errorCode", "transient_failure"))
    job["nextAction"] = default_action
    job["retry"]["state"] = state
    return state


def execute_action_job(job, context):
    with job_execution_lock(context["root"], job["id"]):
        return _execute_action_job_locked(job, context)


def _goal_app_action_args(goal):
    target = str(goal.get("target") or "").strip()
    if not target:
        raise CommandFailure("application target is required", code=2)
    args = ["action", target, "--operation", str(goal.get("operation") or "click")]
    package = str(goal.get("package") or "").strip()
    if package:
        args.extend(["--package", package])
    selector = goal.get("selector")
    if selector:
        args.extend(["--selector", json.dumps(selector, separators=(",", ":"))])
    for key, option in (
        ("text", "--text"),
        ("key", "--key"),
        ("actionId", "--action-id"),
        ("timeoutMs", "--timeout-ms"),
        ("pollMs", "--poll-ms"),
        ("afterTimeoutMs", "--after-timeout-ms"),
        ("x", "--x"),
        ("y", "--y"),
        ("x1", "--x1"),
        ("y1", "--y1"),
        ("x2", "--x2"),
        ("y2", "--y2"),
        ("durationMs", "--duration-ms"),
    ):
        if key in goal and goal[key] is not None:
            args.extend([option, str(goal[key])])
    if goal.get("direction"):
        args.extend(["--direction", str(goal["direction"])])
    if goal.get("afterSelector"):
        args.extend(
            [
                "--after-selector",
                json.dumps(goal["afterSelector"], separators=(",", ":")),
            ]
        )
    if goal.get("openIfNeeded"):
        args.append("--open-if-needed")
    return args


def _goal_adapter(target, package="", context=None):
    requested = package or target
    try:
        adapter = get_app_adapter(target)
        if package and package not in adapter.get("packageAliases", []):
            return dynamic_app_adapter(package)
        return adapter
    except CommandFailure:
        if context is not None:
            return resolve_app_adapter(requested, context)
        return dynamic_app_adapter(requested)


def _execute_normalized_goal(goal, context):
    action = goal.get("action")
    if action == "sequence":
        return _execute_sequence_goal(goal, context)
    if action == "media.play":
        return handle_media(
            [
                "play",
                "--app",
                goal.get("target", "youtube_music"),
                "--query",
                goal.get("query", ""),
            ],
            context,
        )
    if action == "app.open":
        return handle_app(["open", goal.get("target", "")], context)
    if action == "app.action":
        return handle_app(_goal_app_action_args(goal), context)
    if action == "app.inspect":
        package = goal.get("package") or goal.get("target", "")
        adapter = _goal_adapter(goal.get("target", ""), package, context)
        return automation_broker_request(
            context["root"],
            {
                "jobId": context.get("job_id"),
                "action": "app.inspect",
                "arguments": {
                    "adapter": adapter,
                    "expectedPackage": package,
                    "fact": goal.get("fact", "ui"),
                    "openIfNeeded": True,
                },
            },
            context["test_mode"],
        )
    if action == "browser.navigate":
        return handle_browser(["navigate", goal.get("query", "")], context)
    if action == "browser.inspect":
        return handle_browser(
            ["inspect", "--package", goal.get("package", "")], context
        )
    if action == "ui.goal":
        return automation_broker_request(
            context["root"],
            {
                "jobId": context.get("job_id"),
                "action": "ui.goal",
                "arguments": {"goal": goal},
            },
            context["test_mode"],
        )
    raise CommandFailure("unsupported normalized action: " + str(action), code=3)


def _sequence_result(records, verified):
    primary = []
    independent = []
    stable = []
    for record in records:
        result = record.get("result") or {}
        for source, destination in (
            ("primaryEvidence", primary),
            ("independentEvidence", independent),
            ("stabilityEvidence", stable),
        ):
            raw = result.get(source)
            if raw is None:
                continue
            destination.extend(raw if isinstance(raw, list) else [raw])
    return command_result(
        verified=bool(verified),
        sequence=records,
        primaryEvidence=primary,
        independentEvidence=independent,
        stabilityEvidence=stable,
    )


def _execute_sequence_goal(goal, context):
    steps = goal.get("steps") or []
    if not steps:
        raise CommandFailure(
            "sequence contains no executable steps",
            code=2,
            details={"errorCode": "empty_sequence"},
        )
    job = context.get("job")
    if not isinstance(job, dict):
        raise CommandFailure(
            "durable job context is required for a sequence",
            code=4,
            details={"errorCode": "sequence_job_context_missing"},
        )
    stored = job.get("sequenceEvidence") or []
    records_by_index = {
        int(item.get("index")): item
        for item in stored
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }
    start_index = max(0, min(int(job.get("sequenceIndex", 0)), len(steps)))
    for index in range(start_index, len(steps)):
        step = steps[index]
        job["sequenceIndex"] = index
        job["currentStep"] = "sequence:{}/{}".format(index + 1, len(steps))
        job["checkpointId"] = uuid.uuid4().hex
        job["nextAction"] = "execute-sequence-step"
        job["state"] = "checkpointed"
        save_job(context["root"], job)
        result = _execute_normalized_goal(step, context)
        record = {"index": index, "goal": step, "result": result}
        records_by_index[index] = record
        job["sequenceEvidence"] = [
            records_by_index[key] for key in sorted(records_by_index)
        ]
        if not result.get("verified"):
            job["state"] = "checkpointed"
            job["nextAction"] = "retry-sequence-step"
            save_job(context["root"], job)
            return _sequence_result(job["sequenceEvidence"], False)
        job["sequenceIndex"] = index + 1
        job["state"] = "checkpointed" if index + 1 < len(steps) else "running"
        save_job(context["root"], job)
    return _sequence_result(
        [records_by_index[key] for key in sorted(records_by_index)],
        len(records_by_index) == len(steps)
        and all((records_by_index[key].get("result") or {}).get("verified") for key in records_by_index),
    )


def _execute_action_job_locked(job, context):
    root = context["root"]
    if job.get("manualStop"):
        raise CommandFailure(
            "manual stop is authoritative",
            code=4,
            details={"errorCode": "manual_stop", "job": job},
        )
    goal = job.get("normalizedGoal") or {}
    goal_action = goal.get("action")
    job.setdefault("executionNonce", uuid.uuid4().hex)
    context["job_id"] = job["id"]
    context["job"] = job
    job["state"] = "running"
    job["step"] = "execute"
    job["currentStep"] = "execute"
    job["nextAction"] = "verify"
    job.setdefault("strategyHistory", []).append(
        {
            "action": "execute",
            "strategy": job.get("currentStrategy") or job.get("strategy"),
            "attempt": int(job.get("attempt", 1)),
            "at": iso_now(),
        }
    )
    write_active_job_binding(root, job, "running")
    save_job(root, job)
    try:
        result = _execute_normalized_goal(goal, context)
    except CommandFailure as exc:
        if goal_action == "ui.goal":
            error = {
                "errorCode": exc.details.get("errorCode", "native_route_unavailable"),
                "message": str(exc),
                "details": exc.details,
                "at": iso_now(),
            }
            job["lastError"] = error
            persist_model_continuation(job, "native-route-unavailable", error)
            save_job(root, job)
            return command_result(
                jobId=job["id"],
                job=job,
                verified=False,
                status="waiting_for_alternative",
                continuationRequired=job.get("continuationRequired"),
            )
        schedule_job_retry(job, "action-failed")
        mark_strategy_failure(job, "action-failed")
        apply_recovery_state(job, exc, "resume-after-wait")
        if job.get("strategyExhausted"):
            job["retry"]["nextAt"] = None
        job["lastError"] = {
            "errorCode": exc.details.get("errorCode", "action_failed"),
            "message": str(exc),
            "details": exc.details,
            "at": iso_now(),
        }
        save_job(root, job)
        raise
    _set_action_evidence(job, result)
    job["step"] = "independent_verification"
    job["currentStep"] = "independent_verification"
    if result.get("verified"):
        try:
            verified_job = verify_job(root, job)
            verified_job["nextAction"] = None
            verified_job["retry"] = {"attempt": int(job.get("attempt", 1)), "nextAt": None}
            verified_job = save_job(root, verified_job)
            return command_result(
                jobId=job["id"],
                job=verified_job,
                result=result,
                verified=True,
                evidence=str(root / "evidence" / (job["id"] + ".json")),
            )
        except CommandFailure as exc:
            schedule_job_retry(job, "verification-failed")
            mark_strategy_failure(job, "verification-failed")
            apply_recovery_state(job, exc, "resume-after-wait")
            if job.get("strategyExhausted"):
                job["retry"]["nextAt"] = None
            job["lastError"] = {
                "errorCode": exc.details.get("errorCode", "verification_failed"),
                "message": str(exc),
                "details": exc.details,
                "at": iso_now(),
            }
    else:
        schedule_job_retry(job, "goal-not-verified")
        mark_strategy_failure(job, "goal-not-verified")
        if job.get("strategyExhausted"):
            job["retry"]["nextAt"] = None
    save_job(root, job)
    return command_result(
        jobId=job["id"],
        job=job,
        result=result,
        verified=False,
    )


def handle_ocr(args, context):
    if not args:
        raise CommandFailure("usage: codex-ocr <image> [language]", code=2)
    language = args[1] if len(args) > 1 else "eng"
    result = run_process(["tesseract", args[0], "stdout", "-l", language], timeout=180)
    if not result["ok"]:
        raise CommandFailure("OCR failed", result["exitCode"], result)
    return command_result(image=args[0], language=language, text=result["stdout"])


def handle_speech(args, context):
    if not args:
        raise CommandFailure("usage: codex-speech <say|listen> ...", code=2)
    if args[0] == "say":
        return run_process(["termux-tts-speak", " ".join(args[1:])], timeout=120)
    if args[0] == "listen":
        result = run_process(["termux-speech-to-text"], timeout=180)
        if not result["ok"]:
            raise CommandFailure("speech recognition failed", result["exitCode"], result)
        return command_result(text=result["stdout"].strip())
    raise CommandFailure("invalid codex-speech action", code=2)


def vault_request(root, payload, test_mode=False):
    if test_mode:
        store_path = root / "vault" / "test-store.json"
        store = load_json(store_path, {})
        action = payload["action"]
        key = payload.get("key")
        if action == "set":
            store[key] = payload.get("value", "")
            atomic_write_json(store_path, store)
            return command_result(key=key)
        if action == "get":
            if key not in store:
                raise CommandFailure("vault key not found", code=4)
            return command_result(key=key, value=store[key])
        if action == "delete":
            store.pop(key, None)
            atomic_write_json(store_path, store)
            return command_result(key=key)
        if action == "list":
            return command_result(keys=sorted(store))
    broker = load_json(root / "vault" / "broker.json", None)
    if not broker:
        raise CommandFailure("Android Keystore broker is not paired", code=5)
    request = dict(payload)
    request["token"] = broker["token"]
    response = None
    last_error = None
    for _ in range(12):
        try:
            with socket.create_connection(
                (broker.get("host", "127.0.0.1"), int(broker.get("port", 18766))),
                timeout=3,
            ) as connection:
                connection.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode())
                reader = connection.makefile("r", encoding="utf-8")
                response = json.loads(reader.readline())
            break
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.25)
    if response is None:
        raise CommandFailure("Android Keystore broker is unavailable: " + str(last_error), code=5)
    if not response.get("ok"):
        raise CommandFailure(response.get("error", "vault request failed"), code=6)
    return response


def handle_vault(args, context):
    if not args:
        raise CommandFailure("usage: codex-vault <set|get|delete|list> ...", code=2)
    action = args[0]
    if action == "set" and len(args) >= 3:
        payload = {"action": "set", "key": args[1], "value": " ".join(args[2:])}
    elif action in {"get", "delete"} and len(args) == 2:
        payload = {"action": action, "key": args[1]}
    elif action == "list":
        payload = {"action": "list"}
    else:
        raise CommandFailure("invalid codex-vault operation", code=2)
    return vault_request(context["root"], payload, context["test_mode"])


def memory_store(root):
    return root / "memory" / "entries.json"


def handle_memory(args, context):
    if not args:
        raise CommandFailure("usage: codex-memory <put|get|delete|search|list> ...", code=2)
    path = memory_store(context["root"])
    entries = load_json(path, {})
    action = args[0]
    if action == "put" and len(args) >= 3:
        entries[args[1]] = {"value": " ".join(args[2:]), "updatedAt": iso_now()}
        atomic_write_json(path, entries)
        return command_result(key=args[1])
    if action == "get" and len(args) == 2:
        if args[1] not in entries:
            raise CommandFailure("memory key not found", code=4)
        return command_result(key=args[1], **entries[args[1]])
    if action == "delete" and len(args) == 2:
        entries.pop(args[1], None)
        atomic_write_json(path, entries)
        return command_result(key=args[1])
    if action == "list":
        return command_result(keys=sorted(entries))
    if action == "search" and len(args) >= 2:
        query = " ".join(args[1:]).lower()
        matches = [
            {"key": key, **value}
            for key, value in entries.items()
            if query in key.lower() or query in value.get("value", "").lower()
        ]
        return command_result(matches=matches)
    raise CommandFailure("invalid codex-memory operation", code=2)


def schedule_store(root):
    return root / "schedules.json"


def load_schedules(root):
    return load_json(schedule_store(root), {"version": 1, "jobs": {}})


def handle_schedule(args, context):
    if not args:
        raise CommandFailure("usage: codex-schedule <add|remove|list|tick> ...", code=2)
    schedules = load_schedules(context["root"])
    action = args[0]
    if action == "add":
        positional, options = parse_options(args[1:])
        job_id = options.get("id")
        command = positional
        if not job_id or not command:
            raise CommandFailure(
                "usage: codex-schedule add --id ID --every SECONDS -- command", code=2
            )
        every = int(options.get("every", 3600))
        schedules["jobs"][job_id] = {
            "command": command,
            "everySeconds": every,
            "enabled": True,
            "nextRunAt": (utc_now() + dt.timedelta(seconds=every))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        atomic_write_json(schedule_store(context["root"]), schedules)
        return command_result(id=job_id, job=schedules["jobs"][job_id])
    if action == "remove" and len(args) == 2:
        schedules["jobs"].pop(args[1], None)
        atomic_write_json(schedule_store(context["root"]), schedules)
        return command_result(id=args[1])
    if action == "list":
        return command_result(jobs=schedules["jobs"])
    if action == "tick":
        now = utc_now()
        executed = []
        failures = {}
        for job_id, job in schedules["jobs"].items():
            if not job.get("enabled", True):
                continue
            due = parse_time(job["nextRunAt"])
            if due > now:
                continue
            code, result = run(job["command"], env=context["env"])
            executed.append(job_id)
            if code:
                failures[job_id] = result
            every = max(1, int(job.get("everySeconds", 3600)))
            job["lastRunAt"] = iso_now()
            job["lastExitCode"] = code
            job["nextRunAt"] = (now + dt.timedelta(seconds=every)).isoformat().replace(
                "+00:00", "Z"
            )
        atomic_write_json(schedule_store(context["root"]), schedules)
        return command_result(executed=executed, failures=failures)
    raise CommandFailure("invalid codex-schedule operation", code=2)


def handle_health(args, context):
    root = context["root"]
    current = root / "current"
    active_version = None
    if current.exists() or current.is_symlink():
        active_version = load_json(current / "manifest.json", {}).get("version")
    runtime_sha = None
    try:
        runtime_sha = sha256_file(pathlib.Path(__file__))
    except OSError:
        pass
    command_resolution = {
        command: shutil.which(command)
        for command in COMMANDS
    }
    missing_commands = [
        command
        for command, resolved in command_resolution.items()
        if not resolved
    ]
    active_binding = load_json(active_job_binding_path(root), {})
    runtime_verified = bool(runtime_sha) and not missing_commands
    # Test mode intentionally runs from a source checkout without the Termux
    # command-link set. Production bootstrap must fail closed instead of
    # publishing a healthy marker for a partial runtime.
    health_ok = runtime_verified or context["test_mode"]
    return command_result(
        ok=health_ok,
        marker="CODEX_CAPABILITY_RUNTIME_READY",
        verified=runtime_verified,
        runtimeVersion=VERSION,
        runtimeSha256=runtime_sha,
        activeVersion=active_version or VERSION,
        root=str(root),
        commands=len(COMMANDS),
        commandResolution=command_resolution,
        missingCommands=missing_commands,
        activeJob=active_binding,
        testMode=context["test_mode"],
        time=iso_now(),
    )


def handle_audit(args, context):
    audit_dir = context["root"] / "audit"
    receipts = sorted(audit_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if args and args[0] == "show" and len(args) > 1:
        record = load_json(audit_dir / (args[1] + ".json"), None)
        if not record:
            raise CommandFailure("audit receipt not found", code=4)
        return command_result(receipt=record)
    count = 20
    if args and args[0].isdigit():
        count = max(1, min(int(args[0]), 200))
    return command_result(
        receipts=[load_json(path, {}) for path in receipts[-count:]]
    )


def handle_undo(args, context):
    return handle_restore(args, context)


def migrate_gateway_pairing(root, context):
    candidates = [
        pathlib.Path("/sdcard/Download/codex-win-pairing.json"),
        root / "vault" / "windows-gateway.json",
    ]
    for path in candidates:
        pairing = load_json(path, None)
        if not pairing or not pairing.get("secret"):
            continue
        vault_request(
            root,
            {"action": "set", "key": "windows-gateway-secret", "value": pairing["secret"]},
            context["test_mode"],
        )
        public = {key: value for key, value in pairing.items() if key != "secret"}
        atomic_write_json(root / "vault" / "windows-gateway.json", public)
        if path != root / "vault" / "windows-gateway.json":
            try:
                path.unlink()
            except OSError:
                pass
        return public
    return None


def windows_gateway_request(payload, context, timeout=60, retries=1):
    config_path = context["root"] / "vault" / "windows-gateway.json"
    config = load_json(config_path, None)
    try:
        secret = vault_request(
            context["root"],
            {"action": "get", "key": "windows-gateway-secret"},
            context["test_mode"],
        )["value"]
    except CommandFailure:
        config = migrate_gateway_pairing(context["root"], context) or config
        secret = vault_request(
            context["root"],
            {"action": "get", "key": "windows-gateway-secret"},
            context["test_mode"],
        )["value"]
    if not config:
        raise CommandFailure("Windows gateway is not paired", code=5)
    payload = dict(payload)
    payload.setdefault("requestId", uuid.uuid4().hex)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    attempts = []
    result = None
    for attempt in range(1, max(1, min(int(retries), 3)) + 1):
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        signature = sign_gateway_request(secret, timestamp, nonce, body)
        request = urllib.request.Request(
            "http://{}:{}/".format(config["host"], config.get("port", 18765)),
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Codex-Timestamp": timestamp,
                "X-Codex-Nonce": nonce,
                "X-Codex-Signature": signature,
            },
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=int(timeout)) as response:
                result = json.loads(response.read().decode("utf-8"))
            attempts.append({"attempt": attempt, "ok": True, "latencyMs": round((time.monotonic() - started) * 1000)})
            break
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace")
            raise CommandFailure(
                "Windows gateway rejected request",
                code=exc.code,
                details={"response": body_text, "attempts": attempts},
            )
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            attempts.append({"attempt": attempt, "ok": False, "error": exc.__class__.__name__, "latencyMs": round((time.monotonic() - started) * 1000)})
            if attempt >= max(1, min(int(retries), 3)):
                raise CommandFailure(
                    "Windows gateway unavailable after bounded retries: " + str(exc),
                    code=5,
                    details={"attempts": attempts, "host": config.get("host"), "port": config.get("port")},
                )
            time.sleep(0.25 * attempt)
    if not isinstance(result, dict):
        raise CommandFailure("invalid Windows gateway response", code=7, details={"attempts": attempts})
    if not result.get("ok"):
        raise CommandFailure(result.get("error", "Windows action failed"), details=result)
    result.setdefault("gateway", {})
    if isinstance(result["gateway"], dict):
        result["gateway"].update({
            "transport": config.get("transport", "direct"),
            "host": config.get("host"),
            "port": config.get("port", 18765),
            "attempts": attempts,
        })
    return result


def handle_win(args, context):
    positional, options = parse_options(args)
    if positional:
        try:
            payload = json.loads(" ".join(positional))
        except json.JSONDecodeError:
            payload = {"action": positional[0], "arguments": positional[1:]}
    else:
        payload = {"action": "status"}
    action = str(payload.get("action", "")).lower()
    retries = 3 if action in {"status", "diagnostics", "health"} else 1
    result = windows_gateway_request(
        payload,
        context,
        timeout=int(options.get("timeout", 60)),
        retries=retries,
    )
    if action in {"status", "diagnostics", "health"}:
        result["verified"] = True
    return result


GITHUB_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:token|bearer)\s+)[^\s\"']+"),
    re.compile(r"(?i)\b(?:gh[opusr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(?:gh[opusr]_\*{8,}|github_pat_\*{8,})"),
)


def redact_github_secrets(value):
    if isinstance(value, dict):
        return {key: redact_github_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_github_secrets(item) for item in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in GITHUB_SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", redacted)
    return redacted


def github_delegation_script(tool, arguments):
    encoded = base64.b64encode(json.dumps(arguments).encode("utf-8")).decode("ascii")
    executable = "gh.exe" if tool == "gh" else "git.exe"
    return r'''$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$argvJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))
$toolArgs = @(ConvertFrom-Json $argvJson)
$toolPath = (Get-Command '%s' -ErrorAction Stop).Source
$output = & $toolPath @toolArgs 2>&1 | Out-String
$exitCode = $LASTEXITCODE
@{ ok = ($exitCode -eq 0); tool = '%s'; exitCode = $exitCode; output = $output.TrimEnd() } | ConvertTo-Json -Compress -Depth 6
''' % (encoded, executable, tool)


def handle_github(args, context):
    if not args:
        raise CommandFailure("usage: codex-github <status|gh|git> [arguments...]", code=2)
    action = args[0].lower()
    if action == "status":
        tool = "gh"
        tool_args = ["auth", "status", "--hostname", "github.com"]
    elif action in {"gh", "git"}:
        tool = action
        tool_args = args[1:]
        lowered = [item.lower() for item in tool_args]
        if tool == "gh" and (
            lowered[:2] == ["auth", "token"]
            or "--show-token" in lowered
            or (lowered[:2] == ["auth", "status"] and "-t" in lowered)
        ):
            raise CommandFailure("credential-exporting GitHub CLI commands are blocked; use codex-github status", code=4)
    else:
        raise CommandFailure("usage: codex-github <status|gh|git> [arguments...]", code=2)
    payload = {
        "action": "powershell",
        "script": github_delegation_script(tool, tool_args),
        "timeoutSeconds": 180,
    }
    response = windows_gateway_request(payload, context, timeout=190, retries=1)
    safe = redact_github_secrets(response)
    safe["credentialStorage"] = "Windows GitHub CLI credential store and environment; no credential copied to Android"
    safe["verified"] = bool(safe.get("ok"))
    return safe


def handle_goal(args, context):
    positional, options = parse_options(args)
    if not positional:
        raise CommandFailure("usage: codex-goal <request> [--required-facts JSON]", code=2)
    contract = new_goal_contract(" ".join(positional), options)
    return command_result(goal=contract)


def handle_job(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-job <create|inspect|checkpoint|verify|stop|abandon|resume|continue|next-action|list>",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    root = context["root"]
    job_id = options.get("id") or (positional[0] if positional else None)
    if action == "create":
        job_id = options.get("id")
        if not job_id:
            raise CommandFailure("codex-job create requires --id ID", code=2)
        text = " ".join(positional)
        if not text:
            raise CommandFailure("codex-job create requires a request", code=2)
        return command_result(job=create_job(root, job_id, text, options))
    if action == "list":
        jobs = []
        quarantined = []
        for path in sorted((root / "jobs").glob("*.json")):
            if not path.is_file():
                continue
            try:
                jobs.append(load_job(root, path.stem))
            except CommandFailure as exc:
                if exc.details.get("errorCode") == "corrupt_job_record":
                    quarantined.append({"id": path.stem, **exc.details})
                    continue
                raise
        return command_result(jobs=jobs, quarantined=quarantined)
    if action == "next-action":
        binding = load_json(active_job_binding_path(root), None)
        if not isinstance(binding, dict) or not binding.get("jobId"):
            return command_result(
                active=False,
                status="no_active_job",
                nextAction=None,
                manualActionRequired=False,
            )
        active_id = str(binding.get("jobId"))
        job = load_job(root, active_id)
        binding_nonce = str(binding.get("executionNonce") or "")
        job_nonce = str(job.get("executionNonce") or "")
        if binding_nonce and job_nonce and binding_nonce != job_nonce:
            return command_result(
                active=False,
                status="stale_binding",
                errorCode="active_job_binding_mismatch",
                jobId=active_id,
                binding=binding,
                jobState=job.get("state"),
                manualStop=bool(job.get("manualStop")),
                manualActionRequired=False,
            )
        state = str(job.get("state") or "")
        manual_stop = bool(job.get("manualStop")) or state == "manual_stop"
        terminal = state in {"verified", "abandoned", "failed_permanently"}
        continuation = job.get("continuationRequired")
        if manual_stop:
            status = "manual_stop"
        elif terminal:
            status = state
        elif isinstance(continuation, dict):
            status = "continuation_required"
        else:
            status = "active"
        return command_result(
            active=not manual_stop and not terminal,
            status=status,
            jobId=active_id,
            state=state,
            currentStep=job.get("currentStep"),
            currentStrategy=job.get("currentStrategy") or job.get("strategy"),
            nextAction=job.get("nextAction"),
            originalRequest=job.get("originalRequest") or job.get("request"),
            normalizedGoal=job.get("normalizedGoal"),
            continuationRequired=continuation,
            strategyFailures=job.get("strategyFailures", [])[-8:],
            lastError=job.get("lastError"),
            attempt=job.get("attempt", 0),
            manualStop=manual_stop,
            manualActionRequired=bool(continuation) and not manual_stop and not terminal,
            continuationCommand=(
                "codex-job continue --id {} --request <concrete verifiable action>".format(active_id)
                if isinstance(continuation, dict) and not manual_stop and not terminal
                else None
            ),
            job=job,
            binding=binding,
        )
    if action == "resume-all":
        stale_after_seconds = max(
            0,
            int(options.get("stale-after-seconds", 60)),
        )
        now = utc_now()
        resumed = []
        skipped = []
        for path in sorted((root / "jobs").glob("*.json")):
            try:
                job = load_job(root, path.stem)
            except CommandFailure as exc:
                if exc.details.get("errorCode") == "corrupt_job_record":
                    skipped.append(
                        {
                            "id": path.stem,
                            "state": "quarantined",
                            "reason": exc.details,
                        }
                    )
                    continue
                raise
            if not job:
                continue
            if job.get("manualStop"):
                skipped.append(
                    {
                        "id": job.get("id"),
                        "state": job.get("state"),
                        "reason": "manual-stop-authoritative",
                    }
                )
                continue
            if job.get("state") in {"verified", "abandoned", "failed_permanently"}:
                continue
            try:
                age_seconds = max(
                    0.0,
                    (now - parse_time(job.get("updatedAt"))).total_seconds(),
                )
            except (AttributeError, TypeError, ValueError):
                age_seconds = float("inf")
            if age_seconds < stale_after_seconds:
                skipped.append(
                    {
                        "id": job.get("id"),
                        "state": job.get("state"),
                        "ageSeconds": age_seconds,
                    }
                )
                continue
            retry = job.get("retry") or {}
            next_at = retry.get("nextAt")
            if next_at:
                try:
                    if parse_time(next_at) > now:
                        skipped.append(
                            {
                                "id": job.get("id"),
                                "state": job.get("state"),
                                "ageSeconds": age_seconds,
                                "nextAt": next_at,
                                "reason": "retry-not-due",
                            }
                        )
                        continue
                except (TypeError, ValueError):
                    job.setdefault("lastError", {})["errorCode"] = "invalid_retry_schedule"
            job["state"] = "recovering"
            job["attempt"] = int(job.get("attempt", 0)) + 1
            job["nextAction"] = "continue"
            job.setdefault("strategyHistory", []).append(
                {"action": "resume-all", "at": iso_now(), "attempt": job["attempt"]}
            )
            if not context["test_mode"] and is_runtime_action_job(job):
                try:
                    resumed.append(execute_action_job(job, context))
                except CommandFailure as exc:
                    resumed.append(
                        command_result(
                            jobId=job.get("id"),
                            verified=False,
                            errorCode=exc.details.get("errorCode", "resume_failed"),
                            message=str(exc),
                            job=load_job(root, job.get("id")),
                        )
                        )
            elif is_model_orchestrated_job(job):
                persist_model_continuation(job, "stale-job-recovery")
                resumed.append(
                    command_result(
                        jobId=job.get("id"),
                        state="recovering",
                        attempt=int(job.get("attempt", 1)),
                        verified=False,
                        status="waiting_for_alternative",
                        continuationRequired=job.get("continuationRequired"),
                        job=save_job(root, job),
                    )
                )
            else:
                resumed.append(save_job(root, job))
        return command_result(
            resumed=resumed,
            skipped=skipped,
            count=len(resumed),
            staleAfterSeconds=stale_after_seconds,
        )
    if not job_id:
        raise CommandFailure("job id is required", code=2)
    job = load_job(root, job_id)
    if action == "inspect":
        return command_result(job=job)
    if action in {"resume", "recover"}:
        if job.get("manualStop"):
            raise CommandFailure(
                "manual stop is authoritative",
                code=4,
                details={"errorCode": "manual_stop"},
            )
        job["state"] = "recovering" if action == "recover" else "running"
        job["attempt"] = int(job.get("attempt", 0)) + 1
        job["nextAction"] = "continue"
        job.setdefault("strategyHistory", []).append(
            {"action": action, "at": iso_now(), "attempt": job["attempt"]}
        )
        if is_runtime_action_job(job):
            return execute_action_job(job, context)
        persist_model_continuation(job, action + "-model-continuation")
        return command_result(
            jobId=job.get("id"),
            verified=False,
            status="waiting_for_alternative",
            continuationRequired=job.get("continuationRequired"),
            job=save_job(root, job),
        )
    if action == "continue":
        if job.get("manualStop"):
            raise CommandFailure("manual stop is authoritative", code=4)
        if job.get("state") in {"verified", "abandoned", "failed_permanently"}:
            raise CommandFailure(
                "cannot continue a terminal job",
                code=4,
                details={"errorCode": "terminal_job", "state": job.get("state")},
            )
        raw_goal = options.get("goal-json")
        continuation_goal = parse_json_option(options, "goal-json") if raw_goal is not None else None
        continuation_request = str(options.get("request") or "").strip()
        if continuation_goal is None and not continuation_request:
            remaining = list(positional)
            if remaining and str(remaining[0]) == str(job_id):
                remaining = remaining[1:]
            continuation_request = " ".join(remaining).strip()
        if continuation_goal is not None:
            if not isinstance(continuation_goal, dict) or not continuation_goal.get("action"):
                raise CommandFailure(
                    "--goal-json must be a normalized action object",
                    code=2,
                    details={"errorCode": "invalid_continuation_goal"},
                )
            normalized = continuation_goal
            continuation_request = str(
                continuation_goal.get("request") or continuation_request or job.get("originalRequest") or ""
            )
        else:
            if not continuation_request:
                raise CommandFailure(
                    "codex-job continue requires --request or --goal-json",
                    code=2,
                )
            normalized = normalize_action_goal(continuation_request)
        job["normalizedGoal"] = normalized
        job["executionMode"] = (
            "runtime-action" if normalized.get("action") != "ui.goal" else "model-orchestrated"
        )
        job["currentStrategy"] = ACTION_STRATEGIES[0]
        job["strategy"] = ACTION_STRATEGIES[0]
        job.pop("strategyExhausted", None)
        job["state"] = "running"
        job["currentStep"] = "model-continuation"
        job["nextAction"] = "execute"
        job["lastError"] = None
        job["retry"] = {"attempt": int(job.get("attempt", 0)), "nextAt": None}
        job.setdefault("continuationHistory", []).append(
            {
                "request": continuation_request,
                "action": normalized.get("action"),
                "at": iso_now(),
            }
        )
        job.pop("continuationRequired", None)
        save_job(root, job)
        if context["test_mode"]:
            return command_result(
                jobId=job.get("id"),
                verified=False,
                status="completed_unverified",
                job=job,
            )
        return execute_action_job(job, context)
    if action == "checkpoint":
        if job.get("manualStop"):
            raise CommandFailure("manual stop is authoritative", code=4)
        job["state"] = "checkpointed"
        job["checkpointId"] = uuid.uuid4().hex
        job["currentStep"] = options.get("step", "checkpoint")
        job["currentStrategy"] = options.get("strategy", job.get("currentStrategy"))
        for key, bucket in (
            ("primary", "primaryEvidence"),
            ("independent", "independentEvidence"),
            ("stable", "stabilityEvidence"),
        ):
            if key in options:
                add_evidence(job, bucket, options[key])
        return command_result(job=save_job(root, job))
    if action == "verify":
        verified = verify_job(root, job)
        return command_result(
            verified=True,
            job=verified,
            evidence=str(root / "evidence" / (job["id"] + ".json")),
        )
    if action == "stop":
        job["manualStop"] = True
        job["state"] = "manual_stop"
        job["nextAction"] = None
        saved = save_job(root, job)
        write_active_job_binding(root, saved, "manual_stop")
        return command_result(job=saved)
    if action == "abandon":
        job["state"] = "abandoned"
        job["nextAction"] = None
        job["abandonmentReason"] = " ".join(positional[1:] if positional else [])
        saved = save_job(root, job)
        write_active_job_binding(root, saved, "abandoned")
        return command_result(job=saved)
    raise CommandFailure("invalid codex-job action", code=2)


def handle_capability(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-capability <list|search|register|acquire|install|verify|health|update|rollback|quarantine|remove>",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    root = context["root"]
    if action == "list":
        return command_result(capabilities=load_capabilities(root))
    if action == "search":
        query = options.get("query") or " ".join(positional).strip()
        if not query:
            raise CommandFailure("capability search query is required", code=2)
        return handle_search([query], context)
    name = options.get("name") or (positional[0] if positional else None)
    if not name:
        raise CommandFailure("capability name is required", code=2)
    path = capability_path(root, name)
    capability = load_json(path, None)
    if action == "register":
        capability = {
            "name": name,
            "purpose": options.get("purpose", ""),
            "platform": options.get("platform", "android-termux"),
            "version": options.get("version", "unknown"),
            "source": options.get("source", "user-directed"),
            "provenance": options.get("provenance", options.get("source", "unknown")),
            "checksum": options.get("sha256"),
            "signature": options.get("signature"),
            "permissions": parse_json_option(options, "permissions", []),
            "commands": parse_json_option(options, "commands", []),
            "healthCheck": options.get("health-command"),
            "healthReadback": options.get("health-readback"),
            "health": "unknown",
            "status": "installed",
            "registeredAt": iso_now(),
            "updatedAt": iso_now(),
        }
        history = preserve_capability_version(root, capability if path.exists() else None)
        atomic_write_json(path, capability)
        return command_result(capability=capability, previousVersion=history)
    if action == "acquire":
        acquisition_args = list(positional[1:] if positional and positional[0] == name else positional)
        if options.get("url"):
            acquisition_args.insert(0, options["url"])
        if not acquisition_args:
            raise CommandFailure("capability acquisition URL is required", code=2)
        result = handle_acquire(acquisition_args, context)
        return command_result(capability=name, acquisition=result)
    if not capability:
        raise CommandFailure("capability not found: " + name, code=4)
    if action in {"install", "update"}:
        artifact = options.get("artifact") or (positional[1] if len(positional) > 1 else None)
        if not artifact:
            raise CommandFailure("capability artifact is required", code=2)
        previous = preserve_capability_version(root, capability)
        install_result = install_artifact(artifact, context, replace=True)
        capability["status"] = "installed"
        capability["health"] = "unknown"
        capability["updatedAt"] = iso_now()
        capability["artifact"] = str(artifact)
        if options.get("version"):
            capability["version"] = options["version"]
        if options.get("sha256"):
            capability["checksum"] = options["sha256"]
        atomic_write_json(path, capability)
        return command_result(
            capability=capability,
            install=install_result,
            previousVersion=previous,
            updated=action == "update",
        )
    if action == "rollback":
        history_dir = pathlib.Path(root) / "capabilities" / "history"
        candidates = sorted(history_dir.glob(re.sub(r"[^A-Za-z0-9._-]", "_", str(name)) + "-*.json"))
        if not candidates:
            raise CommandFailure("no capability rollback version available", code=4)
        previous = preserve_capability_version(root, capability)
        restored = load_json(candidates[-1], None)
        if not restored:
            raise CommandFailure("capability rollback record is corrupt", code=6)
        restored["status"] = "installed"
        restored["rolledBackAt"] = iso_now()
        atomic_write_json(path, restored)
        return command_result(capability=restored, rollbackSource=str(candidates[-1]), previousVersion=previous)
    if action in {"quarantine", "remove"}:
        destination = quarantine_path(root, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        return command_result(
            capability=name,
            status="quarantined",
            quarantinePath=str(destination),
            removed=action == "remove",
        )
    if action in {"verify", "health"}:
        health_command = capability.get("healthCheck")
        if not health_command:
            raise CommandFailure(
                "capability has no health check",
                code=4,
                details={"errorCode": "health_check_missing"},
            )
        if context["test_mode"]:
            return command_result(
                capability=capability,
                verified=False,
                reason="test mode does not execute capability health checks",
            )
        try:
            executable = shlex.split(health_command)[0]
        except (IndexError, ValueError):
            executable = ""
        readback_command = capability.get("healthReadback") or (
            "command -v " + shlex.quote(executable) if executable else ""
        )
        if not readback_command:
            raise CommandFailure(
                "capability independent health readback is unavailable",
                code=4,
                details={"errorCode": "health_readback_missing"},
            )
        primary = run_process(["bash", "-lc", health_command], timeout=120)
        independent = run_process(["bash", "-lc", readback_command], timeout=120)
        verified = primary["ok"] and independent["ok"] and bool(independent.get("stdout", "").strip())
        capability["health"] = "healthy" if verified else "unhealthy"
        capability["lastHealthCheckAt"] = iso_now()
        atomic_write_json(path, capability)
        return command_result(
            capability=capability,
            verified=verified,
            primaryEvidence={
                "type": "health-command",
                "verified": primary["ok"],
                "result": primary,
            },
            independentEvidence={
                "type": "capability-command-resolution",
                "command": readback_command,
                "verified": independent["ok"],
                "result": independent,
            },
        )
    raise CommandFailure("invalid codex-capability action", code=2)


def handle_verify(args, context):
    if not args:
        raise CommandFailure("usage: codex-verify <file|package|job> ...", code=2)
    action = args[0]
    positional, options = parse_options(args[1:])
    if action == "file" and positional:
        result = inspect_artifact(positional[0])
        expected = options.get("sha256")
        if expected and result["sha256"].lower() != expected.lower():
            raise CommandFailure(
                "file checksum mismatch",
                code=6,
                details={"errorCode": "checksum_mismatch", **result},
            )
        return command_result(verified=True, primaryEvidence=result, independentEvidence={
            "type": "filesystem-readback",
            "path": result["path"],
            "bytes": result["bytes"],
        }, **result)
    if action == "package" and positional:
        expected_version = options.get("version")
        context["expected_version"] = expected_version
        result = package_inspection(positional[0], context)
        if context["test_mode"]:
            return command_result(
                verified=False,
                package=positional[0],
                version=result.get("version"),
                reason="test mode has no real package-manager readback",
            )
        stable = package_inspection(positional[0], context)
        verified = result.get("path") == stable.get("path") and result.get(
            "version"
        ) == stable.get("version")
        return command_result(
            verified=verified,
            primaryEvidence={"type": "pm-path", "verified": verified, **result},
            independentEvidence={
                "type": "dumpsys-package",
                "verified": verified,
                "package": positional[0],
                "version": result.get("version"),
            },
            stabilityEvidence={
                "type": "repeat-package-readback",
                "verified": verified,
                "package": positional[0],
                "path": stable.get("path"),
                "version": stable.get("version"),
            },
            **result,
        )
    if action == "job" and positional:
        job = verify_job(context["root"], load_job(context["root"], positional[0]))
        return command_result(verified=True, job=job)
    raise CommandFailure("invalid codex-verify action", code=2)


def handle_recover(args, context):
    if not args:
        raise CommandFailure("usage: codex-recover <job-id>", code=2)
    job = load_job(context["root"], args[0])
    if job.get("manualStop"):
        return command_result(
            recovered=False,
            errorCode="manual_stop",
            nextAction=None,
            job=job,
        )
    job["state"] = "recovering"
    job["attempt"] = int(job.get("attempt", 0)) + 1
    job["nextAction"] = "switch-strategy"
    job["strategyHistory"].append(
        {"action": "recovery", "at": iso_now(), "attempt": job["attempt"]}
    )
    if is_runtime_action_job(job):
        return execute_action_job(job, context)
    persist_model_continuation(job, "explicit-recovery")
    return command_result(
        recovered=True,
        verified=False,
        status="waiting_for_alternative",
        continuationRequired=job.get("continuationRequired"),
        job=save_job(context["root"], job),
    )


def handle_artifact(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-artifact <fetch|download|inspect|hash|sign-check|stage|activate|quarantine|restore>",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    if action in {"fetch", "download"}:
        if not positional:
            raise CommandFailure("artifact URL is required", code=2)
        download_args = [positional[0]]
        for key in ("output", "sha256", "retries"):
            if options.get(key) is not None:
                download_args.extend(["--" + key, str(options[key])])
        return handle_download(download_args, context)
    if action in {"stage", "quarantine"} and not positional:
        raise CommandFailure("artifact path is required", code=2)
    if action in {"activate", "restore"} and not positional:
        raise CommandFailure("artifact id is required", code=2)
    if action in {"inspect", "hash", "sign-check", "stage", "quarantine"}:
        target = canonical_path(positional[0])
    else:
        target = None
    if action in {"inspect", "hash"}:
        result = inspect_artifact(target)
        return result if action == "inspect" else command_result(
            verified=True, path=result["path"], sha256=result["sha256"]
        )
    if action == "sign-check":
        result = inspect_artifact(target)
        if target.suffix.lower() != ".apk":
            raise CommandFailure(
                "sign-check currently requires an APK",
                code=2,
                details={"errorCode": "sign_check_type_unsupported"},
            )
        metadata = inspect_apk_metadata(target, context)
        verified = bool(metadata.get("signatureVerified"))
        return command_result(
            verified=verified,
            path=result["path"],
            sha256=result["sha256"],
            signer=metadata.get("signer"),
            signatureVerified=verified,
            primaryEvidence={"type": "apk-signature-inspection", "verified": verified, **metadata},
            independentEvidence={"type": "artifact-hash", "verified": True, "sha256": result["sha256"]},
        )
    if action == "stage":
        return stage_artifact(context["root"], target, options.get("id"))
    if action == "activate":
        activation_target = options.get("target")
        if not activation_target:
            raise CommandFailure(
                "artifact activation requires --target",
                code=2,
                details={"errorCode": "artifact_activation_target_missing"},
            )
        return activate_staged_artifact(context["root"], positional[0], activation_target)
    if action == "restore":
        return restore_staged_artifact(context["root"], positional[0])
    if action == "quarantine":
        if not target.exists():
            raise CommandFailure("artifact does not exist", code=4)
        destination = quarantine_path(context["root"], target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(destination))
        return command_result(quarantinePath=str(destination), originalPath=str(target))
    raise CommandFailure("invalid codex-artifact action", code=2)


def handle_package(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-package <inspect|install|update|rollback|launch|verify>",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    if not positional:
        raise CommandFailure("package or artifact is required", code=2)
    if action == "inspect":
        context["expected_version"] = options.get("version")
        return command_result(**package_inspection(positional[0], context))
    if action == "verify":
        context["expected_version"] = options.get("version")
        result = package_inspection(positional[0], context)
        if context["test_mode"]:
            return command_result(
                verified=False,
                package=positional[0],
                version=result.get("version"),
                reason="test mode has no real package-manager readback",
            )
        stable = package_inspection(positional[0], context)
        verified = result.get("path") == stable.get("path") and result.get(
            "version"
        ) == stable.get("version")
        return command_result(
            verified=verified,
            package=positional[0],
            version=result.get("version"),
            primaryEvidence={"type": "pm-path", "verified": verified, **result},
            independentEvidence={
                "type": "dumpsys-package",
                "verified": verified,
                "package": positional[0],
                "version": result.get("version"),
            },
            stabilityEvidence={
                "type": "repeat-package-readback",
                "verified": verified,
                "package": positional[0],
                "path": stable.get("path"),
                "version": stable.get("version"),
            },
        )
    if action in {"install", "update", "rollback"}:
        context["expected_package"] = options.get("package")
        if action == "rollback" and not context["expected_package"] and options.get("artifact"):
            context["expected_package"] = positional[0]
        target_value = options.get("artifact") or positional[0]
        if action == "rollback" and not options.get("artifact"):
            raise CommandFailure(
                "package rollback requires --artifact with the preserved APK or split set",
                code=2,
                details={"errorCode": "package_rollback_artifact_missing"},
            )
        target = canonical_path(target_value)
        artifact_inspection = validate_apk_install_options(target, options, context)
        if artifact_inspection and artifact_inspection.get("available") and not context.get("expected_package"):
            context["expected_package"] = artifact_inspection.get("package")
        result = install_artifact(target, context)
        result["target"] = str(target)
        if artifact_inspection:
            result["artifactInspection"] = artifact_inspection
        finalized = finalize_install_verification(target, result, artifact_inspection, context)
        finalized["operation"] = action
        finalized["rollbackAvailable"] = True
        return command_result(**finalized)
    if action == "launch":
        return run_privileged(
            ["monkey", "-p", positional[0], "-c", "android.intent.category.LAUNCHER", "1"],
            test_mode=context["test_mode"],
        )
    raise CommandFailure("invalid codex-package action", code=2)


def handle_network(args, context):
    return handle_net(args, context)


def handle_action(args, context):
    if not args or args[0] not in {"plan", "execute", "resume", "inspect", "verify", "stop"}:
        raise CommandFailure(
            "usage: codex-action <plan|execute|resume|inspect|verify|stop> <goal>",
            code=2,
        )
    operation = args[0]
    request = " ".join(args[1:]).strip()
    if operation in {"resume", "inspect", "verify", "stop"}:
        if not request:
            raise CommandFailure("job id is required", code=2)
        if operation == "stop":
            return handle_job(["stop", "--id", request], context)
        if operation == "verify":
            return handle_job(["verify", "--id", request], context)
        if operation == "resume":
            return handle_job(["resume", "--id", request], context)
        return handle_job(["inspect", "--id", request], context)
    if not request:
        raise CommandFailure("goal request is required", code=2)
    goal = normalize_action_goal(request)
    plan = command_result(
        goal=goal,
        strategies=list(ACTION_STRATEGIES),
        adapter=get_app_adapter(goal["target"]) if goal["target"] in APP_ADAPTERS else None,
        verified=False,
        risk=goal["risk"],
        completionGate=[
            "primary_action",
            "system_readback",
            "independent_verifier",
            "evidence_persisted",
            "stability_recheck",
        ],
    )
    if operation == "plan":
        return plan
    job_id = "action-" + uuid.uuid4().hex[:16]
    job = {
        "id": job_id,
        "sequence": next_sequence(context["root"]),
        "request": request,
        "normalizedGoal": goal,
        "goalContract": goal,
        "state": "running",
        "strategy": ACTION_STRATEGIES[0],
        "currentStrategy": ACTION_STRATEGIES[0],
        "step": "execute",
        "currentStep": "execute",
        "attempt": 1,
        "manualStop": False,
        "createdAt": iso_now(),
        "updatedAt": iso_now(),
        "strategyHistory": [],
        "primaryEvidence": [],
        "independentEvidence": [],
        "stabilityEvidence": [],
        "evidence": [],
        "nextAction": "execute",
        "lastError": None,
    }
    save_job(context["root"], job)
    return execute_action_job(job, context)


def handle_app(args, context):
    if not args:
        raise CommandFailure("usage: codex-app <list|inspect|open|action> ...", code=2)
    action = args[0]
    positional, options = parse_options(args[1:])
    if action == "list":
        adapters = list(APP_ADAPTERS.values())
        if context["test_mode"]:
            return command_result(
                adapters=adapters,
                installedPackages=[],
                packageCount=0,
                packageInventoryVerified=False,
                applicationInventory=[],
                applicationInventoryVerified=False,
                inventoryFilters={
                    "query": options.get("query", ""),
                    "includeSystem": bool(options.get("include-system")),
                    "launchableOnly": bool(options.get("launchable-only")),
                    "limit": int(options.get("limit", 250)),
                },
            )
        inventory = None
        try:
            inventory = automation_broker_request(
                context["root"],
                {
                    "action": "app.inventory",
                    "arguments": {
                        "query": options.get("query", ""),
                        "includeSystem": bool(options.get("include-system")),
                        "launchableOnly": bool(options.get("launchable-only")),
                        "limit": int(options.get("limit", 250)),
                    },
                },
                context["test_mode"],
            )
        except CommandFailure:
            # Preserve the original package-manager-only route if the broker is
            # temporarily unavailable; the richer route is an enhancement, not
            # a prerequisite for existing package discovery.
            inventory = None
        package_result = run_privileged(["pm", "list", "packages"], test_mode=False)
        installed = sorted(
            {
                line.split(":", 1)[1].strip()
                for line in package_result.get("stdout", "").splitlines()
                if line.startswith("package:") and line.split(":", 1)[1].strip()
            }
        )
        application_inventory = []
        inventory_verified = False
        inventory_evidence = {
            "type": "package-manager-list",
            "verified": package_result.get("ok") is True,
            "count": len(installed),
        }
        if inventory:
            application_inventory = (inventory.get("values") or {}).get("applications", [])
            inventory_verified = inventory.get("verified") is True
            inventory_evidence = inventory.get("primaryEvidence") or inventory_evidence
            installed = sorted(
                {
                    str(item.get("package"))
                    for item in application_inventory
                    if isinstance(item, dict) and item.get("package")
                }
            ) or installed
        elif options.get("query"):
            query = str(options["query"]).lower()
            installed = [package for package in installed if query in package.lower()]
        if not inventory and options.get("launchable-only"):
            # The package-manager fallback cannot prove launchability. Do not
            # return an unfiltered list under a launchable-only contract.
            installed = []
        return command_result(
            adapters=adapters,
            installedPackages=installed,
            packageCount=len(installed),
            applicationInventory=application_inventory,
            inventoryFilters={
                "query": options.get("query", ""),
                "includeSystem": bool(options.get("include-system")),
                "launchableOnly": bool(options.get("launchable-only")),
                "limit": int(options.get("limit", 250)),
            },
            packageInventoryVerified=inventory_verified or package_result.get("ok") is True,
            applicationInventoryVerified=inventory_verified,
            primaryEvidence=inventory_evidence,
            independentEvidence=(inventory.get("independentEvidence") if inventory else {
                "type": "package-manager-list-fallback",
                "verified": package_result.get("ok") is True,
                "count": len(installed),
            }),
            stabilityEvidence=(inventory.get("stabilityEvidence") if inventory else None),
        )
    if not positional:
        raise CommandFailure("application adapter is required", code=2)
    try:
        adapter = get_app_adapter(positional[0])
    except CommandFailure:
        if action not in {"inspect", "open", "action"}:
            raise
        adapter = resolve_app_adapter(options.get("package") or positional[0], context)
    if action == "inspect":
        return command_result(adapter=adapter, risk="read_only", verified=True)
    if action == "open":
        result = automation_broker_request(
            context["root"],
            {"action": "app.open", "arguments": {"adapter": adapter}},
            context["test_mode"],
        )
        result.update({"adapter": adapter["id"], "risk": "reversible_local"})
        return result
    if action == "action":
        operation = options.get("operation") or (positional[1] if len(positional) > 1 else "")
        generic_operations = {
            "snapshot",
            "wait_for",
            "click",
            "long_click",
            "focus",
            "back",
            "home",
            "tap",
            "swipe",
            "set_text",
            "clear_text",
            "select_all",
            "copy",
            "cut",
            "paste",
            "dismiss",
            "expand",
            "collapse",
            "ime_action",
            "scroll_forward",
            "scroll_backward",
            "global_action",
            "global",
            "key",
        }
        if operation not in adapter.get("actions", []) and operation not in generic_operations:
            raise CommandFailure("unsupported adapter action: " + str(operation), code=3)
        arguments = {
            "adapter": adapter,
            "operation": operation,
            "query": options.get("query", ""),
        }
        if options.get("package"):
            arguments["expectedPackage"] = options["package"]
        if options.get("text"):
            arguments["text"] = options["text"]
        if options.get("key") is not None:
            arguments["key"] = options["key"]
        if options.get("action-id"):
            arguments["actionId"] = int(options["action-id"])
        if options.get("timeout-ms"):
            arguments["timeoutMs"] = int(options["timeout-ms"])
        if options.get("poll-ms"):
            arguments["pollMs"] = int(options["poll-ms"])
        if options.get("x") is not None:
            arguments["x"] = float(options["x"])
        if options.get("y") is not None:
            arguments["y"] = float(options["y"])
        for key in ("x1", "y1", "x2", "y2"):
            if options.get(key) is not None:
                arguments[key] = float(options[key])
        if options.get("duration-ms") is not None:
            arguments["durationMs"] = int(options["duration-ms"])
        if options.get("direction"):
            arguments["direction"] = options["direction"]
        if options.get("selector"):
            try:
                arguments["selector"] = json.loads(options["selector"])
            except json.JSONDecodeError as exc:
                raise CommandFailure("selector must be valid JSON", code=2) from exc
        if options.get("after-selector"):
            try:
                arguments["afterSelector"] = json.loads(options["after-selector"])
            except json.JSONDecodeError as exc:
                raise CommandFailure("after selector must be valid JSON", code=2) from exc
        if options.get("after-timeout-ms"):
            arguments["afterTimeoutMs"] = int(options["after-timeout-ms"])
        if options.get("open-if-needed"):
            arguments["openIfNeeded"] = True
        return automation_broker_request(
            context["root"],
            {
                "jobId": context.get("job_id"),
                "action": "app.action",
                "arguments": arguments,
            },
            context["test_mode"],
        )
    raise CommandFailure("invalid codex-app action", code=2)


def handle_notification(args, context):
    if not args:
        raise CommandFailure("usage: codex-notification <list|inspect|action>", code=2)
    action = args[0]
    positional, options = parse_options(args[1:])
    if action not in {"list", "inspect", "action"}:
        raise CommandFailure("invalid codex-notification action", code=2)
    if not options.get("package"):
        raise CommandFailure(
            "notification operations require --package for scope",
            code=2,
        )
    arguments = {
        "key": positional[0] if positional else None,
        "operation": options.get("operation"),
        "package": options.get("package"),
    }
    if options.get("index") is not None:
        arguments["index"] = int(options["index"])
    if options.get("after-timeout-ms") is not None:
        arguments["afterTimeoutMs"] = int(options["after-timeout-ms"])
    if options.get("after-notification") is not None:
        try:
            arguments["afterNotification"] = json.loads(options["after-notification"])
        except json.JSONDecodeError as exc:
            raise CommandFailure(
                "after notification selector must be valid JSON",
                code=2,
            ) from exc
    return automation_broker_request(
        context["root"],
        {
            "action": "notification." + action,
            "arguments": arguments,
        },
        context["test_mode"],
    )


def handle_browser(args, context):
    positional, options = parse_options(args)
    if positional and positional[0] in {"open", "navigate", "inspect", "action"}:
        if positional[0] in {"inspect", "action"} and not options.get("package"):
            raise CommandFailure(
                "browser inspection and actions require --package for scope",
                code=2,
            )
        broker_arguments = {
            "values": positional[1:],
            "visible": bool(options.get("visible")),
            "preferredRoute": "windows-profile-2-extension",
            "fallbackRoute": "localhost-webapk",
        }
        if options.get("operation"):
            broker_arguments["operation"] = options["operation"]
        if options.get("selector"):
            broker_arguments["selector"] = json.loads(options["selector"])
        if options.get("after-selector"):
            broker_arguments["afterSelector"] = json.loads(options["after-selector"])
        if options.get("after-timeout-ms"):
            broker_arguments["afterTimeoutMs"] = int(options["after-timeout-ms"])
        if options.get("text") is not None:
            broker_arguments["text"] = options["text"]
        if options.get("package"):
            broker_arguments["expectedPackage"] = options["package"]
        return automation_broker_request(
            context["root"],
            {
                "action": "browser." + positional[0],
                "arguments": broker_arguments,
            },
            context["test_mode"],
        )
    return command_result(
        supported=True,
        route="localhost-webapk",
        delegatedRoute="windows-profile-2-extension",
        url="http://localhost:5900/?openProjectPath=/data/data/com.termux/files/home",
        visible=bool(options.get("visible")),
    )


def handle_ui(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-ui <current|dump|screenshot|tap|text|swipe|snapshot|snapshot-any|wait-for|click|long-click|focus|action|set-text|ime-action|scroll-forward|scroll-backward|global|key|back|home>",
            code=2,
        )
    action = args[0]
    if action in {
        "snapshot",
        "snapshot-any",
        "wait-for",
        "click",
        "long-click",
        "focus",
        "action",
        "set-text",
        "clear-text",
        "select-all",
        "copy",
        "cut",
        "paste",
        "dismiss",
        "expand",
        "collapse",
        "ime-action",
        "swipe",
        "scroll-forward",
        "scroll-backward",
        "global",
        "global-action",
        "key",
        "back",
        "home",
    }:
        positional, options = parse_options(args[1:])
        arguments = {}
        if options.get("selector"):
            try:
                arguments["selector"] = json.loads(options["selector"])
            except json.JSONDecodeError as exc:
                raise CommandFailure("selector must be valid JSON", code=2) from exc
        if options.get("after-selector"):
            try:
                arguments["afterSelector"] = json.loads(options["after-selector"])
            except json.JSONDecodeError as exc:
                raise CommandFailure("after selector must be valid JSON", code=2) from exc
        if options.get("after-timeout-ms"):
            arguments["afterTimeoutMs"] = int(options["after-timeout-ms"])
        if action == "set-text":
            arguments["text"] = options.get("text") or " ".join(positional)
        if action in {"global", "global-action", "key"}:
            arguments["key"] = options.get("key") or (positional[0] if positional else "")
        if action == "action":
            if not options.get("action-id"):
                raise CommandFailure("action requires --action-id", code=2)
            arguments["actionId"] = int(options["action-id"])
        if action == "wait-for":
            if options.get("timeout-ms"):
                arguments["timeoutMs"] = int(options["timeout-ms"])
            if options.get("poll-ms"):
                arguments["pollMs"] = int(options["poll-ms"])
        if action == "swipe":
            for key in ("x1", "y1", "x2", "y2"):
                if options.get(key) is not None:
                    arguments[key] = float(options[key])
            if options.get("duration-ms") is not None:
                arguments["durationMs"] = int(options["duration-ms"])
            if options.get("direction"):
                arguments["direction"] = options["direction"]
        if action == "ime-action" and options.get("submit-selector"):
            try:
                arguments["submitSelector"] = json.loads(options["submit-selector"])
            except json.JSONDecodeError as exc:
                raise CommandFailure(
                    "submit selector must be valid JSON",
                    code=2,
                ) from exc
        if action != "snapshot-any" and not options.get("package"):
            raise CommandFailure(
                "UI actions require --package for foreground scoping",
                code=2,
            )
        if options.get("package"):
            arguments["expectedPackage"] = options["package"]
        broker_operation = (
            "global_action"
            if action in {"global", "global-action", "key"}
            else action.replace("-", "_")
        )
        return automation_broker_request(
            context["root"],
            {
                "action": "ui." + broker_operation,
                "arguments": arguments,
            },
            context["test_mode"],
        )
    return handle_android(args, context)


def handle_account(args, context):
    positional, options = parse_options(args)
    package = options.get("package") or (positional[0] if positional else None)
    if not package:
        raise CommandFailure("usage: codex-account inspect --package PACKAGE", code=2)
    app_id = options.get("app")
    adapter = _goal_adapter(app_id or "todoist", package, context)
    return automation_broker_request(
        context["root"],
        {
            "action": "app.inspect",
            "arguments": {
                "adapter": adapter,
                "expectedPackage": package,
                "fact": "account",
                "openIfNeeded": True,
            },
        },
        context["test_mode"],
    )


def handle_entitlement(args, context):
    positional, options = parse_options(args)
    package = options.get("package") or (positional[0] if positional else None)
    if not package:
        raise CommandFailure("usage: codex-entitlement inspect --package PACKAGE", code=2)
    app_id = options.get("app")
    adapter = _goal_adapter(app_id or "todoist", package, context)
    return automation_broker_request(
        context["root"],
        {
            "action": "app.inspect",
            "arguments": {
                "adapter": adapter,
                "expectedPackage": package,
                "fact": "entitlement",
                "openIfNeeded": True,
            },
        },
        context["test_mode"],
    )


def handle_todoist(args, context):
    if not args:
        raise CommandFailure(
            "usage: codex-todoist <plan|inspect|launch|account|entitlement|verify> [--package PACKAGE]",
            code=2,
        )
    action = args[0]
    positional, options = parse_options(args[1:])
    package = options.get("package") or "com.todoist"
    if action == "plan":
        return command_result(
            workflow="official-todoist",
            package=package,
            steps=[
                "inspect-installed-package",
                "preserve-application-data",
                "install-or-update-official-signed-build",
                "verify-package-manager-readback",
                "launch-and-verify-foreground",
                "inspect-account-state-separately",
                "inspect-official-entitlement-separately",
            ],
            prohibitedSubstitutions=[
                "modified-or-repackaged-apk",
                "license-bypass",
                "destructive-uninstall-without-rollback",
            ],
            verified=False,
        )
    if action == "inspect":
        result = handle_package(["inspect", package], context)
        result.update({"workflow": "official-todoist", "fact": "installation"})
        return result
    if action == "launch":
        result = handle_package(["launch", package], context)
        result.update({"workflow": "official-todoist", "fact": "foreground-launch"})
        return result
    if action == "account":
        result = handle_account(["inspect", "--package", package], context)
        result.update({"workflow": "official-todoist", "fact": "account"})
        return result
    if action == "entitlement":
        result = handle_entitlement(["inspect", "--package", package], context)
        result.update({"workflow": "official-todoist", "fact": "official-entitlement"})
        return result
    if action == "verify":
        installation = handle_package(["verify", package], context)
        account = handle_account(["inspect", "--package", package], context)
        entitlement = handle_entitlement(["inspect", "--package", package], context)
        facts = {
            "installation": installation,
            "account": account,
            "officialEntitlement": entitlement,
        }
        return command_result(
            workflow="official-todoist",
            package=package,
            facts=facts,
            verified=all(item.get("verified") is True for item in facts.values()),
            limitation=(
                "official entitlement remains unverified unless the authorized account state and entitlement observation both pass"
            ),
        )
    raise CommandFailure("invalid codex-todoist action", code=2)


HANDLERS = {
    "codex-route": handle_route,
    "codex-exec": handle_exec,
    "codex-search": handle_search,
    "codex-source": handle_source,
    "codex-fetch": handle_fetch,
    "codex-download": handle_download,
    "codex-acquire": handle_acquire,
    "codex-install": handle_install,
    "codex-update": handle_update,
    "codex-delete": handle_delete,
    "codex-restore": handle_restore,
    "codex-fs": handle_fs,
    "codex-pm": handle_pm,
    "codex-android": handle_android,
    "codex-privilege": handle_privilege,
    "codex-provision": handle_provision,
    "codex-net": handle_net,
    "codex-protocol": handle_protocol,
    "codex-media": handle_media,
    "codex-ocr": handle_ocr,
    "codex-speech": handle_speech,
    "codex-vault": handle_vault,
    "codex-memory": handle_memory,
    "codex-schedule": handle_schedule,
    "codex-health": handle_health,
    "codex-audit": handle_audit,
    "codex-undo": handle_undo,
    "codex-win": handle_win,
    "codex-github": handle_github,
    "codex-job": handle_job,
    "codex-goal": handle_goal,
    "codex-capability": handle_capability,
    "codex-verify": handle_verify,
    "codex-recover": handle_recover,
    "codex-browser": handle_browser,
    "codex-ui": handle_ui,
    "codex-network": handle_network,
    "codex-artifact": handle_artifact,
    "codex-package": handle_package,
    "codex-account": handle_account,
    "codex-entitlement": handle_entitlement,
    "codex-todoist": handle_todoist,
    "codex-action": handle_action,
    "codex-app": handle_app,
    "codex-notification": handle_notification,
}


def run(argv, env=None):
    env = dict(os.environ if env is None else env)
    if not argv:
        return 2, command_result(False, error="missing command", commands=list(COMMANDS))
    command = pathlib.Path(argv[0]).name
    args = list(argv[1:])
    if command not in HANDLERS:
        return 2, command_result(False, error="unknown command: " + command)
    root = runtime_root(env)
    ensure_layout(root)
    context = {
        "root": root,
        "env": env,
        "test_mode": env.get("CODEX_RUNTIME_TEST_MODE") == "1",
    }
    started = utc_now()
    code = 0
    try:
        result = HANDLERS[command](args, context)
        if not isinstance(result, dict):
            result = command_result(value=result)
        if not result.get("ok", False):
            code = int(result.get("exitCode", 1))
    except CommandFailure as exc:
        code = exc.code
        details = dict(exc.details)
        details.pop("ok", None)
        result = command_result(False, error=str(exc), **details)
    except Exception as exc:
        code = 1
        result = command_result(
            False, error=str(exc), errorType=exc.__class__.__name__
        )
    result = enrich_result_envelope(result, command, started, utc_now(), code)
    write_receipt(root, command, args, started, code, result)
    return code, result


def cli_arguments():
    invoked = pathlib.Path(sys.argv[0]).name
    if invoked in COMMANDS:
        return [invoked, *sys.argv[1:]]
    return sys.argv[1:]


def main():
    code, result = run(cli_arguments())
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
