"""Commission for one student, given resolved terms.

`calculate` answers the simulator's question: this student, this fee, this many
students counted so far -- eligible or not, how much, and why. `accrue` walks a
sequence of students in order and writes ledger-style entries, including the
true-up adjustments that a retroactive tier creates for students already
counted; earlier entries are never rewritten, only offset.
"""
from app.registry import get as _dashboard

model = _dashboard("commission").load_module("model")


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def tier_for(tiers: list[dict], n: int) -> dict | None:
    for t in sorted(tiers or [], key=lambda t: _f(t.get("min_count"), 0)):
        lo, hi = _f(t.get("min_count"), 0), _f(t.get("max_count"))
        if n >= lo and (hi is None or n <= hi):
            return t
    return None


def next_tier(tiers: list[dict], n: int) -> dict | None:
    ahead = [t for t in tiers or [] if _f(t.get("min_count"), 0) > n]
    return min(ahead, key=lambda t: _f(t.get("min_count"), 0)) if ahead else None


# --- eligibility --------------------------------------------------------------

def _match_place(rule: dict, student: dict) -> bool:
    value = rule.get("value") or ""
    for key in ("nationality", "residence", "country"):
        if model.same_place(value, student.get(key)):
            return True
    return False


def territory_verdict(terms: dict, student: dict) -> tuple[bool, str | None, str | None]:
    rules = terms.get("territory_rules") or []
    for r in rules:
        if r.get("type") == "EXCLUDE" and _match_place(r, student):
            return False, f"{r.get('value')} is excluded", r.get("source")
    includes = [r for r in rules if r.get("type") == "INCLUDE"]
    if terms.get("territory_type") == "NOT_GLOBAL" or includes:
        if not any(_match_place(r, student) for r in includes):
            where = student.get("nationality") or student.get("residence") or "this territory"
            return False, f"{where} is not an included territory", None
    return True, None, None


def exclusion_hit(terms: dict, student: dict) -> dict | None:
    level = student.get("course_level")
    flags = set(student.get("flags") or [])
    for e in terms.get("exclusions") or []:
        kind = e.get("type")
        levels = set(e.get("course_levels") or []) | set(model.EXCLUSION_LEVELS.get(kind, ()))
        if level and level in levels and e.get("cap_count") is None:
            return e
        if kind == "CAMPUS" and model.same_place(e.get("campus") or e.get("note"), student.get("campus")):
            return e
        flag = model.EXCLUSION_FLAGS.get(kind)
        if flag and flag in flags:
            return e
    return None


def pick_rule(terms: dict, student: dict) -> dict | None:
    """The most specific rule that matches: institution, then campus, then the
    narrowest course-level list; ties by priority."""
    level, campus, inst = student.get("course_level"), student.get("campus"), student.get("institution_id")
    candidates = []
    for r in terms.get("rules") or []:
        levels = r.get("course_levels") or []
        if levels and level not in levels:
            continue
        if r.get("campus") and campus and not model.same_place(r["campus"], campus):
            continue
        if r.get("institution_id") and inst and str(r["institution_id"]) != str(inst):
            continue
        score = (
            1 if r.get("institution_id") else 0,
            1 if r.get("campus") and campus else 0,
            1 if levels else 0,
            -len(levels),
            -(r.get("priority") or 0),
        )
        candidates.append((score, r))
    if not candidates:
        return None
    candidates.sort(key=lambda sr: sr[0], reverse=True)
    return candidates[0][1]


def bonus_applies(b: dict, rule: dict, student: dict) -> bool:
    ids = b.get("applies_to_rule_ids") or []
    levels = b.get("course_levels") or []
    if ids and rule.get("id") in ids:
        return True
    if levels:
        return student.get("course_level") in levels
    return not ids


# --- amounts ------------------------------------------------------------------

def rule_rate(rule: dict, n: int, position: int | None = None) -> tuple[float | None, dict | None]:
    """(value, tier). RETROACTIVE uses the tier containing the count; MARGINAL
    the tier containing this student's own position."""
    if rule.get("structure") != "TIERED":
        return _f(rule.get("value")), None
    at = position if rule.get("tier_mode") == "MARGINAL" and position else n
    tier = tier_for(rule.get("tiers"), at)
    return (_f(tier.get("value")) if tier else None), tier


def amount_for(pricing: str, value: float, fee: float) -> float:
    return round(fee * value / 100, 2) if pricing == "PERCENT" else round(value, 2)


