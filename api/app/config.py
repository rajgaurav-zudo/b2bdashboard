from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://b2b:b2b@db:5432/b2bdash"
    dashboards_dir: str = "/srv/dashboards"
    upload_dir: str = "/srv/data/uploads"
    # counts in core.changelog are always exact; this caps how many row-level
    # diffs get stored per entry so one bad export cannot write millions of rows
    changelog_row_limit: int = 10_000

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
