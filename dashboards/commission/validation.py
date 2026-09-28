"""What a contract needs before it can be saved, and before it can be published.

Two different bars. Saving a draft is refused only for things that are wrong
rather than missing (overlapping tiers, milestones that do not add up to 100) --
a half-filled draft is the normal state of an import. Publishing needs the whole
checklist: the always-required fields, the fields the contract's own choices make
required (each one saying which choice, "because VAT = Exclusive"), and it lists
warnings that do not block.
"""
from datetime import date

from app.registry import get as _dashboard

model = _dashboard("commission").load_module("model")


def _item(key, label, ok, because=None, message=None, where=None):
    return {"key": key, "label": label, "ok": bool(ok), "because": because,
            "message": None if ok else (message or f"{label} is required"), "where": where}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tier_problems(tiers: list[dict]) -> list[str]:
    """Contiguous, non-overlapping, only the last open-ended, ascending from the
    first tier's minimum."""
    out = []
    if len(tiers) < 2:
        out.append("a tiered rule needs at least 2 tiers")
    ordered = sorted(tiers, key=lambda t: (_num(t.get("min_count")) or 0))
    for i, t in enumerate(ordered):
        lo, hi = _num(t.get("min_count")), _num(t.get("max_count"))
        if lo is None:
            out.append(f"tier {i + 1} has no minimum")
            continue
        if hi is not None and hi < lo:
            out.append(f"tier {i + 1} ends ({hi:g}) before it starts ({lo:g})")
        if hi is None and i != len(ordered) - 1:
            out.append(f"only the last tier may be open-ended (tier {i + 1} is)")
        if i + 1 < len(ordered):
            nxt = _num(ordered[i + 1].get("min_count"))
            if hi is not None and nxt is not None:
                if nxt <= hi:
                    out.append(f"tiers {i + 1} and {i + 2} overlap ({hi:g} / {nxt:g})")
                elif nxt != hi + 1:
                    out.append(f"gap between tier {i + 1} (to {hi:g}) and tier {i + 2} (from {nxt:g})")
        if _num(t.get("value")) is None:
            out.append(f"tier {i + 1} has no value")
    return out


def save_blockers(contract: dict) -> list[dict]:
    """Errors that stop even a draft from saving."""
    terms = contract.get("terms") or {}
    out = []
    for kind, items in (("rule", terms.get("rules") or []), ("bonus", terms.get("bonuses") or [])):
        for r in items:
            if (r.get("structure") == "TIERED" or kind == "bonus") and r.get("tiers") and len(r["tiers"]) >= 2:
                for p in tier_problems(r["tiers"]):
                    out.append({"where": f"{kind}:{r.get('id')}", "message": f"{r.get('name') or kind}: {p}"})
    ms = terms.get("milestones") or []
    if ms:
        total = sum(_num(m.get("pct")) or 0 for m in ms)
        if abs(total - 100) > 1e-6:
            out.append({"where": "milestones", "message": f"payment milestones add up to {total:g}%, not 100%"})
    return out


