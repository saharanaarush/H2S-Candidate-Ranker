"""Feature-based candidate scoring. Pure standard library, CPU-only, no network.

score_candidate(c) -> dict with:
  composite   final score in (0, 1)
  components  per-component sub-scores (for transparency / reasoning)
  facts       extracted facts the reasoning generator can quote (no hallucination)
  flags       booleans: honeypot, keyword_stuffer, services_only, offdomain, etc.

The design follows jd_profile.py. Each component returns 0..1; the weighted sum
is multiplied by a behavioural availability modifier and an honeypot gate.
"""

from datetime import date

import jd_profile as J

_TODAY = date.fromisoformat(J.TODAY_ISO)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _months_between(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _pdate(s):
    try:
        return date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def _any(text: str, terms) -> bool:
    return any(t in text for t in terms)


def _count_terms(text: str, terms) -> int:
    return sum(1 for t in terms if t in text)


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- #
# Corpus extraction: where REAL evidence lives (career descriptions), kept
# separate from the skills array (where keyword-stuffers operate).
# --------------------------------------------------------------------------- #
def _build_corpus(c):
    p = c.get("profile", {})
    parts = [p.get("headline", ""), p.get("summary", "")]
    for r in c.get("career_history", []):
        parts.append(r.get("title", ""))
        parts.append(r.get("description", ""))
    return " ".join(parts).lower()


def _titles_lower(c):
    return [r.get("title", "").lower() for r in c.get("career_history", [])]


# --------------------------------------------------------------------------- #
# 1. Title / career bucket
# --------------------------------------------------------------------------- #
def _title_bucket(title_l):
    for name, base, terms in J.TITLE_BUCKETS:
        if _any(title_l, terms):
            return name, base
    return "non_tech", 0.10


def score_title_career(c, corpus):
    cur = c.get("profile", {}).get("current_title", "").lower()
    cur_bucket, cur_base = _title_bucket(cur)

    # Best bucket seen anywhere in history (so a current non-tech role with a
    # strong engineering past isn't zeroed out).
    best_base = cur_base
    best_bucket = cur_bucket
    for t in _titles_lower(c):
        b, base = _title_bucket(t)
        if base > best_base:
            best_base, best_bucket = base, b

    # Weight current title more than past (the JD wants people coding NOW).
    base = 0.7 * cur_base + 0.3 * best_base

    # Evidence bonus: built ranking/search/recsys/retrieval systems. This is the
    # "Tier-5 without the buzzwords" reward the JD explicitly calls for.
    ir_hits = _count_terms(corpus, J.IR_RANKING_TERMS)
    built_system = _any(corpus, ["built", "shipped", "designed", "deployed", "owned"]) and ir_hits >= 1
    bonus = min(0.30, 0.06 * ir_hits) + (0.08 if built_system else 0.0)

    is_non_tech = cur_bucket == "non_tech" or _any(cur, J.NON_TECH_TITLES)
    return _clip(base + bonus), {
        "cur_bucket": cur_bucket,
        "best_bucket": best_bucket,
        "ir_hits": ir_hits,
        "built_system": built_system,
        "is_non_tech": is_non_tech,
    }


# --------------------------------------------------------------------------- #
# 2. Domain relevance (NLP / IR vs off-domain CV/speech/robotics)
# --------------------------------------------------------------------------- #
def score_domain(c, corpus):
    ir = _count_terms(corpus, J.IR_RANKING_TERMS)
    nlp = _count_terms(corpus, J.NLP_TERMS)
    off = _count_terms(corpus, J.OFFDOMAIN_TERMS)

    relevant = ir + nlp
    raw = _clip(0.12 + 0.16 * ir + 0.10 * nlp)  # saturates quickly

    offdomain_primary = off >= 2 and relevant <= 1
    if offdomain_primary:
        raw = min(raw, 0.22)  # JD: CV/speech/robotics without NLP/IR is a no
    elif off > relevant and relevant >= 1:
        raw *= 0.7

    return _clip(raw), {
        "ir": ir, "nlp": nlp, "off": off, "offdomain_primary": offdomain_primary,
    }


# --------------------------------------------------------------------------- #
# 3. Trust-weighted required skills (anti keyword-stuffer)
# --------------------------------------------------------------------------- #
def _skill_trust(sk, assess):
    """0..1 trust that a listed skill reflects real depth.

    A skill claimed 'expert' with 0 endorsements, 0 months used, and no
    assessment score is worth almost nothing — that's the stuffer pattern.
    """
    prof = {"beginner": 0.3, "intermediate": 0.6, "advanced": 0.85, "expert": 1.0}.get(
        sk.get("proficiency", "intermediate"), 0.5)
    dur = sk.get("duration_months", 0) or 0
    dur_f = _clip(dur / 36.0)                      # 3+ yrs of use -> full
    end = sk.get("endorsements", 0) or 0
    end_f = _clip(end / 25.0)
    name = sk.get("name", "")
    a = assess.get(name)
    assess_f = _clip(a / 80.0) if isinstance(a, (int, float)) and a >= 0 else 0.0

    # Evidence-weighted; proficiency claim alone is capped low without backing.
    backing = max(dur_f, end_f, assess_f)
    return _clip(0.35 * prof + 0.65 * (0.5 * prof + 0.5 * 1.0) * backing)


def score_skills(c):
    skills = c.get("skills", []) or []
    assess = c.get("redrob_signals", {}).get("skill_assessment_scores", {}) or {}

    # Per-family best trust among matching skills.
    fam_score = {}
    matched_named = {}
    for fam, (required, weight, terms) in J.SKILL_FAMILIES.items():
        best = 0.0
        best_name = None
        for sk in skills:
            nm = sk.get("name", "").lower()
            if any(t in nm for t in terms):
                tr = _skill_trust(sk, assess)
                if tr > best:
                    best, best_name = tr, sk.get("name")
        fam_score[fam] = (required, weight, best)
        if best_name and best > 0.45:
            matched_named[fam] = best_name

    num = sum(w * s for (_req, w, s) in fam_score.values())
    den = sum(w for (_req, w, _s) in fam_score.values())
    raw = num / den if den else 0.0

    # Required-family coverage matters more than nice-to-haves.
    req_present = sum(1 for (req, w, s) in fam_score.values() if req and s > 0.4)
    coverage = req_present / sum(1 for (req, *_r) in fam_score.values() if req)
    score = _clip(0.55 * raw + 0.45 * coverage)
    return score, {"matched_named": matched_named, "req_present": req_present}


# --------------------------------------------------------------------------- #
# 4. Experience fit (5-9 sweet spot, peak 6-8)
# --------------------------------------------------------------------------- #
def score_experience(c):
    y = c.get("profile", {}).get("years_of_experience", 0) or 0
    if 6 <= y <= 8:
        s = 1.0
    elif 5 <= y < 6 or 8 < y <= 9:
        s = 0.88
    elif 4 <= y < 5 or 9 < y <= 11:
        s = 0.7
    elif 3 <= y < 4 or 11 < y <= 13:
        s = 0.5
    elif y < 3:
        s = 0.28 + 0.07 * y
    else:  # > 13
        s = max(0.25, 0.5 - 0.04 * (y - 13))
    return _clip(s), {"years": y}


# --------------------------------------------------------------------------- #
# 5. Product company vs services-only
# --------------------------------------------------------------------------- #
def _is_services(company):
    cl = (company or "").lower()
    return any(f in cl for f in J.SERVICES_FIRMS)


def score_production(c, corpus):
    hist = c.get("career_history", []) or []
    if not hist:
        return 0.4, {"services_only": False, "product_evidence": False}
    services_flags = [_is_services(r.get("company")) for r in hist]
    n_services = sum(services_flags)
    all_services = n_services == len(hist)
    cur_services = services_flags[0] if services_flags else False

    product_evidence = _any(corpus, [
        "real users", "production", "shipped", "scale", "millions", "users",
        "latency", "deployed", "a/b test", "recommendation system", "live ",
    ])

    if all_services:
        s = 0.12                       # JD disqualifier (entire career services)
    elif cur_services:
        s = 0.55 + (0.1 if product_evidence else 0)   # has product past
    else:
        s = 0.75 + (0.2 if product_evidence else 0)
    return _clip(s), {
        "services_only": all_services,
        "cur_services": cur_services,
        "product_evidence": product_evidence,
    }


# --------------------------------------------------------------------------- #
# 6. Location fit
# --------------------------------------------------------------------------- #
def score_location(c):
    p = c.get("profile", {})
    loc = (p.get("location", "") + " " + p.get("country", "")).lower()
    sig = c.get("redrob_signals", {})
    relocate = bool(sig.get("willing_to_relocate"))
    india = "india" in loc or _any(loc, J.TIER1_CITIES)

    if _any(loc, J.TIER1_CITIES_TOP):
        s = 1.0
    elif _any(loc, J.TIER1_CITIES):
        s = 0.9
    elif india:
        s = 0.7 + (0.1 if relocate else 0)
    else:  # outside India: case-by-case, no visa sponsorship
        s = 0.3 + (0.12 if relocate else 0)
    return _clip(s), {"india": india, "relocate": relocate,
                      "location": p.get("location", "")}


# --------------------------------------------------------------------------- #
# 7. Education (minor)
# --------------------------------------------------------------------------- #
def score_education(c):
    best = 0.45
    for e in c.get("education", []) or []:
        tier = e.get("tier", "unknown")
        t = {"tier_1": 1.0, "tier_2": 0.8, "tier_3": 0.6, "tier_4": 0.45}.get(tier, 0.5)
        field = (e.get("field_of_study", "") or "").lower()
        if any(k in field for k in ["computer", "data", "machine", "statistic", "math", "electr"]):
            t = min(1.0, t + 0.1)
        best = max(best, t)
    return _clip(best), {}


# --------------------------------------------------------------------------- #
# Honeypot / impossibility detection -> hard gate
# --------------------------------------------------------------------------- #
def detect_honeypot(c):
    reasons = []
    y = c.get("profile", {}).get("years_of_experience", 0) or 0
    hist = c.get("career_history", []) or []

    total_role_months = 0
    for r in hist:
        sd, ed = _pdate(r.get("start_date")), _pdate(r.get("end_date"))
        ed_eff = ed or _TODAY
        dm = r.get("duration_months", 0) or 0
        total_role_months += dm
        if sd:
            actual = _months_between(sd, ed_eff)
            if abs(actual - dm) > 6:
                reasons.append("role dates inconsistent with stated duration")
            if dm > (y * 12) + 18:
                reasons.append("single tenure exceeds total experience")

    # 'expert' skills never actually used.
    skills = c.get("skills", []) or []
    expert0 = sum(1 for s in skills
                  if s.get("proficiency") == "expert" and (s.get("duration_months", 0) or 0) == 0)
    if expert0 >= 2:
        reasons.append("multiple 'expert' skills with zero months of use")

    # Any skill used longer than the whole career.
    for s in skills:
        if (s.get("duration_months", 0) or 0) > (y * 12) + 18:
            reasons.append("skill usage longer than entire career")
            break

    # Career months wildly exceed stated experience.
    if total_role_months > (y * 12) + 36 and y > 0:
        reasons.append("career history far longer than stated experience")

    # Education sanity.
    for e in c.get("education", []) or []:
        sy, ey = e.get("start_year"), e.get("end_year")
        if isinstance(sy, int) and isinstance(ey, int) and ey < sy:
            reasons.append("education ends before it begins")

    return (len(reasons) > 0), reasons


# --------------------------------------------------------------------------- #
# Behavioural availability modifier (multiplier ~0.5 .. 1.12)
# --------------------------------------------------------------------------- #
def behavioural_modifier(c):
    s = c.get("redrob_signals", {}) or {}
    facts = {}
    m = 1.0

    last = _pdate(s.get("last_active_date"))
    months_inactive = _months_between(last, _TODAY) if last else 12
    facts["months_inactive"] = months_inactive
    if months_inactive <= 1:
        m *= 1.05
    elif months_inactive <= 3:
        m *= 1.0
    elif months_inactive <= 6:
        m *= 0.9
    elif months_inactive <= 9:
        m *= 0.78
    else:
        m *= 0.65

    rr = s.get("recruiter_response_rate", 0.5)
    facts["response_rate"] = rr
    if rr >= 0.6:
        m *= 1.05
    elif rr >= 0.35:
        m *= 1.0
    elif rr >= 0.2:
        m *= 0.9
    else:
        m *= 0.8

    otw = s.get("open_to_work_flag")
    facts["open_to_work"] = bool(otw)
    m *= 1.04 if otw else 0.9

    np = s.get("notice_period_days", 60)
    facts["notice_period_days"] = np
    if np <= 30:
        m *= 1.04
    elif np >= 120:
        m *= 0.9
    elif np >= 90:
        m *= 0.96

    # Light positive signals.
    if (s.get("saved_by_recruiters_30d", 0) or 0) >= 8:
        m *= 1.02
    if (s.get("interview_completion_rate", 0) or 0) >= 0.8:
        m *= 1.02
    if (s.get("profile_completeness_score", 0) or 0) >= 85:
        m *= 1.02
    if s.get("verified_email") and s.get("verified_phone"):
        m *= 1.01

    return _clip(m, 0.5, 1.12), facts


# --------------------------------------------------------------------------- #
# Master scorer
# --------------------------------------------------------------------------- #
def score_candidate(c):
    corpus = _build_corpus(c)

    comp = {}
    meta = {}
    comp["title_career"], meta["title_career"] = score_title_career(c, corpus)
    comp["domain"], meta["domain"] = score_domain(c, corpus)
    comp["skills"], meta["skills"] = score_skills(c)
    comp["experience"], meta["experience"] = score_experience(c)
    comp["production"], meta["production"] = score_production(c, corpus)
    comp["location"], meta["location"] = score_location(c)
    comp["education"], meta["education"] = score_education(c)

    base = sum(J.WEIGHTS[k] * comp[k] for k in J.WEIGHTS)

    # Keyword-stuffer trap: non-technical current title + glossy AI skills.
    keyword_stuffer = (meta["title_career"]["is_non_tech"]
                       and comp["skills"] > 0.45
                       and meta["domain"]["ir"] + meta["domain"]["nlp"] <= 1)
    if keyword_stuffer:
        base *= 0.45

    # Small, merit-based tie-break so genuinely-stronger candidates outrank
    # equally-saturated ones by EVIDENCE (not by candidate_id). Bounded so it
    # never overturns the main components.
    richness = (meta["domain"]["ir"] + meta["domain"]["nlp"]
                + len(meta["skills"]["matched_named"]) + meta["skills"]["req_present"]
                + (1 if meta["production"]["product_evidence"] else 0)
                + (1 if meta["title_career"]["built_system"] else 0))
    tie_bonus = 0.03 * _clip(richness / 12.0)

    bmod, bfacts = behavioural_modifier(c)
    honeypot, hp_reasons = detect_honeypot(c)

    score = base * bmod + tie_bonus
    if honeypot:
        score *= 0.04  # sink impossible profiles well below the top 100

    # Order-preserving squash to (0, ~0.97]; no hard ceiling clamp that would
    # collapse strong candidates into ties.
    score = _clip(score / 1.16, 0.001, 0.999)

    facts = {
        "candidate_id": c.get("candidate_id"),
        "name": c.get("profile", {}).get("anonymized_name"),
        "current_title": c.get("profile", {}).get("current_title"),
        "years": meta["experience"]["years"],
        "location": meta["location"]["location"],
        "country": c.get("profile", {}).get("country"),
        "matched_skills": meta["skills"]["matched_named"],
        **{k: meta[k] for k in ("title_career", "domain", "production")},
        "behaviour": bfacts,
    }
    flags = {
        "honeypot": honeypot,
        "honeypot_reasons": hp_reasons,
        "keyword_stuffer": keyword_stuffer,
        "services_only": meta["production"]["services_only"],
        "offdomain_primary": meta["domain"]["offdomain_primary"],
    }
    return {"composite": score, "components": comp, "facts": facts, "flags": flags,
            "behaviour_mult": bmod}
