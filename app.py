"""Sandbox demo for the Redrob ranker (satisfies submission_spec Section 10.5).

A hosted environment (Streamlit Cloud / HF Spaces) where organizers can run the
ranking system on a small candidate sample and download a ranked CSV. The
ranking logic is exactly the same code used by rank.py — no LLM, no network.

Run locally:  streamlit run app.py
"""

import gzip
import io
import json

import streamlit as st

import scoring
from reasoning import make_reasoning

st.set_page_config(page_title="Redrob Candidate Ranker", page_icon="🧭", layout="wide")
st.title("🧭 Redrob Candidate Ranker — Sandbox")
st.caption(
    "Feature-based ranker for the 'Senior AI Engineer — Founding Team' JD. "
    "CPU-only, no network, no LLM calls. Upload a candidate sample (.jsonl / "
    ".json / .jsonl.gz) or use the bundled sample, then rank."
)


def _load_candidates(raw: bytes, name: str):
    if name.endswith(".gz"):
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")
    text_stripped = text.lstrip()
    if text_stripped.startswith("["):           # pretty JSON array
        return json.loads(text_stripped)
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]  # JSONL


def _rank(cands, top_n):
    scored = []
    for c in cands:
        res = scoring.score_candidate(c)
        scored.append((res["composite"], c["candidate_id"], res))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:top_n]
    rows = []
    for i, (score, cid, res) in enumerate(top):
        rows.append({
            "rank": i + 1,
            "candidate_id": cid,
            "score": round(score, 6),
            "title": res["facts"]["current_title"],
            "years": res["facts"]["years"],
            "reasoning": " ".join(make_reasoning(i + 1, res).split()),
        })
    return rows


src = st.radio("Candidate source", ["Bundled sample", "Upload file"], horizontal=True)
cands = None
if src == "Upload file":
    up = st.file_uploader("candidates (.jsonl / .json / .jsonl.gz)",
                          type=["jsonl", "json", "gz"])
    if up is not None:
        cands = _load_candidates(up.getvalue(), up.name)
else:
    try:
        with open("sample_candidates.json", "r", encoding="utf-8") as f:
            cands = json.load(f)
        st.info(f"Loaded bundled sample: {len(cands)} candidates.")
    except FileNotFoundError:
        st.warning("sample_candidates.json not found next to app.py.")

top_n = st.slider("How many to rank", 5, 100, 25)

if cands and st.button("Rank candidates", type="primary"):
    with st.spinner(f"Scoring {len(cands)} candidates…"):
        rows = _rank(cands, top_n)
    st.success(f"Ranked top {len(rows)} of {len(cands)}.")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Downloadable CSV in the exact submission format.
    buf = io.StringIO()
    import csv as _csv
    w = _csv.writer(buf)
    w.writerow(["candidate_id", "rank", "score", "reasoning"])
    for r in rows:
        w.writerow([r["candidate_id"], r["rank"], f"{r['score']:.6f}", r["reasoning"]])
    st.download_button("Download ranked CSV", buf.getvalue(),
                       file_name="submission_sample.csv", mime="text/csv")
