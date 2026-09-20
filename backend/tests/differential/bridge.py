"""Python side of the differential bridge.

Keeps one ``tsx tests/bridge.mts`` process alive for the whole test session and
talks line-delimited JSON to it. The point is that every assertion in this
directory compares the Python port against the *running TypeScript code*, not
against a transcription of it — so a rule that was ported wrong fails here
rather than in production.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


class BridgeError(RuntimeError):
    """The TypeScript side raised while evaluating a call."""


class TsBridge:
    """A long-lived handle on the TypeScript implementation."""

    def __init__(self) -> None:
        self._proc = subprocess.Popen(
            ["npx", "tsx", "tests/bridge.mts"],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def call(self, fn: str, *args: Any) -> Any:
        assert self._proc.stdin and self._proc.stdout
        if self._proc.poll() is not None:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise BridgeError(f"bridge exited with {self._proc.returncode}\n{stderr}")

        self._proc.stdin.write(json.dumps({"fn": fn, "args": list(args)}) + "\n")
        self._proc.stdin.flush()

        line = self._proc.stdout.readline()
        if not line:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise BridgeError(f"bridge closed stdout mid-call\n{stderr}")

        reply = json.loads(line)
        if not reply.get("ok"):
            raise BridgeError(reply.get("error", "unknown error"))
        return reply["value"]

    def close(self) -> None:
        if self._proc.poll() is None:
            assert self._proc.stdin
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
