"""Generate a 1-2 sentence, fact-grounded justification for each ranked candidate.

Spec Stage-4 requirements this targets:
  * Specific facts (years, title, named skills, signal values).
  * JD connection (retrieval/ranking/product-company framing).
  * Honest concerns where the candidate has gaps.
  * No hallucination — every clause is built only from the candidate's own data.
  * Variation — phrasing rotates deterministically per candidate.
  * Rank consistency — tone tracks the score/rank bucket.
"""


def _named_skills(facts, limit=3):
    vals = list(facts.get("matched_skills", {}).values())
    seen, out = set(), []
    for v in vals:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
        if len(out) >= limit:
            break
    return out


def _strength_clause(facts, comp, idx):
    title = facts.get("current_title") or "candidate"
    yrs = facts.get("years")
    yrs_s = f"{yrs:.1f} yrs" if isinstance(yrs, (int, float)) else "n/a"
    skills = _named_skills(facts)
    tc = facts.get("title_career", {})
    dom = facts.get("domain", {})
    prod = facts.get("production", {})

    options = []
    if tc.get("built_system") or dom.get("ir", 0) >= 2:
        options.append(f"{title} with {yrs_s}; career shows hands-on retrieval/ranking "
                       f"work rather than just AI keywords")
    if skills:
        options.append(f"{title}, {yrs_s}; demonstrated depth in {', '.join(skills)}")
    if prod.get("product_evidence") and not prod.get("services_only"):
        options.append(f"{title} with {yrs_s} of product-company engineering experience")
    if dom.get("nlp", 0) >= 1 and dom.get("ir", 0) >= 1:
        options.append(f"{title} with {yrs_s} spanning NLP and retrieval/search")
    options.append(f"{title} with {yrs_s}")
    return options[idx % len(options)]


def _positive_signal(facts):
    """One concrete, true positive signal — location or availability."""
    b = facts.get("behaviour", {})
    loc = facts.get("location")
    country = facts.get("country")
    bits = []
    if isinstance(loc, str) and any(city in loc.lower() for city in ("pune", "noida")):
        city = loc.split(",")[0].strip().title()
        bits.append(f"{city}-based and in-region")
    elif country == "India":
        bits.append("India-based")
    rr = b.get("response_rate")
    if isinstance(rr, (int, float)) and rr >= 0.6:
        bits.append(f"responsive to recruiters ({rr:.0%})")
    mi = b.get("months_inactive")
    if isinstance(mi, int) and mi <= 2 and b.get("open_to_work"):
        bits.append("recently active and open to work")
    np = b.get("notice_period_days")
    if isinstance(np, (int, float)) and np <= 30:
        bits.append(f"short notice ({int(np)}d)")
    return bits[0] if bits else None


def _concern_clause(facts, flags, comp):
    behaviour = facts.get("behaviour", {})
    concerns = []
    if flags.get("services_only"):
        concerns.append("entire career at services/consulting firms, which the JD screens out")
    if flags.get("offdomain_primary"):
        concerns.append("background is primarily vision/speech with limited NLP/IR depth")
    if flags.get("keyword_stuffer"):
        concerns.append("a non-engineering title with an AI skill list that lacks supporting evidence")
    mi = behaviour.get("months_inactive")
    if isinstance(mi, int) and mi >= 6:
        concerns.append(f"inactive on-platform ~{mi} months")
    rr = behaviour.get("response_rate")
    if isinstance(rr, (int, float)) and rr < 0.25:
        concerns.append(f"low recruiter response rate ({rr:.0%})")
    if behaviour.get("open_to_work") is False:
        concerns.append("not currently marked open-to-work")
    np = behaviour.get("notice_period_days")
    if isinstance(np, (int, float)) and np >= 120:
        concerns.append(f"long notice period ({int(np)} days)")
    if comp.get("location", 1) < 0.4:
        loc = facts.get("country") or "outside India"
        concerns.append(f"based in {loc}, outside the Pune/Noida hiring region (no visa sponsorship)")
    if comp.get("experience", 1) < 0.55:
        y = facts.get("years")
        if isinstance(y, (int, float)):
            if y < 4:
                concerns.append(f"only {y:.1f} yrs experience, below the 5-9 band")
            elif y > 11:
                concerns.append(f"{y:.1f} yrs, above the target band")
    return concerns


# Varied closers, selected deterministically per candidate.
_TOP_CLOSERS = [
    "a strong fit for the role.",
    "one of the cleaner matches in the pool.",
    "well aligned with the founding-team profile.",
    "a high-confidence pick.",
]
_MID_CLOSERS = [
    "Solid, relevant match.",
    "A dependable mid-pack fit.",
    "Good coverage of the core requirements.",
    "Relevant across skills and experience.",
]


def make_reasoning(rank, result):
    facts = result["facts"]
    flags = result["flags"]
    comp = result["components"]
    cid = facts.get("candidate_id", "")
    seed = sum(ord(ch) for ch in cid)

    strength = _strength_clause(facts, comp, seed)
    concerns = _concern_clause(facts, flags, comp)
    pos = _positive_signal(facts)

    if rank <= 10:
        if concerns:
            return f"{strength} — {_TOP_CLOSERS[seed % len(_TOP_CLOSERS)]} Minor watch-out: {concerns[0]}."
        lead = f"{strength}, {pos}" if pos else strength
        return f"{lead}. {_TOP_CLOSERS[seed % len(_TOP_CLOSERS)].capitalize()}"
    if rank <= 50:
        if concerns:
            return f"{strength}. Caveats: {'; '.join(concerns[:2])}."
        lead = f"{strength}, {pos}" if pos else strength
        return f"{lead}. {_MID_CLOSERS[seed % len(_MID_CLOSERS)]}"
    # 51-100: marginal; lead with the limiting factor honestly.
    if concerns:
        return f"{strength}, but {'; '.join(concerns[:2])}. Borderline pick near the cutoff."
    return f"{strength}; adjacent fit included near the cutoff as a moderate match."
