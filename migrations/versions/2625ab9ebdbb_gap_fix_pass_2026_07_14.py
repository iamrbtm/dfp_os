"""gap_fix_pass_2026_07_14

Revision ID: 2625ab9ebdbb
Revises: f6a7b8c9d0e1
Create Date: 2026-07-14 17:52:00.454898

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '2625ab9ebdbb'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Drop orphaned tables whose models no longer exist in the codebase
    op.execute("DROP TABLE IF EXISTS content_drafts")
    op.execute("DROP TABLE IF EXISTS sign_assets")
    op.execute("DROP TABLE IF EXISTS print_failure_autopsies")

    # Add business_id column to users table
    op.add_column(
        "users",
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id"),
            nullable=True,
            index=True,
        ),
    )

    # Add FK constraints to notification.user_id
    op.create_foreign_key(
        "notifications_ibfk_user",
        "notifications", "users",
        ["user_id"], ["id"],
    )

    # Add FK constraints to order.market_id and order.pos_session_id
    op.create_foreign_key(
        "orders_ibfk_market",
        "orders", "markets",
        ["market_id"], ["id"],
    )
    op.create_foreign_key(
        "orders_ibfk_pos_session",
        "orders", "pos_sessions",
        ["pos_session_id"], ["id"],
    )

    # Add FK constraint to pos_sessions.market_id
    op.create_foreign_key(
        "pos_sessions_ibfk_market",
        "pos_sessions", "markets",
        ["market_id"], ["id"],
    )

    # Add FK constraints to expenses
    op.create_foreign_key(
        "expenses_ibfk_market",
        "expenses", "markets",
        ["related_market_id"], ["id"],
    )
    op.create_foreign_key(
        "expenses_ibfk_order",
        "expenses", "orders",
        ["related_order_id"], ["id"],
    )
    op.create_foreign_key(
        "expenses_ibfk_receipt",
        "expenses", "receipts",
        ["receipt_id"], ["id"],
    )


def downgrade():
    # Recreate orphaned tables
    op.execute("""
        CREATE TABLE IF NOT EXISTS content_drafts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            title VARCHAR(200) NOT NULL,
            content_type VARCHAR(60) NOT NULL,
            channel VARCHAR(40) NOT NULL,
            caption TEXT,
            media_reference VARCHAR(500),
            product_id INT,
            market_id INT,
            custom_request_id INT,
            planned_publish_date DATETIME,
            status VARCHAR(40) NOT NULL,
            notes TEXT,
            created_by_user_id INT,
            reviewed_by_user_id INT,
            published_at DATETIME,
            INDEX ix_content_drafts_title (title),
            INDEX ix_content_drafts_status (status),
            INDEX ix_content_drafts_product_id (product_id),
            INDEX ix_content_drafts_market_id (market_id),
            INDEX ix_content_drafts_custom_request_id (custom_request_id),
            INDEX ix_content_drafts_channel (channel),
            INDEX ix_content_drafts_planned_publish_date (planned_publish_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS sign_assets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            title VARCHAR(200) NOT NULL,
            subtitle VARCHAR(300),
            price_display VARCHAR(60),
            short_description TEXT,
            care_note TEXT,
            qr_target_url VARCHAR(500),
            generated_html TEXT,
            preview_html TEXT,
            product_id INT,
            collection_id INT,
            market_id INT,
            is_active TINYINT(1) NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL,
            layout VARCHAR(20) NOT NULL DEFAULT 'text',
            ai_image_path VARCHAR(500),
            INDEX ix_sign_assets_title (title),
            INDEX ix_sign_assets_status (status),
            INDEX ix_sign_assets_product_id (product_id),
            INDEX ix_sign_assets_market_id (market_id),
            INDEX ix_sign_assets_layout (layout),
            INDEX ix_sign_assets_collection_id (collection_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS print_failure_autopsies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            print_job_id INT NOT NULL,
            printer_id INT,
            product_id INT,
            filament_spool_id INT,
            user_id INT,
            model_asset_id INT,
            category VARCHAR(60) NOT NULL,
            severity VARCHAR(40) NOT NULL,
            notes TEXT,
            photo_reference VARCHAR(500),
            corrective_action TEXT,
            maintenance_required TINYINT(1) NOT NULL DEFAULT 0,
            resolved TINYINT(1) NOT NULL DEFAULT 0,
            resolution_notes TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            INDEX ix_print_failure_autopsies_print_job_id (print_job_id),
            INDEX ix_print_failure_autopsies_printer_id (printer_id),
            INDEX ix_print_failure_autopsies_product_id (product_id),
            INDEX ix_print_failure_autopsies_filament_spool_id (filament_spool_id),
            INDEX ix_print_failure_autopsies_model_asset_id (model_asset_id),
            INDEX ix_print_failure_autopsies_user_id (user_id),
            INDEX ix_print_failure_autopsies_category (category),
            INDEX ix_print_failure_autopsies_severity (severity),
            INDEX ix_print_failure_autopsies_resolved (resolved)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci
    """)

    # Drop FK constraints (added in upgrade)
    op.drop_constraint("expenses_ibfk_receipt", "expenses", type_="foreignkey")
    op.drop_constraint("expenses_ibfk_order", "expenses", type_="foreignkey")
    op.drop_constraint("expenses_ibfk_market", "expenses", type_="foreignkey")

    op.drop_constraint("pos_sessions_ibfk_market", "pos_sessions", type_="foreignkey")

    op.drop_constraint("orders_ibfk_pos_session", "orders", type_="foreignkey")
    op.drop_constraint("orders_ibfk_market", "orders", type_="foreignkey")

    op.drop_constraint("notifications_ibfk_user", "notifications", type_="foreignkey")

    # Drop business_id column from users
    op.drop_column("users", "business_id")
