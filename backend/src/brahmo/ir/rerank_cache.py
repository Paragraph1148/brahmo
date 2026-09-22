"""Fill the cross-encoder score cache.

    uv run --extra rerank python -m brahmo.ir.rerank_cache

Scores every (judged query, candidate document) pair the reranked
configurations can reach, and writes them beside the judgments. After this the
evaluation reproduces with no model and no torch, which is what keeps the
numbers checkable by someone who has neither.
"""

from __future__ import annotations

import argparse

from brahmo.ir.harness import Campaign
from brahmo.ir.reranker import (
    DEFAULT_MODEL,
    CachedScorer,
    CrossEncoderScorer,
    ScoreCache,
    default_cache_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--depth",
        type=int,
        default=40,
        help="score this many candidates per query; larger than any reranker's "
        "depth so changing that does not need a re-run",
    )
    args = parser.parse_args()

    campaign = Campaign.build()
    cache = ScoreCache.load(default_cache_path())
    scorer = CachedScorer(
        cache=cache, model_name=args.model, compute=CrossEncoderScorer(args.model)
    )

    # Every document is a candidate for at least one first stage on a corpus
    # this size, so score the whole store per query rather than guessing which.
    documents = list(campaign.store)
    print(f"model      {args.model}")
    print(f"queries    {len(campaign.queries)}")
    print(f"documents  {len(documents)}")
    print(f"pairs      {len(campaign.queries) * len(documents)}")
    print()

    for query in campaign.queries:
        before = cache.hits + cache.misses
        scorer.score(query.text, documents)
        scored = cache.hits + cache.misses - before
        print(f"  {query.id:<36} {scored} pairs")

    cache.save()
    print()
    print(f"cache hits {cache.hits}, misses {cache.misses} -> {cache.path}")


if __name__ == "__main__":
    main()
