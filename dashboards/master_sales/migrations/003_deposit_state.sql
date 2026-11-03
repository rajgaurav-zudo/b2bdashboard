-- The deposit as the weekly summary's YTD sheets class it: Active (paid in
-- full, the two deferral columns agree), DAA (paid in full, a deferral awaiting
-- approval) or PD (partially paid). Null for anything else. Closed lost is kept
-- apart in closed_lost. See context.md.

alter table applications add column if not exists deposit_state text;
