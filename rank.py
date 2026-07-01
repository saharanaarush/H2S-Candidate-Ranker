#!/usr/bin/env python3
"""Rank the top-100 candidates for the Redrob Senior AI Engineer JD.

Reproduce command (per submission spec):
    python rank.py --candidates ./candidates.jsonl --out ./submission.csv

Constraints honoured: standard library only, CPU-only, no network, single pass.
Handles plain .jsonl or gzipped .jsonl.gz transparently.
"""

import argparse
import csv
import gzip
import io
import json
import sys
import time

import scoring
from reasoning import make_reasoning

TOP_N = 100


def _open_any(path):
    """Open .jsonl or .jsonl.gz as a UTF-8 text stream."""
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def rank_candidates(path, top_n=TOP_N, progress_every=20000, keep=None,
                    shard=0, nshards=1):
    """Stream the file, score each candidate, keep the best `keep` results.

    `keep` defaults to top_n*3 so shard outputs retain enough margin to merge
    correctly. `shard`/`nshards` split work across processes by line index
    (line_no % nshards == shard) for environments that limit per-call wall time.
    """
    keep = keep or max(top_n * 3, top_n)
    shortlist = []  # list of (score, candidate_id, result)
    prune_at = keep * 2
    n = 0
    seen = 0
    t0 = time.time()
    with _open_any(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            if nshards > 1 and (seen % nshards) != shard:
                seen += 1
                continue
            seen += 1
            n += 1
            c = json.loads(line)
            res = scoring.score_candidate(c)
            shortlist.append((res["composite"], c["candidate_id"], res))
            if len(shortlist) >= prune_at:
                shortlist.sort(key=lambda x: (-x[0], x[1]))
                del shortlist[keep:]
            if progress_every and n % progress_every == 0:
                print(f"  scored {n:,} candidates ({time.time()-t0:.1f}s)", file=sys.stderr)
    shortlist.sort(key=lambda x: (-x[0], x[1]))
    print(f"  scored {n:,} candidates total in {time.time()-t0:.1f}s", file=sys.stderr)
    return shortlist[:keep], n


def write_submission(top, out_path):
    """Write the validated CSV. Ranks 1..N, score non-increasing, ties by id."""
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["candidate_id", "rank", "score", "reasoning"])
        for i, (score, cid, res) in enumerate(top):
            rank = i + 1
            reasoning = " ".join(make_reasoning(rank, res).split())
            w.writerow([cid, rank, f"{score:.6f}", reasoning])


def _dump_partial(shortlist, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([[s, cid, res] for (s, cid, res) in shortlist], f)


def _merge_partials(paths, top_n):
    merged = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for s, cid, res in json.load(f):
                merged.append((s, cid, res))
    merged.sort(key=lambda x: (-x[0], x[1]))
    return merged[:top_n]


def main():
    ap = argparse.ArgumentParser(description="Redrob top-100 candidate ranker (CPU, no network).")
    ap.add_argument("--candidates", help="Path to candidates.jsonl or .jsonl.gz")
    ap.add_argument("--out", default="submission.csv", help="Output CSV path")
    ap.add_argument("--top", type=int, default=TOP_N, help="How many to rank (default 100)")
    # The options below exist only to split work across processes in compute-
    # limited environments; the canonical single-command run uses none of them.
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--partial", help="Write top-K results to this JSON instead of a CSV")
    ap.add_argument("--from-partials", nargs="+", help="Merge these partial JSONs into the final CSV")
    args = ap.parse_args()

    if args.from_partials:
        top = _merge_partials(args.from_partials, args.top)
        write_submission(top, args.out)
        print(f"Merged {len(args.from_partials)} partials -> {len(top)} rows in {args.out}.")
        return

    if not args.candidates:
        ap.error("--candidates is required (unless using --from-partials).")

    shortlist, total = rank_candidates(
        args.candidates, top_n=args.top, shard=args.shard, nshards=args.nshards)

    if args.partial:
        _dump_partial(shortlist, args.partial)
        print(f"Wrote {len(shortlist)} partial results to {args.partial} (from {total:,} scored).")
        return

    top = shortlist[:args.top]
    if len(top) < args.top:
        print(f"WARNING: only {len(top)} candidates available (< {args.top}).", file=sys.stderr)
    write_submission(top, args.out)
    print(f"Wrote {len(top)} ranked candidates to {args.out} (from {total:,} scored).")


if __name__ == "__main__":
    main()
