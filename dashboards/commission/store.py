"""Everything that reads or writes the commission schema.

Every function takes an open cursor whose search_path already points at
dash_commission (router.py and the tests set it), so the caller owns the
transaction: a request commits once at the end, a test rolls back. Every write
goes through audit().
"""
import copy
import json
import re
from datetime import date, datetime
from decimal import Decimal

from app.registry import get as _dashboard

_dash = _dashboard("commission")
model = _dash.load_module("model")
validation = _dash.load_module("validation")
resolve = _dash.load_module("resolve")
calc = _dash.load_module("calc")


class CommissionError(Exception):
    def __init__(self, message: str, status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail or {}


HEADER = ("party_type", "party_id", "covered_institution_ids", "region", "status", "status_reason",
          "status_effective_date", "start_date", "end_date", "is_rolling", "currency", "vat_treatment",
          "vat_rate", "fee_basis", "territory_type", "academic_years", "intake_scope")
TERMS_KEYS = ("territory_rules", "campuses", "rules", "bonuses", "exclusions", "milestones",
              "payment_conditions", "agent_change_rules", "targets", "invoicing", "other_conditions",
              "review_items")
AMENDMENT_FIELDS = ("type", "reference", "received_on", "document_file", "scope_mode", "from_intake",
                    "until_intake", "window_start", "window_end", "applicability_basis", "target_rule_ids",
                    "supersedes_amendment_id", "needs_review", "summary", "changes", "source_cell")
DATE_FIELDS = {"status_effective_date", "start_date", "end_date", "received_on", "window_start", "window_end"}


def jsonable(v):
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _date(v):
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def audit(cur, contract_id, entity, entity_id, action, before=None, after=None, user=None, document_ref=None):
    cur.execute(
        """insert into audit_log (contract_id, entity, entity_id, action, before_json, after_json, "user", document_ref)
           values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)""",
        (contract_id, entity, str(entity_id), action,
         json.dumps(jsonable(before)) if before is not None else None,
         json.dumps(jsonable(after)) if after is not None else None, user, document_ref),
    )


# --- institutions -------------------------------------------------------------

def ensure_institution(cur, name: str, country: str | None = None, region: str | None = None) -> int:
    norm = model.normalize_name(name)
    if not norm:
        raise CommissionError("institution name is empty")
    cur.execute("select id from institutions where normalized_name = %s", (norm,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(
        "insert into institutions (name, normalized_name, country, region) values (%s, %s, %s, %s) returning id",
        (name.strip(), norm, country, region),
    )
    return cur.fetchone()["id"]


def institutions(cur) -> list[dict]:
    cur.execute("select id, name, country, region, campuses from institutions order by name")
    return cur.fetchall()


def masters(cur) -> dict:
    cur.execute("select name from course_levels order by sort_order")
    levels = [r["name"] for r in cur.fetchall()]
    cur.execute("select code, name, parent, aliases from countries order by parent nulls first, name")
    return {
        "course_levels": levels, "countries": cur.fetchall(),
        "enums": {k.lower(): list(getattr(model, k)) for k in (
            "PARTY_TYPES", "REGIONS", "STATUSES", "VAT", "FEE_BASIS", "TERRITORY", "INTAKE_SCOPE_MODES",
            "PRICING", "STRUCTURE", "FEE_YEAR_SCOPE", "TIER_MODE", "COUNT_METRIC", "COUNT_SCOPE",
            "BONUS_KIND", "TERRITORY_RULE_TYPE", "TERRITORY_SCOPE", "EXCLUSION_TYPES", "MILESTONE_TRIGGERS",
            "PAYMENT_CONDITIONS", "AGENT_CHANGE", "AMENDMENT_TYPES", "SCOPE_MODES", "APPLICABILITY")},
    }


# --- contracts ----------------------------------------------------------------

def _clean_terms(terms: dict | None) -> dict:
    terms = copy.deepcopy(terms or {})
    out = {k: terms.get(k) for k in TERMS_KEYS if terms.get(k) is not None}
    for key, prefix in (("rules", "r"), ("bonuses", "b"), ("territory_rules", "t"), ("exclusions", "x")):
        for item in out.get(key) or []:
            item.setdefault("id", model.new_id(prefix))
    return out


def _code(cur, name: str, start) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in ("of", "the", "and", "university")]
    stem = ("".join(w[0] for w in words[:4]) or "C").upper()
    year = _date(start).year if start else date.today().year
    code, n = f"{stem}-{year}", 1
    cur.execute("select code from contracts where code like %s", (f"{stem}-{year}%",))
    taken = {r["code"] for r in cur.fetchall()}
    while code in taken:
        n += 1
        code = f"{stem}-{year}-{n}"
    return code


def _fetch(cur, contract_id: int) -> dict:
    cur.execute(
        """select c.*, i.name as party_name,
                  (select coalesce(json_agg(json_build_object('id', ci.id, 'name', ci.name) order by ci.name), '[]')
                     from institutions ci where ci.id = any(c.covered_institution_ids)) as covered_institutions
             from contracts c left join institutions i on i.id = c.party_id
            where c.id = %s""",
        (contract_id,),
    )
    row = cur.fetchone()
    if not row:
        raise CommissionError(f"no contract {contract_id}", 404)
    return row


def _header_values(data: dict) -> dict:
    out = {}
    for f in HEADER:
        if f not in data:
            continue
        v = data[f]
        if f in DATE_FIELDS:
            v = _date(v)
        if f == "intake_scope":
            v = json.dumps(v or {"mode": "ENTIRE_YEAR"})
        if f in ("academic_years", "covered_institution_ids"):
            v = list(v or [])
        out[f] = v
    if out.get("is_rolling"):
        out["end_date"] = None
    return out


def create_contract(cur, data: dict, user: str | None) -> dict:
    party_id = data.get("party_id")
    if not party_id:
        if not data.get("party_name"):
            raise CommissionError("a contract needs a party (institution, provider or agent)")
        party_id = ensure_institution(cur, data["party_name"], data.get("country"), data.get("region"))
    header = _header_values({**data, "party_id": party_id})
    header["status"] = "DRAFT"
    terms = _clean_terms(data.get("terms"))
    blockers = validation.save_blockers({"terms": terms})
    if blockers:
        raise CommissionError("cannot save", 422, {"blockers": blockers})
    cur.execute("select name from institutions where id = %s", (party_id,))
    name = cur.fetchone()["name"]
    cols = list(header) + ["code", "terms", "created_by", "source_tab", "source_rows", "import_batch_id"]
    vals = list(header.values()) + [data.get("code") or _code(cur, name, header.get("start_date")),
                                    json.dumps(terms), user, data.get("source_tab"), data.get("source_rows"),
                                    data.get("import_batch_id")]
    cur.execute(
        f"insert into contracts ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) returning id",
        vals,
    )
    cid = cur.fetchone()["id"]
    row = contract_row(cur, cid)
    audit(cur, cid, "contract", cid, "create", None, row, user)
    return row


def contract_row(cur, contract_id: int) -> dict:
    return jsonable(_fetch(cur, contract_id))


def update_contract(cur, contract_id: int, data: dict, user: str | None) -> dict:
    before = contract_row(cur, contract_id)
    header = _header_values(data)
    header.pop("status", None)          # status moves through publish / set_status, not edits
    terms = _clean_terms(data["terms"]) if "terms" in data else before["terms"]
    blockers = validation.save_blockers({"terms": terms})
    if blockers:
        raise CommissionError("cannot save", 422, {"blockers": blockers})
    if data.get("party_name") and not data.get("party_id"):
        header["party_id"] = ensure_institution(cur, data["party_name"])
    sets = [f"{k} = %s" for k in header] + ["terms = %s", "has_unpublished = true", "updated_at = now()"]
    cur.execute(f"update contracts set {', '.join(sets)} where id = %s",
                [*header.values(), json.dumps(terms), contract_id])
    after = contract_row(cur, contract_id)
    audit(cur, contract_id, "contract", contract_id, "update", before, after, user)
    return after


def snapshot(row: dict) -> dict:
    return jsonable({**{f: row.get(f) for f in HEADER}, "code": row.get("code"),
                     "party_name": row.get("party_name"), "terms": row.get("terms") or {}})


def amendments_of(cur, contract_id: int, published_only: bool = False) -> list[dict]:
    cur.execute(
        f"""select * from amendments where contract_id = %s
            {"and status = 'PUBLISHED'" if published_only else ""} order by number""",
        (contract_id,),
    )
    return [jsonable(r) for r in cur.fetchall()]


def versions_of(cur, contract_id: int) -> list[dict]:
    cur.execute("select * from contract_versions where contract_id = %s order by version", (contract_id,))
    return [jsonable(r) for r in cur.fetchall()]


def contract_checklist(cur, contract_id: int, today: date | None = None) -> dict:
    row = contract_row(cur, contract_id)
    return validation.checklist(row, today, amendments_of(cur, contract_id))


def publish_contract(cur, contract_id: int, user: str | None, effective_from=None,
                     today: date | None = None) -> dict:
    today = today or date.today()
    row = contract_row(cur, contract_id)
    check = validation.checklist(row, today, amendments_of(cur, contract_id))
    if not check["ready"]:
        raise CommissionError("not ready to publish", 409, {"checklist": check})
    version = row["current_version"] + 1
    eff = _date(effective_from) or (_date(row["start_date"]) if version == 1 else today)
    cur.execute(
        """insert into contract_versions (contract_id, version, effective_from, snapshot_json, published_by)
           values (%s, %s, %s, %s::jsonb, %s)""",
        (contract_id, version, eff, json.dumps(snapshot(row)), user),
    )
    status = "ACTIVE" if row["status"] == "DRAFT" else row["status"]
    cur.execute(
        """update contracts set current_version = %s, status = %s, has_unpublished = false,
                  published_by = %s, published_at = now() where id = %s""",
        (version, status, user, contract_id),
    )
    if version > 1 and eff < today:
        raise_recalc(cur, contract_id, f"Base v{version} published effective {eff:%d %b %Y}, backdated",
                     model.intake_of(eff), user)
    after = contract_row(cur, contract_id)
    audit(cur, contract_id, "contract_version", f"{contract_id}:v{version}", "publish", None,
          {"version": version, "effective_from": eff}, user)
    return after


def set_status(cur, contract_id: int, status: str, reason: str | None, effective, user: str | None) -> dict:
    if status not in ("ACTIVE", "INACTIVE", "EXPIRED"):
        raise CommissionError(f"status {status} cannot be set directly")
    before = contract_row(cur, contract_id)
    if before["current_version"] == 0:
        raise CommissionError("publish the contract before changing its status", 409)
    if status == "INACTIVE" and (not reason or not effective):
        raise CommissionError("an inactive contract needs a reason and an effective date", 422)
    cur.execute(
        """update contracts set status = %s, status_reason = %s, status_effective_date = %s, updated_at = now()
            where id = %s""",
        (status, reason, _date(effective), contract_id),
    )
    after = contract_row(cur, contract_id)
    audit(cur, contract_id, "contract", contract_id, "status", {"status": before["status"]},
          {"status": status, "reason": reason, "effective": effective}, user)
    return after


def delete_draft_contract(cur, contract_id: int, user: str | None) -> None:
    row = contract_row(cur, contract_id)
    if row["current_version"] > 0:
        raise CommissionError("a published contract cannot be deleted; mark it inactive instead", 409)
    cur.execute("delete from contracts where id = %s", (contract_id,))
    audit(cur, contract_id, "contract", contract_id, "delete", row, None, user)


def raise_recalc(cur, contract_id: int, reason: str, from_intake: str | None, user: str | None) -> None:
    cur.execute(
        "insert into recalc_batches (contract_id, reason, from_intake, created_by) values (%s, %s, %s, %s) returning id",
        (contract_id, reason, from_intake, user),
    )
    bid = cur.fetchone()["id"]
    audit(cur, contract_id, "recalc_batch", bid, "create", None, {"reason": reason, "from_intake": from_intake}, user)


# --- amendments ---------------------------------------------------------------

def _amendment_values(data: dict) -> dict:
    out = {}
    for f in AMENDMENT_FIELDS:
        if f not in data:
            continue
        v = data[f]
        if f in DATE_FIELDS:
            v = _date(v)
        if f == "changes":
            v = copy.deepcopy(v or {})
            for key, prefix in (("rules", "r"), ("bonuses", "b"), ("add_territory_rules", "t"), ("add_exclusions", "x")):
                for item in v.get(key) or []:
                    item.setdefault("id", model.new_id(prefix))
            v = json.dumps(v)
        if f == "target_rule_ids":
            v = list(v or [])
        out[f] = v
    return out


def _amendment(cur, amendment_id: int) -> dict:
    cur.execute("select * from amendments where id = %s", (amendment_id,))
    row = cur.fetchone()
    if not row:
        raise CommissionError(f"no amendment {amendment_id}", 404)
    return jsonable(row)


def create_amendment(cur, contract_id: int, data: dict, user: str | None) -> dict:
    _fetch(cur, contract_id)
    if data.get("type") not in model.AMENDMENT_TYPES:
        raise CommissionError("choose an amendment type", 422)
    vals = _amendment_values(data)
    cur.execute("select coalesce(max(number), 0) + 1 as n from amendments where contract_id = %s", (contract_id,))
    number = data.get("number") or cur.fetchone()["n"]
    cols = ["contract_id", "number", "created_by", *vals]
    cur.execute(
        f"insert into amendments ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) returning id",
        [contract_id, number, user, *vals.values()],
    )
    aid = cur.fetchone()["id"]
    row = _amendment(cur, aid)
    audit(cur, contract_id, "amendment", aid, "create", None, row, user, row.get("document_file"))
    return row


def update_amendment(cur, amendment_id: int, data: dict, user: str | None) -> dict:
    before = _amendment(cur, amendment_id)
    if before["status"] != "DRAFT":
        raise CommissionError("a published amendment cannot be edited; add a new one that supersedes it", 409)
    vals = _amendment_values(data)
    if vals:
        cur.execute(f"update amendments set {', '.join(f'{k} = %s' for k in vals)} where id = %s",
                    [*vals.values(), amendment_id])
    after = _amendment(cur, amendment_id)
    audit(cur, before["contract_id"], "amendment", amendment_id, "update", before, after, user, after.get("document_file"))
    return after


def delete_amendment(cur, amendment_id: int, user: str | None) -> None:
    row = _amendment(cur, amendment_id)
    if row["status"] != "DRAFT":
        raise CommissionError("a published amendment cannot be deleted", 409)
    cur.execute("delete from amendments where id = %s", (amendment_id,))
    audit(cur, row["contract_id"], "amendment", amendment_id, "delete", row, None, user)


def _range(a: dict) -> tuple[str, str]:
    lo = a.get("from_intake") or (model.intake_of(_date(a["window_start"])) if a.get("window_start") else "0000-00")
    hi = a.get("until_intake") or (model.intake_of(_date(a["window_end"])) if a.get("window_end") else "9999-12")
    return lo, hi


def _supersedes(a: dict, b: dict, all_by_id: dict) -> bool:
    """True if a supersedes b, directly or through a chain."""
    seen, cur_id = set(), a.get("supersedes_amendment_id")
    while cur_id and cur_id not in seen:
        if cur_id == b["id"]:
            return True
        seen.add(cur_id)
        cur_id = (all_by_id.get(cur_id) or {}).get("supersedes_amendment_id")
    return False


def amendment_checks(cur, amendment_id: int, today: date | None = None) -> list[dict]:
    """What stands between this amendment and publishing, as check items."""
    today = today or date.today()
    a = _amendment(cur, amendment_id)
    c = contract_row(cur, a["contract_id"])
    everything = amendments_of(cur, a["contract_id"])
    by_id = {x["id"]: x for x in everything}
    checks = []

    def add(key, label, ok, message=None, block=True):
        checks.append({"key": key, "label": label, "ok": bool(ok), "block": block,
                       "message": None if ok else (message or f"{label} is required")})

    add("type", "Type", a.get("type") in model.AMENDMENT_TYPES)
    add("reference", "Reference", a.get("reference"))
    add("received_on", "Received on", a.get("received_on"))
    add("document", "Document", a.get("document_file"))
    mode = a.get("scope_mode") if a.get("type") != "EXTENSION" else None   # an extension's scope is its new end date
    if mode in ("INTAKE", "BOTH"):
        add("from_intake", "From intake", a.get("from_intake"))
        if a.get("from_intake") and a.get("until_intake"):
            add("intake_order", "Until intake on or after from intake", a["until_intake"] >= a["from_intake"])
    if mode in ("DATE_WINDOW", "BOTH"):
        add("window", "Window start and end", a.get("window_start") and a.get("window_end"))
        if a.get("window_start") and a.get("window_end"):
            add("window_order", "Window end after start", a["window_end"] >= a["window_start"])
    add("published_base", "Base terms published", c["current_version"] > 0,
        "publish the base terms before any amendment")

    ch = a.get("changes") or {}
    t = a.get("type")
    if t == "RATE_CHANGE":
        add("targets", "Target rules", a.get("target_rule_ids") or ch.get("rules"),
            "pick the rules this changes, or give the new rules")
    if t == "RULE_ADDITION":
        add("rules", "At least one rule", ch.get("rules"))
    if t == "BONUS_INCENTIVE":
        add("bonuses", "At least one bonus", ch.get("bonuses"))
    if t == "EXTENSION":
        new_end = _date(ch.get("new_end_date"))
        add("new_end", "New end date after the current end",
            new_end and (c.get("is_rolling") or not c.get("end_date") or new_end > _date(c["end_date"])))
    for kind, items in (("rule", ch.get("rules") or []), ("bonus", ch.get("bonuses") or [])):
        for r in items:
            if r.get("tiers") and len(r["tiers"]) >= 2:
                for p in validation.tier_problems(r["tiers"]):
                    add(f"tiers:{r.get('id')}", f"{r.get('name') or kind} tiers", False, p)

    # scope must sit inside the contract's validity, unless this is the extension
    if t != "EXTENSION" and c["current_version"] > 0:
        start = _date(c.get("start_date"))
        end = None if c.get("is_rolling") else resolve.extended_end({**c, "amendments": [x for x in everything if x["status"] == "PUBLISHED"]})
        outside = []
        for label, d in (("from intake", a.get("from_intake") and model.intake_start(a["from_intake"])),
                         ("until intake", a.get("until_intake") and model.intake_start(a["until_intake"])),
                         ("window start", _date(a.get("window_start"))), ("window end", _date(a.get("window_end")))):
            if d and ((start and d < start) or (end and d > end)):
                outside.append(f"{label} {d:%d %b %Y}")
        span = f"{start:%d %b %Y} – {end:%d %b %Y}" if start and end else (f"from {start:%d %b %Y}" if start else "")
        add("validity", "Scope within contract validity", not outside,
            f"outside the contract's validity ({span}): {', '.join(outside)}. Renew the contract or record an extension.")

    # two published amendments changing the same rule for the same intake
    if t in ("RATE_CHANGE", "SCOPE_CHANGE") and a.get("target_rule_ids"):
        lo, hi = _range(a)
        mine = set(a["target_rule_ids"])
        for o in everything:
            if o["id"] == a["id"] or o["status"] != "PUBLISHED" or not set(o.get("target_rule_ids") or []) & mine:
                continue
            olo, ohi = _range(o)
            if lo <= ohi and olo <= hi and not _supersedes(a, o, by_id) and not _supersedes(o, a, by_id):
                add(f"conflict:{o['id']}", f"No clash with amendment #{o['number']}", False,
                    f"amendment #{o['number']} already changes the same rule for overlapping intakes; set which one it supersedes")
    if a.get("needs_review"):
        add("review", "Reviewed", False, "flagged needs review on import; clear the flag once checked", block=False)
    return checks


def publish_amendment(cur, amendment_id: int, user: str | None, today: date | None = None) -> dict:
    today = today or date.today()
    a = _amendment(cur, amendment_id)
    if a["status"] == "PUBLISHED":
        raise CommissionError("already published", 409)
    checks = amendment_checks(cur, amendment_id, today)
    failing = [c for c in checks if c["block"] and not c["ok"]]
    if failing:
        raise CommissionError(failing[0]["message"], 409, {"checks": checks})
    cur.execute("update amendments set status = 'PUBLISHED', published_by = %s, published_at = now() where id = %s",
                (user, amendment_id))
    lo, _ = _range(a)
    if lo != "0000-00" and model.intake_start(lo) <= today:
        raise_recalc(cur, a["contract_id"], f"Amendment #{a['number']} published with a backdated scope from {model.intake_label(lo)}",
                     lo, user)
    after = _amendment(cur, amendment_id)
    audit(cur, a["contract_id"], "amendment", amendment_id, "publish", a, after, user, a.get("document_file"))
    return after


# --- resolution ---------------------------------------------------------------

def load_full(cur, contract_id: int, extra_amendment: dict | None = None) -> dict:
    """The live row + published versions + published amendments, the shape
    resolve.py takes. `extra_amendment` is treated as published (previews)."""
    row = contract_row(cur, contract_id)
    row["versions"] = versions_of(cur, contract_id)
    row["amendments"] = amendments_of(cur, contract_id, published_only=True)
    if extra_amendment:
        row["amendments"] = [x for x in row["amendments"] if x["id"] != extra_amendment["id"]]
        row["amendments"].append({**extra_amendment, "status": "PUBLISHED"})
    return row


def load_for_institution(cur, institution_id: int) -> list[dict]:
    cur.execute(
        "select id from contracts where party_id = %s or %s = any(covered_institution_ids)",
        (institution_id, institution_id),
    )
    return [load_full(cur, r["id"]) for r in cur.fetchall()]


def resolve_terms(cur, institution_id: int, intake: str, student_dates: dict | None = None) -> dict:
    return resolve.resolve_terms(load_for_institution(cur, institution_id), intake, student_dates)


def effective(cur, contract_id: int, intake: str, student_dates: dict | None = None) -> dict:
    return resolve.resolve_one(load_full(cur, contract_id), intake, student_dates)


def simulate(cur, contract_id: int, intake: str, student: dict) -> dict:
    terms = effective(cur, contract_id, intake, student.get("dates"))
    return {"terms_ok": terms["ok"], "result": calc.calculate(terms, student)}


def amendment_preview(cur, amendment_id: int, today: date | None = None) -> dict:
    """Before/after resolved terms for each intake the amendment touches, plus
    the publish checks."""
    today = today or date.today()
    a = _amendment(cur, amendment_id)
    c = load_full(cur, a["contract_id"])
    lo, hi = _range(a)
    if lo == "0000-00":
        lo = model.intake_of(today)
    stop = hi if hi != "9999-12" else model.add_months(lo, 12)
    intakes, i = [], lo
    while i <= stop and len(intakes) < 6:
        if int(i[-2:]) in model.MAJOR_MONTHS or i in (lo, hi):
            intakes.append(i)
        i = model.add_months(i, 1)
    after_c = load_full(cur, a["contract_id"], extra_amendment=a)
    rows = [{"intake": x, "label": model.intake_label(x),
             "before": resolve.resolve_one(c, x), "after": resolve.resolve_one(after_c, x)} for x in intakes]
    return {"amendment": a, "intakes": rows, "checks": amendment_checks(cur, amendment_id, today),
            "open_ended": a.get("scope_mode") != "DATE_WINDOW" and not a.get("until_intake")}


# --- screens ------------------------------------------------------------------

def _review_count(terms: dict) -> int:
    return (sum(1 for r in (terms.get("rules") or []) + (terms.get("bonuses") or []) if r.get("needs_review"))
            + len(terms.get("review_items") or []))


def list_contracts(cur, today: date | None = None) -> list[dict]:
    today = today or date.today()
    cur.execute(
        """select c.id, c.code, c.party_type, c.region, c.status, c.status_reason, c.start_date, c.end_date,
                  c.is_rolling, c.current_version, c.has_unpublished, c.terms, c.source_tab,
                  c.party_id, i.name as party_name,
                  (select count(*) from amendments a where a.contract_id = c.id) as amendments,
                  (select count(*) from amendments a where a.contract_id = c.id and a.status = 'DRAFT') as draft_amendments,
                  (select count(*) from amendments a where a.contract_id = c.id and a.needs_review and a.status = 'DRAFT') as amendments_review
             from contracts c left join institutions i on i.id = c.party_id
            order by i.name, c.start_date"""
    )
    rows = [jsonable(r) for r in cur.fetchall()]
    # the next intake still to start: one already under way this month has its terms settled
    here = model.intake_of(today)
    nxt = next((x for x in model.major_intakes_around(today, 0, 2) if x > here), None)
    out = []
    for r in rows:
        terms = r.pop("terms") or {}
        alerts = []
        days = None
        if r["end_date"] and not r["is_rolling"]:
            days = (_date(r["end_date"]) - today).days
            if 0 <= days <= 90 and r["status"] == "ACTIVE":
                alerts.append({"kind": "expiry", "message": f"Ends in {days} days"})
        if r["status"] == "ACTIVE" and nxt:
            res = effective(cur, r["id"], nxt)
            if not res["ok"]:
                alerts.append({"kind": "gap", "message": f"No terms for {model.intake_label(nxt)}"})
        if r["has_unpublished"] and r["current_version"] > 0:
            alerts.append({"kind": "draft", "message": "Unpublished edits"})
        out.append({**r, "days_to_expiry": days, "needs_review": _review_count(terms) + r.pop("amendments_review"),
                    "rules": len(terms.get("rules") or []), "alerts": alerts})
    return out


def timeline(cur, contract_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    c = load_full(cur, contract_id)
    here = model.intake_of(today)
    majors = model.major_intakes_around(today, 4, 8)
    default = model.major_intakes_around(today, 2, 4)
    columns = []
    for x in majors:
        res = resolve.resolve_one(c, x)
        summary = None
        if res["ok"]:
            summary = {
                "rules": [{"name": r.get("name"), "rate": _rate_text(r, res.get("currency")), "source": r.get("source")}
                          for r in res["rules"]],
                "bonuses": [{"criteria": b.get("criteria_text"), "kind": b.get("kind"), "source": b.get("source")}
                            for b in res["bonuses"]],
                "excluded": [{"value": t.get("value"), "source": t.get("source")}
                             for t in res["territory_rules"] if t.get("type") == "EXCLUDE"],
                "applied": res["applied"], "version": res["version"],
            }
        columns.append({"intake": x, "label": model.intake_label(x), "past": x < here, "current": x == here,
                        "in_default": x in default, "ok": res["ok"], "reason": res.get("reason"), "summary": summary})
    all_amendments = amendments_of(cur, contract_id)
    end = None if c.get("is_rolling") else resolve.extended_end(c)
    checks = validation.checklist(c, today, all_amendments)
    return {
        "columns": columns,
        "validity": {"start": c.get("start_date"), "end": end and end.isoformat(), "rolling": c.get("is_rolling"),
                     "scope": c.get("intake_scope")},
        "versions": [{"version": v["version"], "effective_from": v["effective_from"],
                      "published_at": v["published_at"], "published_by": v["published_by"]} for v in c["versions"]],
        "amendments": [{k: x.get(k) for k in ("id", "number", "type", "status", "summary", "scope_mode", "from_intake",
                                             "until_intake", "window_start", "window_end", "needs_review", "received_on")}
                       for x in all_amendments],
        "alerts": [col for col in columns if not col["ok"] and not col["past"] and col["in_default"]],
        "checks": checks,
    }


def _rate_text(rule: dict, currency: str | None) -> str:
    def one(v):
        return f"{float(v):g}%" if rule.get("pricing") == "PERCENT" else model.fmt_money(float(v), currency)
    if rule.get("structure") == "TIERED":
        return " / ".join(one(t["value"]) for t in rule.get("tiers") or [] if t.get("value") is not None) + " tiered"
    return one(rule["value"]) if rule.get("value") is not None else "—"


def audit_entries(cur, contract_id: int, entity: str | None = None, action: str | None = None) -> list[dict]:
    q = "select * from audit_log where contract_id = %s"
    args = [contract_id]
    if entity:
        q += " and entity = %s"
        args.append(entity)
    if action:
        q += " and action = %s"
        args.append(action)
    cur.execute(q + " order by created_at desc, id desc limit 500", args)
    return [jsonable(r) for r in cur.fetchall()]


def contract_detail(cur, contract_id: int, today: date | None = None) -> dict:
    row = contract_row(cur, contract_id)
    ams = amendments_of(cur, contract_id)
    cur.execute("select * from recalc_batches where contract_id = %s order by created_at desc", (contract_id,))
    return {
        "contract": row, "versions": [{k: v[k] for k in ("version", "effective_from", "published_by", "published_at")}
                                      for v in versions_of(cur, contract_id)],
        "amendments": ams, "checklist": validation.checklist(row, today, ams),
        "recalc_batches": [jsonable(r) for r in cur.fetchall()],
    }
