"""resolveTerms: the terms that apply to one institution for one intake.

A pure function over already-loaded contracts, so it can be tested without a
database and so the simulator, the timeline and the effective-terms screen all
ask the same question the same way. store.load_for_institution() fetches the
input.

Each contract passed in carries its live row (status is live: marking a
contract inactive takes effect without a new version), its published
`versions` and its PUBLISHED `amendments`. Draft edits never reach here.
"""
import copy
from datetime import date

from app.registry import get as _dashboard

model = _dashboard("commission").load_module("model")


def no_terms(reason: str, **extra) -> dict:
    return {"ok": False, "reason": reason, **extra}


def _d(v) -> date | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def in_scope(scope: dict, intake: str) -> bool:
    mode = (scope or {}).get("mode", "ENTIRE_YEAR")
    if mode == "INTAKES":
        return intake in (scope.get("intakes") or [])
    if mode == "UP_TO":
        until = scope.get("until_intake")
        return bool(until) and intake <= until and intake >= (scope.get("from_intake") or "0000-00")
    return True


def extended_end(contract: dict) -> date | None:
    """The contract's end date after any published extension."""
    end = _d(contract.get("end_date"))
    for a in contract.get("amendments") or []:
        if a.get("type") == "EXTENSION" and a.get("status") == "PUBLISHED":
            new = _d((a.get("changes") or {}).get("new_end_date"))
            if new and (end is None or new > end):
                end = new
    return end


def version_for(contract: dict, on: date) -> dict | None:
    versions = sorted(contract.get("versions") or [], key=lambda v: v["version"])
    if not versions:
        return None
    chosen = [v for v in versions if _d(v["effective_from"]) <= on]
    return (chosen or versions[:1])[-1]


def covers(contract: dict, snapshot: dict, intake: str) -> tuple[bool, str]:
    """Whether this contract, as published, covers the intake -- and if not, why."""
    start = model.intake_start(intake)
    status = contract.get("status")
    if status == "DRAFT":
        return False, "the contract has not been published"
    if status == "EXPIRED":
        return False, "the contract is marked expired"
    if status == "INACTIVE":
        eff = _d(contract.get("status_effective_date"))
        if eff is None or start >= eff:
            return False, f"the contract is inactive{f' from {eff:%d %b %Y}' if eff else ''}"
    s = _d(snapshot.get("start_date"))
    end = None if snapshot.get("is_rolling") else extended_end({**snapshot, "amendments": contract.get("amendments")})
    if s and start < s:
        return False, f"the contract starts {s:%d %b %Y}"
    if end and start > end:
        return False, f"the contract ended {end:%d %b %Y}"
    if not in_scope(snapshot.get("intake_scope") or {}, intake):
        scope = snapshot.get("intake_scope") or {}
        if scope.get("mode") == "UP_TO":
            return False, f"the contract's terms run up to {model.intake_label(scope['until_intake'])}"
        return False, "the intake is outside the contract's intake scope"
    return True, ""


def amendment_applies(a: dict, intake: str, student_dates: dict | None) -> tuple[bool, str | None]:
    """(applies, condition). `condition` is set when a date window cannot be
    checked because the student date it needs was not given."""
    mode = a.get("scope_mode") or "INTAKE"
    ok_intake = True
    if mode in ("INTAKE", "BOTH"):
        lo, hi = a.get("from_intake"), a.get("until_intake")
        ok_intake = (not lo or intake >= lo) and (not hi or intake <= hi)
    if not ok_intake:
        return False, None
    if mode in ("DATE_WINDOW", "BOTH"):
        basis = a.get("applicability_basis") or "INTAKE_START"
        if basis == "INTAKE_START":
            when = model.intake_start(intake)
        else:
            when = _d((student_dates or {}).get(basis.lower()))
            if when is None:
                return False, f"applies if {basis.replace('_', ' ').lower()} is within the window"
        ws, we = _d(a.get("window_start")), _d(a.get("window_end"))
        if (ws and when < ws) or (we and when > we):
            return False, None
    return True, None


def _tag(items, source):
    out = []
    for it in items or []:
        it = copy.deepcopy(it)
        it.setdefault("source", source)
        out.append(it)
    return out


