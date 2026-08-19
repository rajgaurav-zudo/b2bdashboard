from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://b2b:b2b@db:5432/b2bdash"
    dashboards_dir: str = "/srv/dashboards"
    upload_dir: str = "/srv/data/uploads"
    # counts in core.changelog are always exact; this caps how many row-level
    # diffs get stored per entry so one bad export cannot write millions of rows
    changelog_row_limit: int = 10_000

    # --- connection behaviour -------------------------------------------------
    # Off by default because a transaction-mode pooler cannot keep server-side
    # prepared statements alive between transactions. See db.py.
    disable_prepared_statements: bool = True
    db_pool_min: int = 1
    # Supabase counts pooler clients against the project's limit, so an API
    # replica should not hold more than it needs.
    db_pool_max: int = 10

    # --- auth -----------------------------------------------------------------
    # On unless deliberately switched off. The local compose stack sets
    # AUTH_REQUIRED=false so development needs no credentials; anything that does
    # not say so explicitly gets the safe answer.
    auth_required: bool = True
    supabase_url: str = ""
    # Supabase signs user tokens with `aud: authenticated`.
    auth_audience: str = "authenticated"
    # Current projects use ES256 (asymmetric, public JWKS). HS256 is the legacy
    # shared-secret scheme; listed so an older project still verifies.
    auth_algorithms: list[str] = ["ES256", "RS256", "HS256"]
    auth_jwks_ttl: int = 600
    # Who is allowed in. A valid Supabase token only proves the holder signed up,
    # and projects accept public sign-ups by default -- one of these must be set.
    auth_allowed_emails: list[str] = []
    auth_allowed_domains: list[str] = []

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
