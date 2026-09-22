"""Cross-encoder reranking.

A first-stage retriever scores a query and a document apart — BM25 compares
term statistics, never reading the two together. A cross-encoder reads the
concatenated pair, so it can tell that a question about rheumatic mitral
stenosis is answered by a recommendation that never uses the word "rheumatic".
It is far too slow to score a whole corpus, which is why it reranks a candidate
list rather than replacing the retriever.

The configuration worth attention is reranking the *tag* set. The shipped
system already sends those documents; ranking and trimming them cannot surface
anything it would have withheld, so it is the change a cautious reviewer can
accept without re-litigating what the model is allowed to see.

torch is an optional dependency (``--extra rerank``). Everything else in
:mod:`brahmo.ir` works without it, and a cached score file lets the evaluation
be reproduced without it too.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Protocol, Sequence

from brahmo.ir.documents import Document, DocumentStore
from brahmo.ir.retrievers import Query, Retriever, Scored, _stable_order

#: Small, CPU-friendly, trained on MS MARCO passage ranking. Chosen because it
#: runs in seconds on a laptop and this corpus is 29 documents — a larger
#: reranker would be measuring the model rather than the idea.
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class ScoresUnavailable(RuntimeError):
    """No cached score and no model to compute one with."""


class PairScorer(Protocol):
    """Scores (query, document) pairs. Higher is more relevant."""

    @property
    def name(self) -> str: ...

    def score_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...


def _pair_key(model: str, query_text: str, doc_id: str) -> str:
    """Cache key. The query text is hashed so a reworded question misses.

    Keying on the query *id* would silently reuse a stale score after a
    question is edited, which is the kind of quiet wrongness this project keeps
    finding elsewhere.
    """
    digest = hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:16]
    return f"{model}|{digest}|{doc_id}"


@dataclass
class ScoreCache:
    """Cross-encoder scores on disk, so a run is reproducible without torch."""

    path: Path
    scores: dict[str, float] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    @classmethod
    def load(cls, path: str | Path) -> ScoreCache:
        resolved = Path(path)
        if resolved.is_file():
            data = json.loads(resolved.read_text(encoding="utf-8"))
            return cls(path=resolved, scores=dict(data.get("scores", {})))
        return cls(path=resolved)

    def get(self, key: str) -> float | None:
        value = self.scores.get(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def put(self, key: str, value: float) -> None:
        self.scores[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "about": (
                "Cross-encoder scores, cached so the evaluation reproduces without "
                "torch installed. Keyed by model, a hash of the query text, and "
                "document id — editing a question invalidates its scores rather "
                "than silently reusing them."
            ),
            "scores": dict(sorted(self.scores.items())),
        }
        self.path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


class CrossEncoderScorer:
    """The real model. Loaded lazily so importing this module stays cheap."""

    def __init__(self, model_name: str = DEFAULT_MODEL, max_length: int = 512) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self._model = None

    @property
    def name(self) -> str:
        return self.model_name

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - depends on the extra
                raise ScoresUnavailable(
                    "sentence-transformers is not installed. Either run with "
                    "`uv run --extra rerank`, or use the cached scores."
                ) from exc
            self._model = CrossEncoder(self.model_name, max_length=self.max_length)
        return self._model

    def score_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        return [float(s) for s in self._load().predict(list(pairs))]


@dataclass
class CachedScorer:
    """Serves cached scores, falling back to a model only on a miss.

    With ``allow_compute`` false it raises instead, which is what the test suite
    uses: a test that quietly downloads a model is a test that fails on a plane.
    """

    cache: ScoreCache
    model_name: str = DEFAULT_MODEL
    compute: PairScorer | None = None
    allow_compute: bool = True

    @property
    def name(self) -> str:
        return self.model_name

    def score(self, query_text: str, documents: Sequence[Document]) -> list[float]:
        keys = [_pair_key(self.model_name, query_text, d.id) for d in documents]
        cached = [self.cache.get(k) for k in keys]

        missing = [i for i, value in enumerate(cached) if value is None]
        if missing:
            if not self.allow_compute:
                raise ScoresUnavailable(
                    f"{len(missing)} pair(s) are not in the score cache and computing "
                    "is disabled. Run `python -m brahmo.ir.rerank_cache` to fill it."
                )
            scorer = self.compute or CrossEncoderScorer(self.model_name)
            pairs = [(query_text, documents[i].indexed_text) for i in missing]
            for index, value in zip(missing, scorer.score_pairs(pairs)):
                cached[index] = value
                self.cache.put(keys[index], value)

        return [float(v) for v in cached]  # type: ignore[arg-type]


@dataclass
class RerankedRetriever:
    """A first stage, reordered by the cross-encoder.

    ``depth`` is how many candidates are rescored. It bounds both the cost and
    what the reranker can achieve: nothing outside the first stage's top
    ``depth`` can be recovered, so recall is inherited and only the ordering —
    and what survives the cutoff — is the reranker's to improve.
    """

    first_stage: Retriever
    scorer: CachedScorer
    store: DocumentStore
    depth: int = 25
    label: str | None = None

    @property
    def name(self) -> str:
        return self.label or f"rerank({self.first_stage.name})"

    def search(self, query: Query, k: int) -> list[Scored]:
        candidates = self.first_stage.search(query, self.depth)
        documents = [self.store.get(c.doc_id) for c in candidates]
        present = [(c, d) for c, d in zip(candidates, documents) if d is not None]
        if not present:
            return []
        scores = self.scorer.score(query.text, [d for _, d in present])
        return _stable_order(
            Scored(c.doc_id, score) for (c, _), score in zip(present, scores)
        )[:k]


def default_cache_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "rerank_scores.json"


def build_reranked(
    store: DocumentStore,
    first_stages: Iterable[Retriever],
    *,
    cache_path: str | Path | None = None,
    allow_compute: bool = True,
    depth: int = 25,
    scorer_factory: Callable[[], PairScorer] | None = None,
) -> tuple[RerankedRetriever, ...]:
    cache = ScoreCache.load(cache_path or default_cache_path())
    scorer = CachedScorer(
        cache=cache,
        compute=scorer_factory() if scorer_factory else None,
        allow_compute=allow_compute,
    )
    return tuple(
        RerankedRetriever(first_stage=stage, scorer=scorer, store=store, depth=depth)
        for stage in first_stages
    )
