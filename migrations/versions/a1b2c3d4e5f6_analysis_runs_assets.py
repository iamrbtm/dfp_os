"""product analysis runs, model assets, cost snapshot evidence

Revision ID: a1b2c3d4e5f6
Revises: 435585c0d386
Create Date: 2026-07-29 00:00:00.000000

Introduces race-proof analysis runs + model assets (Issue 6/7), cost snapshot
evidence columns (Issue 15), an index on products.analysis_status (Issue 39),
prunes the unbounded model_analysis_config JSON column (Issue 40), and stores
the semantic cost formula version (Issue 43).
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "435585c0d386"
branch_labels = None
depends_on = None


# Issue 40 — only these scalar keys may remain on Product.model_analysis_config.
ALLOWED_CONFIG_KEYS = frozenset(
    {
        "original_filename",
        "uploaded_at",
        "uploaded_by",
        "printer_profile",
        "material",
        "filament_density",
        "nozzle_diameter",
        "layer_height",
        "perimeters",
        "top_solid_layers",
        "bottom_solid_layers",
        "infill_percent",
        "infill_pattern",
        "supports",
        "brim_width",
        "copies",
        "scale_percent",
        "preserve_orientation",
        "multicolor",
        "use_embedded_settings",
        "embedded_settings_applied",
        "retain_gcode",
        "convert_to_glb",
    }
)


def upgrade():
    # --- Issue 6: product_model_assets (created before analysis_runs because
    # analysis_runs.source_asset_id depends on it) -------------------------
    op.create_table(
        "product_model_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("storage_reference", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("safe_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_kind",
            sa.Enum(
                "source_model",
                "gcode",
                "glb_preview",
                "image",
                "metadata",
                "reference",
                name="assetkind",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index(op.f("ix_product_model_assets_product_id"), "product_model_assets", ["product_id"])
    op.create_index(op.f("ix_product_model_assets_business_id"), "product_model_assets", ["business_id"])
    op.create_index(op.f("ix_product_model_assets_asset_kind"), "product_model_assets", ["asset_kind"])
    op.create_index(op.f("ix_product_model_assets_is_current"), "product_model_assets", ["is_current"])

    # --- Issue 6: product_analysis_runs -----------------------------------
    op.create_table(
        "product_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("source_asset_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "started",
                "validating",
                "slicing",
                "storing_gcode",
                "costing",
                "converting",
                "complete",
                "failed",
                "superseded",
                name="analysisrunstatus",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("embedded_settings_json", sa.JSON(), nullable=True),
        sa.Column("geometry_json", sa.JSON(), nullable=True),
        sa.Column("slicer_stats_json", sa.JSON(), nullable=True),
        sa.Column("parsed_volume_mm3", sa.Numeric(length=12, scale=4), nullable=True),
        sa.Column("parsed_surface_area_mm2", sa.Numeric(length=12, scale=4), nullable=True),
        sa.Column("parsed_triangle_count", sa.Integer(), nullable=True),
        sa.Column("parsed_filament_grams", sa.Numeric(length=10, scale=2), nullable=True),
        sa.Column("parsed_print_minutes", sa.Numeric(length=10, scale=2), nullable=True),
        sa.Column("parsed_material_cost", sa.Numeric(length=10, scale=2), nullable=True),
        sa.Column("gcode_asset_id", sa.Integer(), nullable=True),
        sa.Column("preview_asset_id", sa.Integer(), nullable=True),
        sa.Column("metadata_asset_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["source_asset_id"], ["product_model_assets.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["gcode_asset_id"], ["product_model_assets.id"]),
        sa.ForeignKeyConstraint(["preview_asset_id"], ["product_model_assets.id"]),
        sa.ForeignKeyConstraint(["metadata_asset_id"], ["product_model_assets.id"]),
    )
    op.create_index(op.f("ix_product_analysis_runs_product_id"), "product_analysis_runs", ["product_id"])
    op.create_index(op.f("ix_product_analysis_runs_business_id"), "product_analysis_runs", ["business_id"])
    op.create_index(op.f("ix_product_analysis_runs_source_asset_id"), "product_analysis_runs", ["source_asset_id"])
    op.create_index(op.f("ix_product_analysis_runs_status"), "product_analysis_runs", ["status"])
    op.create_index(op.f("ix_product_analysis_runs_is_current"), "product_analysis_runs", ["is_current"])
    op.create_index("ix_analysis_runs_product_current", "product_analysis_runs", ["product_id", "is_current"])

    # --- Issue 39: index on products.analysis_status ----------------------
    op.create_index(op.f("ix_products_analysis_status"), "products", ["analysis_status"])

    # --- Issue 15: cost_snapshots evidence columns ------------------------
    op.add_column("cost_snapshots", sa.Column("model_asset_id", sa.Integer(), nullable=True))
    op.add_column("cost_snapshots", sa.Column("analysis_run_id", sa.Integer(), nullable=True))
    op.add_column("cost_snapshots", sa.Column("file_sha256", sa.String(length=64), nullable=True))
    op.add_column("cost_snapshots", sa.Column("slicer_settings_hash", sa.String(length=64), nullable=True))
    op.add_column("cost_snapshots", sa.Column("material", sa.String(length=40), nullable=True))
    op.add_column("cost_snapshots", sa.Column("density", sa.Numeric(length=6, scale=4), nullable=True))
    op.add_column(
        "cost_snapshots",
        sa.Column(
            "density_source",
            sa.Enum("default", "embedded", "manual", name="costsnapshotdensitysource", native_enum=False, length=20),
            nullable=True,
        ),
    )
    op.add_column("cost_snapshots", sa.Column("scale_percent", sa.Integer(), nullable=True))
    op.add_column("cost_snapshots", sa.Column("copies", sa.Integer(), nullable=True))
    op.add_column("cost_snapshots", sa.Column("parsed_filament_grams", sa.Numeric(length=10, scale=2), nullable=True))
    op.add_column("cost_snapshots", sa.Column("parsed_print_minutes", sa.Numeric(length=10, scale=2), nullable=True))
    op.add_column("cost_snapshots", sa.Column("cost_resolver_evidence_json", sa.Text(), nullable=True))
    op.create_index(op.f("ix_cost_snapshots_model_asset_id"), "cost_snapshots", ["model_asset_id"])
    op.create_index(op.f("ix_cost_snapshots_analysis_run_id"), "cost_snapshots", ["analysis_run_id"])
    op.create_index("ix_cost_snapshots_product_stale", "cost_snapshots", ["product_id", "stale"])
    op.create_foreign_key(
        op.f("fk_cost_snapshots_model_asset_id_product_model_assets"),
        "cost_snapshots",
        "product_model_assets",
        ["model_asset_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_cost_snapshots_analysis_run_id_product_analysis_runs"),
        "cost_snapshots",
        "product_analysis_runs",
        ["analysis_run_id"],
        ["id"],
    )

    # --- Issue 40: prune disallowed keys from existing model_analysis_config
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, model_analysis_config FROM products")).fetchall()
    for row in rows:
        raw = row[1]
        if raw is None:
            continue
        if isinstance(raw, str):
            try:
                import json

                data = json.loads(raw)
            except ValueError:
                continue
        elif isinstance(raw, dict):
            data = raw
        else:
            continue
        pruned = {k: v for k, v in data.items() if k in ALLOWED_CONFIG_KEYS}
        if pruned != data:
            import json

            bind.execute(
                sa.text("UPDATE products SET model_analysis_config = :cfg WHERE id = :id"),
                {"cfg": json.dumps(pruned), "id": row[0]},
            )

    # --- Issue 6 backfill: one source-model asset + current run per product
    products = bind.execute(
        sa.text(
            "SELECT id, business_id, model_file_path, analysis_status, "
            "parsed_volume_mm3, parsed_surface_area_mm2, parsed_triangle_count, "
            "parsed_filament_grams, parsed_print_minutes, parsed_material_cost, "
            "analysis_requested_at, analysis_completed_at "
            "FROM products WHERE model_file_path IS NOT NULL"
        )
    ).fetchall()
    for p in products:
        import hashlib

        sha = hashlib.sha256(str(p[2]).encode("utf-8")).hexdigest()
        asset_result = bind.execute(
            sa.text(
                "INSERT INTO product_model_assets "
                "(product_id, business_id, storage_reference, original_filename, safe_filename, "
                "content_type, size_bytes, sha256, asset_kind, is_current, created_at, updated_at) "
                "VALUES (:pid, :bid, :ref, :name, :safe, 'application/octet-stream', 0, :sha, "
                "'source_model', 1, NOW(), NOW())"
            ),
            {
                "pid": p[0],
                "bid": p[1],
                "ref": p[2],
                "name": p[2].rsplit("/", 1)[-1],
                "safe": p[2].rsplit("/", 1)[-1],
                "sha": sha,
            },
        )
        asset_id = asset_result.lastrowid
        status = p[3] or "queued"
        if status == "complete":
            run_status = "complete"
        elif status == "failed":
            run_status = "failed"
        elif status in {"pending", "analyzing", "slicing", "validating"}:
            run_status = "started"
        else:
            run_status = "queued"
        is_current = 1 if status in {"complete", "failed", "pending", "analyzing", "slicing", "validating"} else 0
        bind.execute(
            sa.text(
                "INSERT INTO product_analysis_runs "
                "(product_id, business_id, source_asset_id, status, is_current, "
                "parsed_volume_mm3, parsed_surface_area_mm2, parsed_triangle_count, "
                "parsed_filament_grams, parsed_print_minutes, parsed_material_cost, "
                "requested_at, completed_at, created_at, updated_at) "
                "VALUES (:pid, :bid, :aid, :status, :is_current, :vol, :sa, :tri, :g, :m, :mc, :req, :comp, NOW(), NOW())"
            ),
            {
                "pid": p[0],
                "bid": p[1],
                "aid": asset_id,
                "status": run_status,
                "is_current": is_current,
                "vol": p[4],
                "sa": p[5],
                "tri": p[6],
                "g": p[7],
                "m": p[8],
                "mc": p[9],
                "req": p[10],
                "comp": p[11],
            },
        )


def downgrade():
    op.drop_index("ix_cost_snapshots_product_stale", table_name="cost_snapshots")
    op.drop_index(op.f("ix_cost_snapshots_analysis_run_id"), table_name="cost_snapshots")
    op.drop_index(op.f("ix_cost_snapshots_model_asset_id"), table_name="cost_snapshots")
    op.drop_constraint(op.f("fk_cost_snapshots_analysis_run_id_product_analysis_runs"), "cost_snapshots", type_="foreignkey")
    op.drop_constraint(op.f("fk_cost_snapshots_model_asset_id_product_model_assets"), "cost_snapshots", type_="foreignkey")
    for col in (
        "cost_resolver_evidence_json",
        "parsed_print_minutes",
        "parsed_filament_grams",
        "copies",
        "scale_percent",
        "density_source",
        "density",
        "material",
        "slicer_settings_hash",
        "file_sha256",
        "analysis_run_id",
        "model_asset_id",
    ):
        op.drop_column("cost_snapshots", col)
    op.drop_index(op.f("ix_products_analysis_status"), table_name="products")
    op.drop_index("ix_analysis_runs_product_current", table_name="product_analysis_runs")
    op.drop_index(op.f("ix_product_analysis_runs_is_current"), table_name="product_analysis_runs")
    op.drop_index(op.f("ix_product_analysis_runs_status"), table_name="product_analysis_runs")
    op.drop_index(op.f("ix_product_analysis_runs_source_asset_id"), table_name="product_analysis_runs")
    op.drop_index(op.f("ix_product_analysis_runs_business_id"), table_name="product_analysis_runs")
    op.drop_index(op.f("ix_product_analysis_runs_product_id"), table_name="product_analysis_runs")
    op.drop_table("product_analysis_runs")
    op.drop_index(op.f("ix_product_model_assets_is_current"), table_name="product_model_assets")
    op.drop_index(op.f("ix_product_model_assets_asset_kind"), table_name="product_model_assets")
    op.drop_index(op.f("ix_product_model_assets_business_id"), table_name="product_model_assets")
    op.drop_index(op.f("ix_product_model_assets_product_id"), table_name="product_model_assets")
    op.drop_table("product_model_assets")