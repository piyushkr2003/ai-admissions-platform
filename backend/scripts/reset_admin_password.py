"""CLI entry point: reset the password of an existing `college_admin`
account.

One-time recovery tool for when a bootstrap password (e.g. the one
supplied via `ADMIN_BOOTSTRAP_PASSWORD` to `create_first_college.py` /
`create_college_admin.py`) is lost after that environment variable has
already been removed. Reuses the project's existing password hashing
(`app.core.security.hash_password`) and audit-logging
(`app.services.audit.record_audit`) - no new service or architecture.

Usage:
    ADMIN_PASSWORD_RESET=... python scripts/reset_admin_password.py \\
        --email admin@nova-institute-of-technology.example.edu

The new password is never a CLI argument (that would leak into shell
history/process listings) - it is only ever read from the
`ADMIN_PASSWORD_RESET` environment variable, and it is never printed,
logged, or written into the audit-log `meta`.

Identifies the account by `--email` (`User.email` is globally unique -
see app/models/user.py). Refuses to make any write if:
  - `ADMIN_PASSWORD_RESET` is not set.
  - No user with that email exists.
  - The user with that email is not a `college_admin`.
  - The new password fails `hash_password`'s minimum-length check.

Updates only the existing user's `password_hash`. Never creates,
deletes, or otherwise modifies a College or User row.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit import record_audit  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Email of the existing college_admin account to reset.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    normalized_email = args.email.strip().lower()

    new_password = os.environ.get("ADMIN_PASSWORD_RESET")
    if not new_password:
        print("ADMIN_PASSWORD_RESET environment variable is not set.", file=sys.stderr)
        return 1

    try:
        password_hash = hash_password(new_password)
    except ValueError as exc:
        print(f"Invalid password: {exc}", file=sys.stderr)
        return 1

    with session_scope() as db:
        user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if user is None:
            print(f"No user found with email '{normalized_email}'.", file=sys.stderr)
            return 1
        if user.role != "college_admin":
            print(f"User '{normalized_email}' is not a college_admin (role={user.role}).", file=sys.stderr)
            return 1

        user.password_hash = password_hash
        db.flush()
        record_audit(
            db, college_id=user.college_id, user_id=None,
            action="admin_password_reset", entity_type="user", entity_id=user.id,
            meta={"email": normalized_email},
        )
        user_id = user.id

    print(f"Password reset for college_admin '{normalized_email}' (id={user_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
