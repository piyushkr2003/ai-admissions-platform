"""CLI entry point: seed fictional demo data into the configured database.

Usage:
    python scripts/seed_demo.py

Safe to run against an already-seeded database only if the target database
is empty of these two college slugs - it does not perform upsert
deduplication for child records. Intended for local/dev/test bootstrapping,
never for production.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.seed import seed_demo_data  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.college import College  # noqa: E402


def main() -> None:
    with session_scope() as db:
        existing = db.execute(
            select(College.slug).where(
                College.slug.in_(["nova-institute-of-technology", "aurora-college-of-management"])
            )
        ).scalars().all()
        if existing:
            print(f"Demo colleges already present ({', '.join(existing)}); skipping seed.")
            return
        result = seed_demo_data(db)
        print(f"Seeded {result['nova']['college'].name} and {result['aurora']['college'].name}.")


if __name__ == "__main__":
    main()
