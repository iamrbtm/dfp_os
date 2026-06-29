"""fix_enum_values_to_lowercase

Revision ID: 43c4bd2dd978
Revises: 787cadb6f437
Create Date: 2026-06-28 10:45:46.091206

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "43c4bd2dd978"
down_revision = "787cadb6f437"
branch_labels = None
depends_on = None


LICENSE_MAP = {
    "COMMERCIAL_ALLOWED": "commercial_allowed",
    "COMMERCIAL_SUBSCRIPTION": "commercial_subscription",
    "CUSTOMER_OWNED": "customer_owned",
    "NEEDS_REVIEW": "needs_review",
    "PERSONAL_ONLY": "personal_only",
    "RESTRICTED": "restricted",
    "RETIRED": "retired",
    "UNKNOWN": "unknown",
}

SOURCE_MAP = {
    "COMMISSIONED": "commissioned",
    "FREE_STL": "free_stl",
    "GENERATED": "generated",
    "PURCHASED_STL": "purchased_stl",
    "SELF_DESIGNED": "self_designed",
    "SUBSCRIPTION_STL": "subscription_stl",
    "THIRD_PARTY_PLATFORM": "third_party_platform",
    "UNKNOWN": "unknown",
}


def upgrade():
    conn = op.get_bind()

    # Fix LicenseStatus rows using BINARY for case-sensitive comparison
    for old, new in LICENSE_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE products SET license_status = :new "
                "WHERE BINARY license_status = :old"
            ),
            {"new": new, "old": old},
        )

    # Fix ModelSourceType rows using BINARY for case-sensitive comparison
    for old, new in SOURCE_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE products SET model_source_type = :new "
                "WHERE BINARY model_source_type = :old"
            ),
            {"new": new, "old": old},
        )


def downgrade():
    pass
