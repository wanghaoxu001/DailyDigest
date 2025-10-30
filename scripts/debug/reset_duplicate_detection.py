#!/usr/bin/env python

"""Utility to reset duplicate detection state after interrupted runs."""

import argparse
from typing import List

from app.db.session import SessionLocal
from app.models.digest import Digest
from app.models.duplicate_detection import DuplicateDetectionResult


def reset_states(target_statuses: List[str], dry_run: bool = False) -> None:
    session = SessionLocal()
    try:
        query = session.query(Digest)
        if target_statuses:
            query = query.filter(Digest.duplicate_detection_status.in_(target_statuses))

        digests = query.all()
        if not digests:
            print("No digests matched the provided status filter; nothing to reset.")
            return

        print(f"Preparing to reset {len(digests)} digests")
        for digest in digests:
            print(f"- Digest {digest.id}: status={digest.duplicate_detection_status}")

        if dry_run:
            print("Dry-run mode: no changes committed.")
            return

        digest_ids = [d.id for d in digests]

        # Clear duplicate detection results for selected digests
        deleted = session.query(DuplicateDetectionResult).filter(
            DuplicateDetectionResult.digest_id.in_(digest_ids)
        ).delete(synchronize_session=False)
        print(f"Deleted {deleted} duplicate detection result rows")

        # Reset digest status
        updated = 0
        for digest in digests:
            digest.duplicate_detection_status = 'pending'
            digest.duplicate_detection_started_at = None
            updated += 1

        session.commit()
        print(f"Reset {updated} digests to pending state")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset duplicate detection state")
    parser.add_argument(
        "-s",
        "--status",
        action="append",
        dest="statuses",
        help="Target statuses to reset (repeatable). Defaults to ['running', 'pending'].",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Reset all digests regardless of status",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without committing",
    )

    args = parser.parse_args()

    if args.all:
        statuses = []
    else:
        statuses = args.statuses or ['running', 'pending']

    print("Resetting duplicate detection state")
    if statuses:
        print(f"Filtering for statuses: {statuses}")
    else:
        print("Resetting digests regardless of status")

    reset_states(statuses, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
