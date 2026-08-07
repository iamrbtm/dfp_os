from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    HIDDEN = "hidden"
    RETIRED = "retired"
    NEEDS_REVIEW = "needs_review"


class ProductType(StrEnum):
    FINISHED_GOOD = "finished_good"
    CUSTOMIZABLE_PRODUCT = "customizable_product"
    MADE_TO_ORDER_PRODUCT = "made_to_order_product"
    POS_QUICK_ITEM = "pos_quick_item"
    B2B_PRODUCT = "b2b_product"
    INTERNAL_ONLY = "internal_only"


class LicenseStatus(StrEnum):
    UNKNOWN = "unknown"
    PERSONAL_ONLY = "personal_only"
    COMMERCIAL_ALLOWED = "commercial_allowed"
    COMMERCIAL_SUBSCRIPTION = "commercial_subscription"
    CUSTOMER_OWNED = "customer_owned"
    NEEDS_REVIEW = "needs_review"
    RESTRICTED = "restricted"
    RETIRED = "retired"


product_collections = Table(
    "product_collections",
    db.metadata,
    db.Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    db.Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_product_collections_product_id", "product_id"),
    Index("ix_product_collections_collection_id", "collection_id"),
)


class ModelSourceType(StrEnum):
    SELF_DESIGNED = "self_designed"
    PURCHASED_STL = "purchased_stl"
    SUBSCRIPTION_LIBRARY = "subscription_library"
    FREE_MODEL = "free_model"
    CUSTOMER_PROVIDED = "customer_provided"
    COMMISSIONED_DESIGN = "commissioned_design"
    UNKNOWN = "unknown"


class AssetKind(StrEnum):
    SOURCE_MODEL = "source_model"
    GCODE = "gcode"
    GLB_PREVIEW = "glb_preview"
    IMAGE = "image"
    METADATA = "metadata"
    REFERENCE = "reference"