def apply_amendment(terms: dict, a: dict) -> dict | None:
    """Apply one amendment to resolved terms in place. Returns a no-terms dict
    for a suspension."""
    src = f"Amendment #{a['number']}"
    ch = a.get("changes") or {}
    kind = a["type"]
    if kind == "SUSPENSION":
        return no_terms(f"Suspended by amendment #{a['number']}", source=src)
    if kind == "RATE_CHANGE":
        targets = set(a.get("target_rule_ids") or [])
        terms["rules"] = [r for r in terms["rules"] if r["id"] not in targets]
        terms["rules"].extend(_tag(ch.get("rules"), src))
        drop = set(ch.get("remove_bonus_ids") or [])
        terms["bonuses"] = [b for b in terms["bonuses"] if b["id"] not in drop]
        terms["bonuses"].extend(_tag(ch.get("bonuses"), src))
    elif kind == "RULE_ADDITION":
        terms["rules"].extend(_tag(ch.get("rules"), src))
    elif kind == "BONUS_INCENTIVE":
        terms["bonuses"].extend(_tag(ch.get("bonuses"), src))
    elif kind == "SCOPE_CHANGE":
        drop = set(ch.get("remove_territory_rule_ids") or [])
        terms["territory_rules"] = [t for t in terms["territory_rules"] if t.get("id") not in drop]
        terms["territory_rules"].extend(_tag(ch.get("add_territory_rules"), src))
        drop = set(ch.get("remove_exclusion_ids") or [])
        terms["exclusions"] = [e for e in terms["exclusions"] if e.get("id") not in drop]
        terms["exclusions"].extend(_tag(ch.get("add_exclusions"), src))
        if ch.get("territory_type"):
            terms["territory_type"] = ch["territory_type"]
        campuses = [c for c in terms["campuses"] if c not in (ch.get("remove_campuses") or [])]
        terms["campuses"] = campuses + [c for c in ch.get("add_campuses") or [] if c not in campuses]
    elif kind == "INTAKE_NOTE":
        if ch.get("note"):
            terms["notes"].append({"text": ch["note"], "source": src})
        terms["targets"].extend(_tag(ch.get("targets"), src))
    elif kind == "EXTENSION":
        terms["notes"].append({"text": f"Contract extended to {ch.get('new_end_date')}", "source": src})
    return None


def resolve_one(contract: dict, intake: str, student_dates: dict | None = None) -> dict:
    start = model.intake_start(intake)
    version = version_for(contract, start)
    if version is None:
        return no_terms(f"No valid contract for {model.intake_label(intake)}: nothing published yet")
    snap = version["snapshot_json"]
    ok, why = covers(contract, snap, intake)
    if not ok:
        return no_terms(f"No valid contract for {model.intake_label(intake)}: {why}")
    base = f"Base v{version['version']}"
    t = snap.get("terms") or {}
    terms = {
        "rules": _tag(t.get("rules"), base),
        "bonuses": _tag(t.get("bonuses"), base),
        "territory_rules": _tag(t.get("territory_rules"), base),
        "exclusions": _tag(t.get("exclusions"), base),
        "campuses": list(t.get("campuses") or []),
        "targets": _tag(t.get("targets"), base),
        "notes": [],
        "territory_type": snap.get("territory_type"),
    }
    applied, conditional = [], []
    amendments = sorted(
        (a for a in contract.get("amendments") or [] if a.get("status") == "PUBLISHED"),
        key=lambda a: (str(a.get("received_on") or ""), a["number"]),
    )
    for a in amendments:
        hit, cond = amendment_applies(a, intake, student_dates)
        if cond:
            conditional.append({"number": a["number"], "type": a["type"], "condition": cond})
        if not hit:
            continue
        stop = apply_amendment(terms, a)
        applied.append({"number": a["number"], "type": a["type"], "summary": a.get("summary")})
        if stop:
            return {**stop, "reason": f"{stop['reason']} ({model.intake_label(intake)})", "applied": applied}
    return {
        "ok": True,
        "intake": intake,
        "contract": {"id": contract["id"], "code": contract.get("code"), "status": contract.get("status")},
        "version": version["version"],
        "currency": snap.get("currency"),
        "vat_treatment": snap.get("vat_treatment"),
        "vat_rate": snap.get("vat_rate"),
        "fee_basis": snap.get("fee_basis"),
        "milestones": t.get("milestones") or [{"trigger": "ENROLLED", "pct": 100, "default": True}],
        "payment_conditions": t.get("payment_conditions") or [],
        "other_conditions": t.get("other_conditions") or [],
        "applied": applied,
        "conditional": conditional,
        **terms,
    }


def resolve_terms(contracts: list[dict], intake: str, student_dates: dict | None = None) -> dict:
    """The first contract (latest start first) that yields terms for the intake;
    otherwise the most informative reason none did."""
    if not contracts:
        return no_terms(f"No valid contract for {model.intake_label(intake)}: no contract on file")
    ordered = sorted(contracts, key=lambda c: str(c.get("start_date") or ""), reverse=True)
    reasons = []
    for c in ordered:
        out = resolve_one(c, intake, student_dates)
        if out["ok"]:
            return out
        reasons.append(out)
    return reasons[0]