def calculate(terms: dict, student: dict) -> dict:
    """student: course_level, nationality, campus, fee, count, position?,
    bonus_count?, flags[]. `count` is the qualifying count for the rule, pooled
    across every student at the institution."""
    if not terms.get("ok"):
        return {"eligible": False, "blocked": True, "reason": terms.get("reason"), "amount": 0}
    currency = terms.get("currency")
    base = {"eligible": False, "blocked": False, "amount": 0, "currency": currency}

    ok, why, source = territory_verdict(terms, student)
    if not ok:
        return {**base, "reason": f"Not eligible: {why}", "source": source}
    excl = exclusion_hit(terms, student)
    if excl:
        label = (excl.get("type") or "").replace("_", " ").lower()
        note = excl.get("note")
        return {**base, "excluded": True, "reason": f"Excluded: {label}{f' ({note})' if note else ''}",
                "source": excl.get("source")}
    rule = pick_rule(terms, student)
    if rule is None:
        return {**base, "reason": f"No commission rule covers {student.get('course_level') or 'this course level'}"}

    fee = _f(student.get("fee"), 0)
    n = int(student.get("count") or 1)
    position = student.get("position")
    value, tier = rule_rate(rule, n, position)
    if value is None:
        return {**base, "reason": f"{rule.get('name')}: no tier covers a count of {n}", "rule": rule}
    commission = amount_for(rule.get("pricing"), value, fee)
    breakdown = [{
        "label": rule.get("name"), "kind": "BASE", "source": rule.get("source"),
        "rate": value if rule.get("pricing") == "PERCENT" else None,
        "amount": commission,
        "detail": (f"{value:g}% of {model.fmt_money(fee, currency)}" if rule.get("pricing") == "PERCENT"
                   else f"flat {model.fmt_money(value, currency)}")
                  + (f", tier {tier.get('min_count')}–{tier.get('max_count') or '∞'} ({rule.get('tier_mode', '').lower()})" if tier else ""),
    }]

    bonuses, lump_sums, total_rate = [], [], value if rule.get("pricing") == "PERCENT" else None
    for b in terms.get("bonuses") or []:
        if not bonus_applies(b, rule, student):
            continue
        bn = int(student.get("bonus_count") or n)
        at = position if b.get("tier_mode") == "MARGINAL" and position else bn
        t = tier_for(b.get("tiers"), at)
        nxt = next_tier(b.get("tiers"), at)
        entry = {"id": b.get("id"), "kind": b.get("kind"), "criteria": b.get("criteria_text"),
                 "source": b.get("source"), "reached": bool(t), "amount": 0,
                 "needs_review": b.get("needs_review")}
        if nxt:
            entry["progress"] = f"{bn} of {int(_f(nxt['min_count']))}"
        if t:
            v = _f(t.get("value"), 0)
            if b.get("kind") == "RATE_UPLIFT":
                entry["amount"] = round(fee * v / 100, 2)
                entry["detail"] = f"+{v:g}% at {t.get('min_count')}+"
                if total_rate is not None:
                    total_rate += v
            elif b.get("kind") == "FIXED_PER_STUDENT":
                entry["amount"] = round(v, 2)
                entry["detail"] = f"+{model.fmt_money(v, currency)} per student at {t.get('min_count')}+"
            else:
                entry["detail"] = f"lump sum {model.fmt_money(v, currency)} when the count reaches {t.get('min_count')}"
                entry["lump_sum"] = v
                lump_sums.append(entry)
                entry = {**entry, "amount": 0}
            commission += entry["amount"]
        bonuses.append(entry)

    commission = round(commission, 2)
    vat_t, vat_rate = terms.get("vat_treatment"), _f(terms.get("vat_rate"), 0) or 0
    vat_rate_frac = vat_rate / 100 if vat_rate > 1 else vat_rate
    if vat_t == "INCLUSIVE":
        vat = {"treatment": vat_t, "rate": vat_rate_frac * 100,
               "revenue_ex_vat": round(commission / (1 + vat_rate_frac), 2),
               "invoice_total": commission,
               "detail": f"VAT inclusive: {model.fmt_money(commission / (1 + vat_rate_frac), currency)} ex VAT"}
    elif vat_t == "EXCLUSIVE":
        vat = {"treatment": vat_t, "rate": vat_rate_frac * 100, "revenue_ex_vat": commission,
               "invoice_total": round(commission * (1 + vat_rate_frac), 2),
               "detail": f"VAT exclusive: {vat_rate_frac * 100:g}% added on the invoice"}
    else:
        vat = {"treatment": vat_t or "NOT_APPLICABLE", "rate": 0, "revenue_ex_vat": commission,
               "invoice_total": commission, "detail": "No VAT"}

    milestones = [{"trigger": m.get("trigger"), "pct": _f(m.get("pct"), 0), "n_weeks": m.get("n_weeks"),
                   "amount": round(commission * _f(m.get("pct"), 0) / 100, 2)}
                  for m in terms.get("milestones") or [{"trigger": "ENROLLED", "pct": 100}]]
    return {
        **base, "eligible": True, "reason": None, "amount": commission,
        "rate": total_rate, "rule": {k: rule.get(k) for k in ("id", "name", "source", "pricing", "structure", "tier_mode")},
        "fee_basis": terms.get("fee_basis"), "breakdown": breakdown, "bonuses": bonuses,
        "lump_sums": lump_sums, "vat": vat, "milestones": milestones,
    }


def accrue(rule: dict, fees: list[float]) -> list[dict]:
    """Ledger entries for students joining one by one under a rule. Under a
    RETROACTIVE tier, crossing into a new tier re-rates every student already
    counted: each gets a TRUE_UP entry for the difference."""
    entries: list[dict] = []
    applied: dict[int, float] = {}          # student -> rate/amount basis charged so far
    for k, fee in enumerate(fees, start=1):
        value, tier = rule_rate(rule, k, position=k)
        if value is None:
            entries.append({"student": k, "kind": "NONE", "amount": 0, "note": "no tier covers this count"})
            continue
        amt = amount_for(rule.get("pricing"), value, fee)
        entries.append({"student": k, "kind": "COMMISSION", "rate": value, "amount": amt})
        applied[k] = value
        if rule.get("structure") == "TIERED" and rule.get("tier_mode") == "RETROACTIVE":
            for j in range(1, k):
                old = applied.get(j)
                if old is not None and old != value:
                    diff = amount_for(rule.get("pricing"), value, fees[j - 1]) - amount_for(rule.get("pricing"), old, fees[j - 1])
                    entries.append({"student": j, "kind": "TRUE_UP", "rate": round(value - old, 6),
                                    "amount": round(diff, 2), "note": f"student {k} moved the count into the {value:g} tier"})
                    applied[j] = value
    return entries