def _rule_items(r: dict, contract: dict, idx: int) -> list[dict]:
    name = r.get("name") or f"Rule {idx + 1}"
    where = f"rule:{r.get('id')}"
    items = [
        _item(f"{where}:name", f"{name}: name", r.get("name"), where=where),
        _item(f"{where}:levels", f"{name}: course levels", r.get("course_levels"), where=where),
        _item(f"{where}:structure", f"{name}: structure", r.get("structure") in model.STRUCTURE, where=where),
        _item(f"{where}:pricing", f"{name}: pricing", r.get("pricing") in model.PRICING, where=where),
    ]
    if contract.get("party_type") in ("PATHWAY_PROVIDER", "OUTBOUND_AGENT"):
        items.append(_item(f"{where}:inst", f"{name}: institution", r.get("institution_id"),
                           because=f"party type = {contract['party_type'].replace('_', ' ').title()}", where=where))
    if r.get("structure") == "TIERED":
        tiers = r.get("tiers") or []
        probs = tier_problems(tiers)
        items.append(_item(f"{where}:tiers", f"{name}: tiers", not probs, because="structure = Tiered",
                           message="; ".join(probs), where=where))
        for f, label in (("tier_mode", "tier mode"), ("count_metric", "count metric"), ("count_scope", "count scope")):
            items.append(_item(f"{where}:{f}", f"{name}: {label}", r.get(f), because="structure = Tiered", where=where))
        values = [_num(t.get("value")) for t in tiers]
    else:
        values = [_num(r.get("value"))]
        items.append(_item(f"{where}:value", f"{name}: value", values[0] is not None, where=where))
    if r.get("pricing") == "PERCENT":
        bad = [v for v in values if v is not None and not 0 <= v <= 100]
        items.append(_item(f"{where}:pct", f"{name}: percentage between 0 and 100", not bad,
                           because="pricing = Percent", where=where))
        items.append(_item(f"{where}:fys", f"{name}: fee year scope", r.get("fee_year_scope"),
                           because="pricing = Percent", where=where))
    elif r.get("pricing") == "FLAT":
        bad = [v for v in values if v is not None and v <= 0]
        items.append(_item(f"{where}:flat", f"{name}: flat fee above 0", not bad,
                           because="pricing = Flat fee", where=where))
    scope = r.get("count_scope")
    if scope == "CUSTOM_WINDOW":
        items.append(_item(f"{where}:window", f"{name}: count window start and end",
                           r.get("count_window_start") and r.get("count_window_end"),
                           because="count scope = Custom window", where=where))
    if scope == "COMBINED_INTAKES":
        items.append(_item(f"{where}:combined", f"{name}: at least 2 combined intakes",
                           len(r.get("count_intakes") or []) >= 2,
                           because="count scope = Combined intakes", where=where))
    return items


