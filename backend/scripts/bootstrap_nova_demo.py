"""CLI entry point: bootstrap the Nova Institute of Technology demo tenant
from nova_demo_data/ (fictional data only).

Usage:
    python scripts/bootstrap_nova_demo.py            # create/upsert (idempotent)
    python scripts/bootstrap_nova_demo.py --reset     # re-ingest RAG content, then upsert

Safe to run repeatedly against the same database - see
app/db/nova_demo.py for the idempotency guarantees, and
docs/development.md ("Nova Demo Data") for the full workflow.

Never run --reset against a production database.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.nova_demo import bootstrap_nova_demo, reset_nova_demo_knowledge  # noqa: E402
from app.db.session import session_scope  # noqa: E402


def main() -> None:
    reset = "--reset" in sys.argv[1:]
    with session_scope() as db:
        if reset:
            reset_nova_demo_knowledge(db)
        result = bootstrap_nova_demo(db)

    college = result["college"]
    print(f"Nova demo bootstrap complete for '{college.name}' ({college.slug}).")
    print(f"  courses: {len(result['courses'])}")
    print(f"  scholarships: {len(result['scholarships'])}")
    print(f"  admission_dates: {len(result['admission_dates'])}")
    print(f"  documents: {len(result['documents'])}")
    print(f"  counselors: {len(result['counselors'])}")
    print(f"  faqs: {len(result['faqs'])}")
    print(f"  knowledge_sources: {len(result['knowledge_sources'])}")


if __name__ == "__main__":
    main()
