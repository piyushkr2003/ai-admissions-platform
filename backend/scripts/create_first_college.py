"""CLI entry point: bootstrap the very first production college tenant
and its first `college_admin`, together, in one transaction.

`scripts/create_college_admin.py` requires an *existing* college - it
can't create the very first tenant on a database that has zero colleges
and zero users. This script closes that remaining gap by combining
`CollegeService.create_college` and `CollegeService.create_initial_admin`
(the same two methods, unmodified) in a single database transaction, so
a failure creating the admin also undoes the college.

Like `create_college_admin.py`, there is no HTTP endpoint for this: an
RBAC-gated route needs a platform_admin to already exist, which is
exactly what a fresh database doesn't have. Authorization instead comes
from execution access - only someone who can run a command against the
target database can invoke this script (see docs/development.md
"Production College Admin Bootstrap" / "First Production Tenant
Bootstrap" for how to do this against Render's free tier).

Usage:
    python scripts/create_first_college.py \\
        --name "Nova Institute of Technology" \\
        --email admissions@nova-institute-of-technology.example.edu \\
        --phone "+91-9800000000" \\
        --admin-email admin@nova-institute-of-technology.example.edu \\
        --admin-full-name "Priya Sharma"

`--slug` is optional and auto-derived from `--name` (same
`normalize_slug()` behavior every other caller of
`CollegeService.create_college` already gets). `timezone`,
`default_language`, `supported_languages`, and `feature_flags` are left
at `CollegeCreate`'s existing defaults - not exposed as flags here, and
settable later via the normal `PATCH /colleges/{id}` onboarding flow.

The admin password is never a CLI argument. Supply it via one of, in
order of precedence:
  1. The ADMIN_BOOTSTRAP_PASSWORD environment variable.
  2. An interactive, non-echoing prompt (getpass).

Creates exactly one College row (status "draft" - this script never
publishes it) and one college_admin User row, plus the two audit-log
entries `CollegeService` already records for those operations. Creates
nothing else: no courses, FAQs, scholarships, counselors, knowledge
sources, leads, or other fictional/demo data - this script never
imports from `app/db/seed.py` or `app/db/nova_demo.py`.

Refuses to run (and leaves no partial state, since both writes share
one transaction) if the college slug is already taken or if the admin
email is already registered.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402

from app.colleges.schemas import CollegeAdminBootstrap, CollegeCreate  # noqa: E402
from app.colleges.service import CollegeService  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.db.session import session_scope  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="College name.")
    parser.add_argument("--slug", default=None, help="College slug (derived from --name if omitted).")
    parser.add_argument("--email", required=True, help="College primary contact email.")
    parser.add_argument("--phone", required=True, help="College primary contact phone.")
    parser.add_argument("--admin-email", required=True, help="Login email for the new college_admin.")
    parser.add_argument("--admin-full-name", required=True, help="Full name of the new college_admin.")
    return parser.parse_args(argv)


def _read_password() -> str:
    env_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if env_password:
        return env_password
    return getpass.getpass("Initial college_admin password: ")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    password = _read_password()

    try:
        college_payload = CollegeCreate(name=args.name, slug=args.slug, email=args.email, phone=args.phone)
        admin_payload = CollegeAdminBootstrap(email=args.admin_email, full_name=args.admin_full_name, password=password)
    except ValidationError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 1

    try:
        with session_scope() as db:
            service = CollegeService(db)
            college = service.create_college(college_payload, actor_user_id=None)
            admin = service.create_initial_admin(college, admin_payload, actor_user_id=None)
            college_id, college_slug, college_status = college.id, college.slug, college.status
            admin_email, admin_id = admin.email, admin.id
    except AppError as exc:
        print(f"Failed: {exc.message}", file=sys.stderr)
        return 1

    print(
        f"Created college '{college_slug}' (id={college_id}, status={college_status}) "
        f"with college_admin '{admin_email}' (id={admin_id})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
