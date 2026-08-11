"""identity: widen otp_challenge.purpose and authentication_method.method_type

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Adds two new enum members to existing CHECK-constrained columns: `otp_challenge.purpose` gains
# LINK_PHONE (an authenticated user proving ownership of a phone number to attach it to their
# existing account -- distinct from REGISTRATION/LOGIN/RECOVERY, which are all pre-auth flows
# keyed purely off the phone), and `authentication_method.method_type` gains APPLE (Sign in with
# Apple, mirroring the existing GOOGLE federated-identity method). Both are additive widenings of
# an allowed-values set -- no existing row's value changes, nothing is dropped except the CHECK
# constraint itself, which is immediately recreated wider in the same transaction.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_otp_challenge_purpose", "otp_challenge", schema="identity", type_="check"
    )  # approved-destructive: immediately recreated wider in the same transaction, no data loss
    op.create_check_constraint(
        "ck_otp_challenge_purpose",
        "otp_challenge",
        "purpose IN ('REGISTRATION','LOGIN','RECOVERY','LINK_PHONE')",
        schema="identity",
    )
    op.drop_constraint(
        "ck_authentication_method_method_type",
        "authentication_method",
        schema="identity",
        type_="check",
    )  # approved-destructive: immediately recreated wider in the same transaction, no data loss
    op.create_check_constraint(
        "ck_authentication_method_method_type",
        "authentication_method",
        "method_type IN ('PHONE_OTP', 'EMAIL', 'GOOGLE', 'APPLE')",
        schema="identity",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_constraint(
        "ck_authentication_method_method_type",
        "authentication_method",
        schema="identity",
        type_="check",
    )  # approved-destructive: fresh-install rollback
    op.create_check_constraint(
        "ck_authentication_method_method_type",
        "authentication_method",
        "method_type IN ('PHONE_OTP', 'EMAIL', 'GOOGLE')",
        schema="identity",
    )
    op.drop_constraint(
        "ck_otp_challenge_purpose", "otp_challenge", schema="identity", type_="check"
    )  # approved-destructive: fresh-install rollback
    op.create_check_constraint(
        "ck_otp_challenge_purpose",
        "otp_challenge",
        "purpose IN ('REGISTRATION','LOGIN','RECOVERY')",
        schema="identity",
    )
