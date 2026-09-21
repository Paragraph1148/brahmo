"""BRAHMO — deterministic clinical safety engine.

The rule here is the same one the TypeScript implementation commits to: no
safety decision consults a language model. Everything in :mod:`brahmo.engine`
is pure computation over a typed patient record.
"""

from importlib import resources


def response_instructions() -> str:
    """The prompt's response-instruction block.

    Held as data rather than a string literal in the composer, and extracted
    verbatim from ``src/lib/prompt-composer.ts`` so the two cannot drift apart
    silently. It is prose for the model, not logic, and nothing reads it.
    """
    return (resources.files("brahmo") / "data" / "response_instructions.md").read_text(
        encoding="utf-8"
    ).rstrip("\n")
