"""CLI entry point: bootstrap the first `college_admin` account for an
existing college in production (or any environment).

This is the only supported way to create a college_admin login outside
the dev/test demo fixtures (`app/db/seed.py`, `app/db/nova_demo.py`,
neither of which this script uses or touches). There is no HTTP endpoint
for this: on a fresh database there is no platform_admin yet either, so
an RBAC-gated route can't bootstrap itself. Authorization instead comes
from execution access - only someone who can run a command against the
target database (see docs/development.md "Production College Admin
Bootstrap" for how to do this against Render's free tier, which has no
Shell/one-off Jobs) can invoke this script.

Usage:
    python scripts/create_college_admin.py \\
        --college-slug nova-institute-of-technology \\
        --email admin@nova-institute-of-technology.example.edu \\
        --full-name "Priya Sharma"

The password is never a CLI argument (that would leak into shell
history/process listings). Supply it via one of, in order of
precedence:
  1. The ADMIN_BOOTSTRAP_PASSWORD environment variable.
  2. An interactive, non-echoing prompt (getpass).

Refuses to run if the college doesn't exist (tenant ownership must be
explicit) or if the college already has a college_admin (this is a
one-time bootstrap, not a general admin-invite tool) or if the email is
already taken.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402

from app.colleges.repository import CollegeRepository  # noqa: E402
from app.colleges.schemas import CollegeAdminBootstrap  # noqa: E402
from app.colleges.service import CollegeService  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.db.session import session_scope  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--college-slug", required=True, help="Slug of an existing college.")
    parser.add_argument("--email", required=True, help="Login email for the new college_admin.")
    parser.add_argument("--full-name", required=True, help="Full name of the new college_admin.")
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
        payload = CollegeAdminBootstrap(email=args.email, full_name=args.full_name, password=password)
    except ValidationError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 1

    try:
        with session_scope() as db:
            college = CollegeRepository(db).get_by_slug(args.college_slug)
            if college is None:
                print(f"No college found with slug '{args.college_slug}'.", file=sys.stderr)
                return 1
            admin = CollegeService(db).create_initial_admin(college, payload, actor_user_id=None)
            college_slug, admin_email, admin_id = college.slug, admin.email, admin.id
    except AppError as exc:
        print(f"Failed: {exc.message}", file=sys.stderr)
        return 1

    print(f"Created college_admin '{admin_email}' (id={admin_id}) for college '{college_slug}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