class AnalysisRunStatus(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    VALIDATING = "validating"
    SLICING = "slicing"
    STORING_GCODE = "storing_gcode"
    COSTING = "costing"
    CONVERTING = "converting"
    COMPLETE = "complete"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class ProductModelAsset(PrimaryKeyMixin, TimestampMixin, db.Model):
    """One file uploaded or generated for a product (source STL, G-code, GLB preview, ...).

    The run references its produced assets (gcode/preview/metadata) via FKs on
    ProductAnalysisRun, so this table only needs to point back to its product.
    """

    __tablename__ = "product_model_assets"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    safe_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_kind: Mapped[AssetKind] = mapped_column(
        Enum(AssetKind, native_enum=False, length=30), nullable=False, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    product = relationship("Product", back_populates="model_assets")


class ProductAnalysisRun(PrimaryKeyMixin, TimestampMixin, db.Model):
    """One attempt at analyzing a product's model. Race-proof replacement for
    writing analysis state directly on the Product row (Issue 6). A task only
    publishes its results to the Product summary fields if it is still the
    current run for that product.
    """

    __tablename__ = "product_analysis_runs"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    source_asset_id: Mapped[int] = mapped_column(
        ForeignKey("product_model_assets.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[AnalysisRunStatus] = mapped_column(
        Enum(AnalysisRunStatus, native_enum=False, length=30),
        default=AnalysisRunStatus.QUEUED,
        nullable=False,
        index=True,
    )
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedded_settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geometry_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    slicer_stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parsed_volume_mm3: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    parsed_surface_area_mm2: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    parsed_triangle_count: Mapped[int | None] = mapped_column(nullable=True)
    parsed_filament_grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parsed_print_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parsed_material_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    gcode_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_model_assets.id"), nullable=True
    )
    preview_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_model_assets.id"), nullable=True
    )
    metadata_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_model_assets.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product = relationship("Product", back_populates="analysis_runs")
    source_asset = relationship("ProductModelAsset", foreign_keys=[source_asset_id])
    gcode_asset = relationship("ProductModelAsset", foreign_keys=[gcode_asset_id])
    preview_asset = relationship("ProductModelAsset", foreign_keys=[preview_asset_id])
    metadata_asset = relationship("ProductModelAsset", foreign_keys=[metadata_asset_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])

    __table_args__ = (
        # Partial-style filter aid: find the current run for a product quickly.
        Index("ix_analysis_runs_product_current", "product_id", "is_current", unique=False),
    )


class Category(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_pos_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products = relationship("Product", back_populates="category", order_by="Product.name")


class Collection(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    primary_products = relationship(
        "Product", back_populates="collection", order_by=lambda: Product.name
    )
    products = relationship(
        "Product",
        secondary=product_collections,
        back_populates="collections",
        order_by=lambda: Product.name,
    )


class Product(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    sku_base: Mapped[str | None] = mapped_column(String(80), unique=True, index=True, nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True, index=True
    )
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, native_enum=False, length=40),
        default=ProductType.FINISHED_GOOD,
        nullable=False,
    )
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, native_enum=False, length=40),
        default=ProductStatus.DRAFT,
        nullable=False,
        index=True,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pos_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    estimated_material_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )
    estimated_labor_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_print_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_profit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    # Issue 14 / Issue 38 — per-product cost-engine overrides. All default to
    # None so the cost engine falls back to the global settings when unset.
    packaging_cost_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    target_margin_percent_override: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    market_allocation_override: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    payment_fee_rate_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    material_spool_override: Mapped[int | None] = mapped_column(
        ForeignKey("filament_spools.id"), nullable=True
    )
    default_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pos_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, values_callable=lambda e: [m.value for m in e], length=40),
        default=LicenseStatus.UNKNOWN,
        nullable=False,
    )
    design_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commercial_license_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_source_type: Mapped[ModelSourceType] = mapped_column(
        Enum(ModelSourceType, values_callable=lambda e: [m.value for m in e], length=40),
        default=ModelSourceType.UNKNOWN,
        nullable=False,
    )
    model_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_designer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_license_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_commercial_use_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    model_license_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_proof_of_license_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str | None] = mapped_column(
        String(30), default=None, nullable=True, index=True
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analysis_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsed_volume_mm3: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    parsed_surface_area_mm2: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    parsed_triangle_count: Mapped[int | None] = mapped_column(nullable=True)
    parsed_filament_grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parsed_print_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parsed_material_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    convert_status: Mapped[str | None] = mapped_column(String(30), default=None, nullable=True)
    conversion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_model_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gcode_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_metadata_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_analysis_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_convert_to_glb: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    story_what_it_is: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_who_it_is_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_materials: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_customization_options: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_internal_compliance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    launch_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_reprint: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def inventory_available(self) -> int:
        return sum(r.quantity_on_hand - r.quantity_reserved for r in self.inventory_records)

    @property
    def reorder_target(self) -> int:
        return max((r.reorder_target for r in self.inventory_records), default=0)

    category = relationship("Category", back_populates="products")
    collection = relationship("Collection", back_populates="primary_products")
    collections = relationship(
        "Collection",
        secondary=product_collections,
        back_populates="products",
        order_by=lambda: (Collection.sort_order, Collection.name),
    )
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    inventory_records = relationship("InventoryRecord", back_populates="product")
    cost_snapshots = relationship(
        "CostSnapshot",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="CostSnapshot.created_at.desc()",
    )
    launch_checklist_items = relationship(
        "ProductLaunchChecklistItem",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductLaunchChecklistItem.key",
    )
    photo_shots = relationship(
        "ProductPhotoShot",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductPhotoShot.shot_type",
    )
    dead_stock_recommendations = relationship(
        "DeadStockRecommendation",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="DeadStockRecommendation.created_at.desc()",
    )

    @property
    def collection_ids(self) -> list[int]:
        return [collection.id for collection in self.collections]

    model_assets = relationship(
        "ProductModelAsset",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductModelAsset.created_at.desc()",
    )
    analysis_runs = relationship(
        "ProductAnalysisRun",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductAnalysisRun.created_at.desc()",
    )


class ProductImage(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "product_images"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    product = relationship("Product", back_populates="images")


@event.listens_for(ProductImage, "after_delete")
def _cleanup_product_image_storage(mapper, connection, target: ProductImage) -> None:
    from app.services.storage import delete_storage_reference

    if target.file_path:
        try:
            delete_storage_reference(target.file_path)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to delete image storage: %s", target.file_path
            )


@event.listens_for(Product, "after_delete")
def _cleanup_product_model_storage(mapper, connection, target: Product) -> None:
    from app.services.storage import delete_storage_reference

    for ref in (
        target.model_file_path,
        target.model_proof_of_license_path,
        target.converted_model_path,
        target.gcode_path,
    ):
        if ref:
            try:
                delete_storage_reference(ref)
            except Exception:
                import logging

                logging.getLogger(__name__).warning("Failed to delete storage reference: %s", ref)
