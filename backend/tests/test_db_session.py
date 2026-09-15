from app.db.session import normalize_database_url


def test_normalize_database_url_adds_psycopg_driver_to_a_bare_postgresql_url():
    # What managed Postgres providers (Render, Heroku) hand back.
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_normalize_database_url_leaves_an_explicit_driver_url_unchanged():
    url = "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url(url) == url


def test_normalize_database_url_leaves_non_postgres_urls_unchanged():
    url = "sqlite:///./test.db"
    assert normalize_database_url(url) == url
