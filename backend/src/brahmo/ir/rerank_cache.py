"""Fill the cross-encoder score cache.

    uv run --extra rerank python -m brahmo.ir.rerank_cache

Scores every (judged query, candidate document) pair the reranked
configurations can reach, and writes them beside the judgments. After this the
evaluation reproduces with no model and no torch, which is what keeps the
numbers checkable by someone who has neither.
"""

from __future__ import annotations

import argparse

from brahmo.ir.drafts import DraftSet
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
        "--drafts",
        action="store_true",
        default=True,
        help="also score the drafted questions, so review pools are not "
        "lexically biased",
    )
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

    # Drafted questions are scored too. Pooling candidates for review without
    # the cross-encoder would build a lexically biased pool — the answers to
    # the vocabulary-gap questions are exactly the ones BM25 cannot reach, so
    # they would never reach a reviewer.
    texts = [(q.id, q.text) for q in campaign.queries]
    if args.drafts:
        texts += [(q.id, q.question) for q in DraftSet.load().questions]

    print(f"model      {args.model}")
    print(f"queries    {len(texts)} ({len(campaign.queries)} judged"
          f"{f', {len(texts) - len(campaign.queries)} drafted' if args.drafts else ''})")
    print(f"documents  {len(documents)}")
    print(f"pairs      {len(texts) * len(documents)}")
    print()

    for query_id, text in texts:
        before = cache.misses
        scorer.score(text, documents)
        computed = cache.misses - before
        if computed:
            print(f"  {query_id:<38} {computed} computed")

    cache.save()
    print()
    print(f"cache hits {cache.hits}, misses {cache.misses} -> {cache.path}")


if __name__ == "__main__":
    main()
