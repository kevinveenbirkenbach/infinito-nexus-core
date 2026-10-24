"""Redact secrets from the harness home before it syncs to Nextcloud.

The agent syncs its whole home, transcripts included, unencrypted, to its
Nextcloud. Before the upload every secret value is masked in the uploaded
copy, so a leaked token, key or password never reaches the sync. The agent's
own `.kdbx` is uploaded encrypted and is not touched by this redactor. Local
deploys run with MASK_CREDENTIALS_IN_LOGS disabled, so this redaction is the
protective layer for what is synced.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"
_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
    re.compile(
        r"(?i)\b(password|secret|api[_-]?key|token|access[_-]?key)\b\s*[:=]\s*"
        r"['\"]?[^\s'\"]{6,}['\"]?"
    ),
)


def redact(text: str) -> str:
    """Return ``text`` with every recognised secret value masked.

    Args:
        text: the content about to be uploaded (a transcript, a log, a file).
    """
    out = text
    for pattern in _PATTERNS:
        if pattern is _PATTERNS[5]:
            out = pattern.sub(lambda m: f"{m.group(1)}={MASK}", out)
        else:
            out = pattern.sub(MASK, out)
    return out


def _demo() -> None:
    assert redact("api_key: s3cr3tVALUE123") == f"api_key={MASK}", redact("api_key: s3cr3tVALUE123")
    assert redact("export TOKEN=ghp_" + "a" * 36).endswith(MASK)
    assert MASK in redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123")
    assert redact("clone https://user:p4ssw0rd@git.example/repo") == f"clone {MASK}git.example/repo"
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----"
    assert redact(f"before {key} after") == f"before {MASK} after"
    clean = "the maintainer opened a pull request and the gate was green"
    assert redact(clean) == clean, "clean prose was altered"
    assert "AKIAIOSFODNN7EXAMPLE" not in redact("key AKIAIOSFODNN7EXAMPLE here")
    print("home-sync redact self-check ok")


if __name__ == "__main__":
    _demo()
