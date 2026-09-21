"""The model boundary.

Deliberately small and deliberately last. Everything clinical is settled before
anything here is called, and the service is fully useful with no model
configured at all: :mod:`brahmo.api` will still return the safety report and
the composed prompts, and simply say no model is available.

That is not a limitation to apologise for. A deployment with no API key still
answers the question this project is actually about — what the deterministic
layer found, and what context the model would have been given.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ModelUnavailable(RuntimeError):
    """No model is configured, or the configured one could not be reached."""


@runtime_checkable
class ModelClient(Protocol):
    """Anything that can turn a prompt into text."""

    @property
    def name(self) -> str:
        """Identifier for the model, recorded alongside its answer."""

    def complete(self, prompt: str) -> str:
        """Answer the prompt, or raise :class:`ModelUnavailable`."""


@dataclass(frozen=True, slots=True)
class NoModel:
    """The default. Refuses politely rather than pretending."""

    reason: str = "no model configured"

    @property
    def name(self) -> str:
        return "none"

    def complete(self, prompt: str) -> str:
        raise ModelUnavailable(self.reason)


@dataclass(frozen=True, slots=True)
class EchoModel:
    """A stand-in for tests. Returns a deterministic digest of the prompt.

    Exists so the consult path can be exercised end to end without a network
    call, which keeps the no-network guarantee testable on every endpoint.
    """

    label: str = "echo"

    @property
    def name(self) -> str:
        return self.label

    def complete(self, prompt: str) -> str:
        return f"[{self.label}] {len(prompt)} chars, {prompt.count(chr(10)) + 1} lines"
