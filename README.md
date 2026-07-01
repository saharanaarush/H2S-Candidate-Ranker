# Redrob Candidate Ranker

Top-100 candidate ranking for the **Senior AI Engineer — Founding Team** job
description from the Intelligent Candidate Discovery & Ranking Challenge.

The ranking step is **pure-Python standard library, CPU-only, offline** — no
LLM calls, no network, no GPU. It scores the full 100,000-candidate pool in
~55 seconds on a single core, well inside the 5-minute / 16 GB budget.

## Reproduce the submission

```bash
python rank.py --candidates ./candidates.jsonl --out ./submission.csv
python validate_submission.py submission.csv   # -> "Submission is valid."
```

`rank.py` transparently accepts `candidates.jsonl` or `candidates.jsonl.gz`.

## How it works

Each candidate gets seven weighted component scores (see `jd_profile.py` for the
exact weights and keyword taxonomies, and `scoring.py` for the logic):

| Component | Weight | What it captures |
|-----------|:------:|------------------|
| `title_career` | 0.26 | Is this actually an ML/engineering career? Decisive signal against keyword-stuffers (a "Marketing Manager" with a glossy AI skill list scores low). Rewards built-a-ranking/search/recsys evidence even without buzzwords. |
| `domain` | 0.20 | NLP / IR / ranking / retrieval relevance. Penalises primarily-vision/speech/robotics profiles without NLP/IR. |
| `skills` | 0.18 | Required-skill coverage, **trust-weighted** by endorsements, months-used, and Redrob assessment scores — so "expert" claims with zero backing are discounted. |
| `experience` | 0.12 | 5–9 year band, peak at 6–8. |
| `production` | 0.12 | Product-company experience vs services-only careers (TCS/Infosys/Wipro/… an entire career here is a JD disqualifier). |
| `location` | 0.08 | Pune/Noida strongest, then Indian Tier-1, then relocatable; outside-India down-weighted (no visa sponsorship). |
| `education` | 0.04 | Minor institution-tier / field signal. |

On top of the weighted sum:

* **Behavioural modifier** (multiplicative): down-weights candidates who are
  inactive, have a low recruiter-response rate, aren't open to work, or have a
  long notice period — "perfect on paper but unavailable" is not actually hireable.
* **Honeypot gate**: detects impossible profiles (career dates inconsistent with
  stated duration, multiple "expert" skills with 0 months of use, tenure longer
  than total experience) and sinks them far below the cutoff. The dataset's ~80
  honeypots do not reach the top 100.
* **Keyword-stuffer trap**: non-technical title + glossy AI skills + no real NLP/IR
  evidence is explicitly penalised.
* **Merit tie-break**: a small evidence-richness bonus orders otherwise-saturated
  top candidates by substance rather than by `candidate_id`.

`reasoning.py` writes a 1–2 sentence justification per candidate built *only* from
that candidate's own data (no hallucination), referencing concrete facts (title,
years, named skills, location, signal values), connecting to the JD, acknowledging
concerns honestly, and varying phrasing deterministically. Tone tracks the rank.

## Files

| File | Purpose |
|------|---------|
| `rank.py` | CLI entry point. Streams candidates, scores, writes the validated top-100 CSV. |
| `scoring.py` | Feature extraction + the seven components + honeypot/behavioural logic. |
| `jd_profile.py` | Declarative JD target: weights, keyword taxonomies, services-firm list, cities. |
| `reasoning.py` | Fact-grounded, varied, rank-consistent reasoning generation. |
| `app.py` | Streamlit sandbox demo (the required hosted demo). Runs the same ranking code on a small sample. |
| `validate_submission.py` | The official format validator (run before submitting). |
| `submission_metadata.yaml` | Portal-metadata mirror. Complete the `TODO` fields before submitting. |
| `sample_candidates.json` | 50-candidate sample for the sandbox demo. |
| `requirements.txt` | Empty for ranking; Streamlit only for the demo. |

## Sandbox demo

```bash
pip install -r requirements.txt
streamlit run app.py
```

Deploy this `app.py` to Streamlit Cloud or a HuggingFace Space and put the URL in
`submission_metadata.yaml: sandbox_link` to satisfy spec Section 10.5.

## Performance constraints (spec Section 3)

* Runtime: ~55s for 100K candidates on one CPU core (≤ 5 min ✓)
* Memory: streams line-by-line, keeps only a small shortlist (≤ 16 GB ✓)
* Compute: CPU-only, standard library only (no GPU ✓)
* Network: none during ranking (✓)

## Before you submit

1. Fill the `TODO` fields in `submission_metadata.yaml` (team name, GitHub URL,
   sandbox URL, contact details, compute environment).
2. Push this directory to a GitHub repo and deploy `app.py` as your sandbox.
3. Re-run the reproduce command on the official `candidates.jsonl` and validate.
