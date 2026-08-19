import type { Overview } from "../../api/types";
import { n0, pct } from "../../format";
import { Fig, Note } from "../../ui/Primitives";

/** Every documented trap in the source files, counted against the loaded data
 *  rather than asserted. A number that reads as a bug is usually one of these. */
export function Notes({ overview }: { overview: Overview }) {
  const d = overview.data;
  const hist = overview.year_histogram;
  const newest = hist.length ? hist[hist.length - 1]! : null;
  const duplicates = d.intro_stats?.duplicate_names ?? null;

  return (
    <div className="notes-grid">
      <Note title="Current intake year is chosen, not assumed">
        {newest && newest.y > overview.current_year ? (
          <>
            The newest intake year in this file is <Fig>{newest.y}</Fig>, holding just{" "}
            <Fig>{n0(newest.n)}</Fig> applications — a phantom created by Nov/Dec rolling forward.
            Current year is taken as the newest year holding at least 10% of the peak year, giving{" "}
            <Fig>CUR = {overview.current_year}</Fig>. Taking max(year) instead would zero every tile.
          </>
        ) : (
          <>
            The newest intake year, <Fig>{newest?.y}</Fig>, holds <Fig>{n0(newest?.n ?? 0)}</Fig>{" "}
            applications and clears the 10%-of-peak floor on its own, so{" "}
            <Fig>CUR = {overview.current_year}</Fig>. The floor exists because Nov/Dec roll forward and
            can otherwise invent a barely-started future intake.
          </>
        )}
      </Note>

      <Note title="Became Customer Date is mostly blank">
        <Fig>{n0(d.blank_became)}</Fig> of <Fig>{n0(d.master_rows)}</Fig> partners (
        {pct(d.blank_became, d.master_rows, 0)}) have no Became Customer Date.{" "}
        <Fig>{n0(d.used_fallback)}</Fig> fell back to Created At; the rest have no cohort year at all.
        Cohort tiles are built partly on that fallback.
      </Note>

      <Note title="Contract status is not a reliable filter">
        <Fig>{n0(d.no_contract)}</Fig> partners ({pct(d.no_contract, d.master_rows, 0)}) have no
        contract status recorded. The active/expired split on each tile covers only those that do.
      </Note>

      <Note title="Revenue invisible to the CRM">
        <Fig>{n0(overview.not_in_crm.n)}</Fig> introducer names appear in applications but not in the
        master file, holding <Fig>{n0(overview.not_in_crm.act)}</Fig> active and{" "}
        <Fig>{n0(overview.not_in_crm.clos)}</Fig> closed deposits. They are shown here as{" "}
        <i>Not in CRM</i> rather than dropped.
      </Note>

      <Note title="Unattributed applications">
        <Fig>{n0(d.blank_intro)}</Fig> applications ({pct(d.blank_intro, d.app_rows, 0)}) have no
        introducer name, including <Fig>{n0(d.blank_intro_deposits)}</Fig> paid deposits. They are
        direct or unattributed business and are excluded from every introducer-level figure.
      </Note>

      <Note title="Contradictory closure records">
        <Fig>{n0(d.contradictions)}</Fig> applications are marked Closed Lost = Yes yet carry an
        Enrolled timestamp. They count as closed deposits here. Worth raising with whoever owns CRM
        hygiene.
      </Note>

      <Note title="Deposit count is the revenue proxy">
        Neither export carries commission value, so every “revenue” figure on this page is a deposit
        count. Partners with different commission rates are being compared as if they were identical.
      </Note>

      <Note title="Duplicates and unusable rows">
        {duplicates === null ? (
          <>Duplicate partner names were collapsed to their first row. </>
        ) : (
          <><Fig>{n0(duplicates)}</Fig> duplicate partner names were collapsed to their first row. </>
        )}
        <Fig>{n0(d.no_year)}</Fig> applications have no usable intake year and fall out of every
        year-based figure.
      </Note>
    </div>
  );
}
