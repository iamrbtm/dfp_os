from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, event
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


class ModelSourceType(StrEnum):
    SELF_DESIGNED = "self_designed"
    PURCHASED_STL = "purchased_stl"
    SUBSCRIPTION_LIBRARY = "subscription_library"
    FREE_MODEL = "free_model"
    CUSTOMER_PROVIDED = "customer_provided"
    COMMISSIONED_DESIGN = "commissioned_design"
    UNKNOWN = "unknown"


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

    products = relationship("Product", back_populates="collection", order_by="Product.name")


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
    default_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pos_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, native_enum=False, length=40),
        default=LicenseStatus.UNKNOWN,
        nullable=False,
    )
    design_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commercial_license_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category = relationship("Category", back_populates="products")
    collection = relationship("Collection", back_populates="products")
    variants = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.pos_sort_order",
    )
    model_assets = relationship(
        "ModelAsset", back_populates="product", cascade="all, delete-orphan"
    )
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    inventory_records = relationship("InventoryRecord", back_populates="product")
    cost_snapshots = relationship(
        "CostSnapshot",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="CostSnapshot.created_at.desc()",
    )


class ProductVariant(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "product_variants"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    colorway: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    material_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    material_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    estimated_print_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_filament_grams: Mapped[int] = mapped_column(default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pos_button_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pos_sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    barcode_or_qr_code: Mapped[str | None] = mapped_column(String(255), nullable=True)

    product = relationship("Product", back_populates="variants")
    inventory_records = relationship("InventoryRecord", back_populates="variant")
    model_assets = relationship("ModelAsset", back_populates="variant", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="variant", cascade="all, delete-orphan")
    cost_snapshots = relationship(
        "CostSnapshot",
        back_populates="variant",
        cascade="all, delete-orphan",
        order_by="CostSnapshot.created_at.desc()",
    )


class ModelAsset(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "model_assets"

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[ModelSourceType] = mapped_column(
        Enum(ModelSourceType, native_enum=False, length=40),
        default=ModelSourceType.UNKNOWN,
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    designer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    license_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    commercial_use_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    license_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proof_of_license_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, native_enum=False, length=40),
        default=LicenseStatus.UNKNOWN,
        nullable=False,
    )

    analysis_status: Mapped[str | None] = mapped_column(
        String(30), default=None, nullable=True
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analysis_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsed_volume_mm3: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    parsed_surface_area_mm2: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    parsed_triangle_count: Mapped[int | None] = mapped_column(nullable=True)
    parsed_filament_grams: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    parsed_print_minutes: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    parsed_material_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    convert_status: Mapped[str | None] = mapped_column(
        String(30), default=None, nullable=True
    )
    conversion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_model_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    gcode_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    product = relationship("Product", back_populates="model_assets")
    variant = relationship("ProductVariant", back_populates="model_assets")


class ProductImage(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "product_images"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    product = relationship("Product", back_populates="images")
    variant = relationship("ProductVariant", back_populates="images")


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


@event.listens_for(ModelAsset, "after_delete")
def _cleanup_model_asset_storage(mapper, connection, target: ModelAsset) -> None:
    from app.services.storage import delete_storage_reference
    for ref in (target.file_location, target.converted_model_path, target.gcode_path):
        if ref:
            try:
                delete_storage_reference(ref)
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to delete storage reference: %s", ref
                )