def checklist(contract: dict, today: date | None = None, amendments: list[dict] | None = None) -> dict:
    """The "Ready to publish?" panel: always required, required by choices,
    warnings. `ready` is true when nothing in the first two groups is failing."""
    today = today or date.today()
    terms = contract.get("terms") or {}
    rules = terms.get("rules") or []
    c = contract

    always = [
        _item("party_type", "Party type", c.get("party_type") in model.PARTY_TYPES),
        _item("party", "Party", c.get("party_id") or c.get("party_name")),
        _item("region", "Region", c.get("region") in model.REGIONS),
        _item("status", "Status", c.get("status") in model.STATUSES),
        _item("start_date", "Start date", c.get("start_date")),
        _item("end_date", "End date or rolling", c.get("end_date") or c.get("is_rolling")),
        _item("currency", "Currency", c.get("currency")),
        _item("vat_treatment", "VAT treatment", c.get("vat_treatment") in model.VAT),
        _item("fee_basis", "Fee basis", c.get("fee_basis") in model.FEE_BASIS),
        _item("academic_years", "Academic years", c.get("academic_years")),
        _item("intake_scope", "Intake scope", (c.get("intake_scope") or {}).get("mode") in model.INTAKE_SCOPE_MODES),
        _item("territory_type", "Territory type", c.get("territory_type") in model.TERRITORY),
        _item("rules", "At least one commission rule", rules),
    ]

    choices = []
    pt = c.get("party_type")
    if pt in ("PATHWAY_PROVIDER", "OUTBOUND_AGENT"):
        choices.append(_item("covered", "At least one covered institution", c.get("covered_institution_ids"),
                             because=f"party type = {pt.replace('_', ' ').title()}"))
    if c.get("status") == "INACTIVE":
        choices.append(_item("status_reason", "Status reason", c.get("status_reason"), because="status = Inactive"))
        choices.append(_item("status_effective_date", "Status effective date", c.get("status_effective_date"),
                             because="status = Inactive"))
    if not c.get("is_rolling") and c.get("start_date") and c.get("end_date"):
        choices.append(_item("end_after_start", "End date after start date",
                             str(c["end_date"]) > str(c["start_date"]), because="the contract is not rolling"))
    tr = terms.get("territory_rules") or []
    if c.get("territory_type") == "GLOBAL_WITH_RESTRICTIONS":
        choices.append(_item("excludes", "At least one excluded territory",
                             any(t.get("type") == "EXCLUDE" for t in tr), because="territory = Global with restrictions"))
    if c.get("territory_type") == "NOT_GLOBAL":
        choices.append(_item("includes", "At least one included territory",
                             any(t.get("type") == "INCLUDE" for t in tr), because="territory = Not global"))
    if c.get("vat_treatment") in ("INCLUSIVE", "EXCLUSIVE"):
        choices.append(_item("vat_rate", "VAT rate", _num(c.get("vat_rate")) is not None,
                             because=f"VAT = {c['vat_treatment'].title()}"))
    scope = c.get("intake_scope") or {}
    if scope.get("mode") == "INTAKES":
        choices.append(_item("scope_intakes", "At least one intake", scope.get("intakes"), because="intake scope = listed intakes"))
    if scope.get("mode") == "UP_TO":
        choices.append(_item("scope_until", "Last intake", scope.get("until_intake"), because="intake scope = up to an intake"))
    for i, r in enumerate(rules):
        choices.extend(_rule_items(r, c, i))
    for b in terms.get("bonuses") or []:
        name = b.get("criteria_text") or "Bonus"
        where = f"bonus:{b.get('id')}"
        choices.append(_item(f"{where}:kind", f"{name[:40]}: bonus kind", b.get("kind") in model.BONUS_KIND,
                             because="a bonus was added", where=where))
        choices.append(_item(f"{where}:tiers", f"{name[:40]}: thresholds", b.get("tiers"),
                             because="a bonus was added", where=where))
        if b.get("count_scope") == "COMBINED_INTAKES":
            choices.append(_item(f"{where}:combined", f"{name[:40]}: at least 2 combined intakes",
                                 len(b.get("count_intakes") or []) >= 2, because="count scope = Combined intakes", where=where))
    for e in terms.get("exclusions") or []:
        if e.get("cap_count") is not None or e.get("cap_scope"):
            choices.append(_item(f"excl:{e.get('id')}:cap", f"{e.get('type')}: cap count and scope",
                                 e.get("cap_count") is not None and e.get("cap_scope"), because="the exclusion has a cap"))
    for s in save_blockers(c):
        choices.append(_item(f"save:{s['where']}", s["message"], False, message=s["message"], where=s["where"]))

    warnings = []
    if not terms.get("milestones"):
        warnings.append({"key": "milestones", "message": "No payment milestones: 100% is due on Enrolled."})
    for r in rules + (terms.get("bonuses") or []):
        if r.get("needs_review"):
            warnings.append({"key": f"review:{r.get('id')}", "where": r.get("source_cell"),
                             "message": f"Needs review: {r.get('review_note') or r.get('name') or r.get('criteria_text') or ''}".strip()})
    for item in terms.get("review_items") or []:
        warnings.append({"key": f"review:{item.get('cell')}", "where": item.get("cell"),
                         "message": f"Needs review: {item.get('message')}"})
    for a in amendments or []:
        if a.get("type") == "SCOPE_CHANGE" and a.get("scope_mode") != "DATE_WINDOW" and not a.get("until_intake"):
            warnings.append({"key": f"open:{a.get('id')}",
                             "message": f"Amendment #{a.get('number')} is an open-ended scope change."})
    end = c.get("end_date")
    if end and not c.get("is_rolling"):
        days = (date.fromisoformat(str(end)) - today).days
        if 0 <= days <= 90:
            warnings.append({"key": "expiry", "message": f"Contract ends in {days} days."})

    failing = [i for i in always + choices if not i["ok"]]
    return {"ready": not failing, "always": always, "choices": choices, "warnings": warnings,
            "failing": len(failing)}
