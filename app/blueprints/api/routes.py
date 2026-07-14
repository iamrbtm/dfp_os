from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from flask import Response, current_app, g, jsonify, request
from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import Schema, fields
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AMSUnit,
    AMSUnitStatus,
    AMSUnitType,
    ApiToken,
    Business,
    Category,
    Collection,
    CustomRequest,
    CustomRequestStatus,
    Customer,
    Expense,
    FeatureFlag,
    ExpenseCategory,
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    InventoryRecord,
    LicenseStatus,
    Market,
    MarketDocument,
    MarketDocumentType,
    MarketHotelBooking,
    MarketHotelBookingStatus,
    MarketPackingList,
    MarketStatus,
    MarketTimelineEvent,
    MarketTimelineEventType,
    MarketWeatherSnapshot,
    ModelSourceType,
    Order,
    OrderFulfillmentMethod,
    OrderItem,
    OrderPaymentStatus,
    OrderStatus,
    OrderSource,
    Payment,
    PaymentMethod,
    PosSale,
    PosSession,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    PrepTaskTemplate,
    Printer,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
    SourceHealthRecord,
    TrendOpportunityScore,
    TrendReport,
)
from app.models.promotion import ContentDraft, ContentStatus, SignAsset, SignStatus
from app.models.receipt import (
    Receipt,
    ReceiptLineItem,
    ReceiptStatus,
)
from app.schemas import (
    AMSUnitSchema,
    ApiTokenSchema,
    BusinessSchema,
    CategorySchema,
    CollectionSchema,
    SettingSchema,
    ContentDraftSchema,
    CustomRequestSchema,
    CustomerSchema,
    ExpenseSchema,
    FeatureFlagSchema,
    FilamentSpoolSchema,
    InventoryLocationSchema,
    InventoryRecordSchema,
    MarketDocumentSchema,
    MarketHotelBookingSchema,
    MarketPackingListSchema,
    MarketSchema,
    MarketTimelineEventSchema,
    MarketWeatherSnapshotSchema,
    OrderItemSchema,
    OrderSchema,
    PaymentSchema,
    PosSaleSchema,
    PosSessionSchema,
    PrepTaskSchema,
    PrepTaskTemplateSchema,
    PrinterSchema,
    PrintJobSchema,
    ProductSchema,
    ResourceListEnvelope,
    SignAssetSchema,
    TrendOpportunityScoreSchema,
    TrendReportSchema,
    TrendSourceHealthRecordSchema,
)
from app.schemas.receipt import ReceiptSchema, ReceiptLineItemSchema
from app.services.admin_mutations import (
    archive_resource as archive_admin_resource,
    create_resource as create_admin_resource,
    update_resource as update_admin_resource,
)
from app.services.crud import (
    apply_search,
    get_by_id,
    paginate_query,
)
from app.extensions import db
from app.services.audit import record_audit_event
from app.services.api_tokens import revoke_api_token
from app.services.inventory import release_inventory, reserve_inventory, transfer_inventory
from app.services.pos import refund_sale
from app.utils import slugify
from app.utils.auth import api_token_required, require_api_scopes

catalog_blp = Blueprint("catalog_api", __name__, url_prefix="/api/v1")


class ListQuerySchema(Schema):
    page = fields.Integer(load_default=1)
    per_page = fields.Integer(load_default=25)
    q = fields.String(load_default="")


class EmptyBodySchema(Schema):
    pass


class InventoryTransferRequestSchema(Schema):
    to_location_id = fields.Integer(required=True)
    quantity = fields.Integer(required=True)
    notes = fields.String(load_default=None, allow_none=True)


class InventoryReservationRequestSchema(Schema):
    quantity = fields.Integer(required=True)
    notes = fields.String(load_default=None, allow_none=True)


class PosRefundRequestSchema(Schema):
    restock_inventory = fields.Boolean(load_default=True)
    notes = fields.String(load_default=None, allow_none=True)


@dataclass(frozen=True)
class ApiResourceConfig:
    endpoint: str
    model: type
    schema: type[Schema]
    search_fields: list[str]
    apply_data: callable
    list_filters: callable | None = None


RESOURCE_SCOPES: dict[str, tuple[str, ...]] = {
    "businesses": ("settings",),
    "feature-flags": ("settings",),
    "categories": ("catalog",),
    "collections": ("catalog",),
    "products": ("catalog",),
    "printers": ("inventory",),
    "ams-units": ("inventory",),
    "filament-spools": ("inventory",),
    "inventory-locations": ("inventory",),
    "inventory-records": ("inventory",),
    "customers": ("orders",),
    "custom-requests": ("orders",),
    "orders": ("orders",),
    "order-items": ("orders",),
    "payments": ("orders",),
    "print-jobs": ("orders",),
    "prep-task-templates": ("markets",),
    "prep-tasks": ("markets",),
    "pos-sessions": ("pos",),
    "pos-sales": ("pos",),
    "markets": ("markets",),
    "market-packing-lists": ("markets",),
    "market-timeline-events": ("markets",),
    "market-weather-snapshots": ("markets",),
    "market-hotel-bookings": ("markets",),
    "market-documents": ("markets",),
    "expenses": ("receipts",),
    "receipts": ("receipts",),
    "receipt-line-items": ("receipts",),
    "trend-reports": ("trend_scout",),
    "trend-opportunity-scores": ("trend_scout",),
    "trend-source-health": ("trend_scout",),
    "report-studio": ("report_studio",),
}


def _list_response(pagination, schema_cls: type[Schema]):
    schema = schema_cls(many=True)
    return {
        "data": schema.dump(pagination.items),
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }


def _scope_guard_for(endpoint: str):
    return require_api_scopes(*RESOURCE_SCOPES.get(endpoint, ()))


def _validation_error(message: str, details: dict | None = None):
    return jsonify(
        {
            "error": {
                "code": "validation_error",
                "message": message,
                "details": details or {},
            }
        }
    ), 400


def _instance_state(instance) -> dict:
    state = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        state[column.name] = value
    return state


def _apply_category(instance: Category, data: dict):
    instance.name = data["name"].strip()
    instance.slug = slugify(data.get("slug", "")) or slugify(data["name"].strip())
    instance.description = data.get("description")
    instance.sort_order = data.get("sort_order", 0) or 0
    instance.is_public = data.get("is_public", True)
    instance.is_pos_visible = data.get("is_pos_visible", True)


def _apply_collection(instance: Collection, data: dict):
    instance.name = data["name"].strip()
    instance.slug = slugify(data.get("slug", "")) or slugify(data["name"].strip())
    instance.description = data.get("description")
    instance.is_public = data.get("is_public", True)
    instance.sort_order = data.get("sort_order", 0) or 0


def _apply_product(instance: Product, data: dict):
    instance.name = data["name"].strip()
    instance.slug = slugify(data.get("slug", "")) or slugify(data["name"].strip())
    instance.sku_base = data.get("sku_base")
    instance.short_description = data.get("short_description")
    instance.description = data.get("description")
    instance.category_id = data["category_id"]
    instance.collection_id = data.get("collection_id")
    instance.product_type = ProductType(data["product_type"])
    instance.status = ProductStatus(data["status"])
    instance.is_public = data.get("is_public", False)
    instance.is_pos_visible = data.get("is_pos_visible", True)
    instance.is_featured = data.get("is_featured", False)
    instance.base_price = data.get("base_price", 0) or 0
    instance.estimated_material_cost = data.get("estimated_material_cost", 0) or 0
    instance.estimated_labor_minutes = data.get("estimated_labor_minutes", 0) or 0
    instance.estimated_print_minutes = data.get("estimated_print_minutes", 0) or 0
    instance.estimated_profit = data.get("estimated_profit", 0) or 0
    instance.default_image_path = data.get("default_image_path")
    instance.tags = data.get("tags")
    instance.care_instructions = data.get("care_instructions")
    instance.safety_notes = data.get("safety_notes")
    instance.license_status = LicenseStatus(data["license_status"])
    instance.design_source = data.get("design_source")
    instance.commercial_license_notes = data.get("commercial_license_notes")
    if data.get("model_source_type"):
        instance.model_source_type = ModelSourceType(data["model_source_type"])
    instance.model_source_url = data.get("model_source_url")
    instance.model_designer_name = data.get("model_designer_name")
    instance.model_license_type = data.get("model_license_type")
    instance.model_commercial_use_allowed = data.get("model_commercial_use_allowed", False)
    instance.model_license_expiration = data.get("model_license_expiration")
    instance.model_file_path = data.get("model_file_path")
    instance.model_notes = data.get("model_notes")


def _apply_printer(instance: Printer, data: dict):
    instance.name = data["name"].strip()
    instance.model = data["model"].strip()
    instance.serial_number = data.get("serial_number")
    instance.status = PrinterStatus(data["status"])
    instance.location = data.get("location")
    instance.has_ams = data.get("has_ams", False)
    instance.default_nozzle_size = data.get("default_nozzle_size")
    instance.notes = data.get("notes")
    instance.purchase_date = data.get("purchase_date")
    instance.maintenance_notes = data.get("maintenance_notes")
    instance.total_print_hours = data.get("total_print_hours", 0) or 0


def _apply_ams_unit(instance: AMSUnit, data: dict):
    instance.name = data["name"].strip()
    instance.type = AMSUnitType(data["type"])
    instance.status = AMSUnitStatus(data["status"])
    instance.assigned_printer_id = data.get("assigned_printer_id")
    instance.slot_count = data.get("slot_count", 4) or 4
    instance.notes = data.get("notes")


def _apply_filament(instance: FilamentSpool, data: dict):
    instance.brand = data["brand"].strip()
    instance.material_type = data["material_type"].strip()
    instance.color_name = data["color_name"].strip()
    instance.color_hex = data.get("color_hex")
    instance.spool_weight_grams = data.get("spool_weight_grams", 0) or 0
    instance.remaining_weight_grams = data.get("remaining_weight_grams", 0) or 0
    instance.cost_per_spool = data.get("cost_per_spool", 0) or 0
    instance.cost_per_gram = data.get("cost_per_gram", 0) or 0
    instance.supplier = data.get("supplier")
    instance.purchase_date = data.get("purchase_date")
    instance.storage_location = data.get("storage_location")
    instance.status = FilamentStatus(data["status"])
    instance.reorder_threshold_grams = data.get("reorder_threshold_grams", 0) or 0
    instance.notes = data.get("notes")


def _apply_location(instance: InventoryLocation, data: dict):
    instance.name = data["name"].strip()
    instance.type = data["type"].strip()
    instance.description = data.get("description")
    instance.active = data.get("active", True)


def _apply_business(instance: Business, data: dict):
    instance.name = data["name"].strip()
    instance.slug = slugify(data.get("slug", "")) or slugify(data["name"].strip())
    instance.legal_name = data.get("legal_name")
    instance.public_name = data.get("public_name")
    instance.contact_email = data.get("contact_email")
    instance.phone = data.get("phone")
    instance.website_url = data.get("website_url")
    instance.address_line1 = data.get("address_line1")
    instance.address_line2 = data.get("address_line2")
    instance.city = data.get("city")
    instance.state = data.get("state")
    instance.postal_code = data.get("postal_code")
    instance.timezone = data.get("timezone", "America/Chicago")
    instance.currency = data.get("currency", "USD")
    instance.is_active = data.get("is_active", True)


def _apply_feature_flag(instance: FeatureFlag, data: dict):
    instance.key = data["key"].strip()
    instance.enabled = data.get("enabled", True)
    instance.description = data.get("description")
    instance.business_id = data.get("business_id")


def _apply_inventory_record(instance: InventoryRecord, data: dict):
    if instance.id is not None and {"quantity_on_hand", "quantity_reserved"}.intersection(data):
        raise ValueError("Inventory quantities must be changed through inventory workflow endpoints.")
    instance.product_id = data["product_id"]
    instance.location_id = data["location_id"]
    if instance.id is None:
        instance.quantity_on_hand = data.get("quantity_on_hand", 0) or 0
        instance.quantity_reserved = data.get("quantity_reserved", 0) or 0
    instance.reorder_threshold = data.get("reorder_threshold", 0) or 0
    instance.reorder_target = data.get("reorder_target", 0) or 0
    instance.last_counted_at = data.get("last_counted_at")


def _apply_customer(instance: Customer, data: dict):
    instance.first_name = data["first_name"].strip()
    instance.last_name = data["last_name"].strip()
    instance.email = data.get("email")
    instance.phone = data.get("phone")
    instance.address_line_1 = data.get("address_line_1")
    instance.address_line_2 = data.get("address_line_2")
    instance.city = data.get("city")
    instance.state = data.get("state")
    instance.zip_code = data.get("zip_code")
    instance.notes = data.get("notes")
    instance.is_active = data.get("is_active", True)


def _apply_custom_request(instance: CustomRequest, data: dict):
    instance.name = data["name"].strip()
    instance.email = data["email"].strip()
    instance.phone = data.get("phone")
    instance.description = data["description"]
    instance.estimated_budget = data.get("estimated_budget")
    instance.deadline = data.get("deadline")
    instance.status = CustomRequestStatus(data["status"])
    instance.admin_notes = data.get("admin_notes")
    instance.internal_notes = data.get("internal_notes")
    instance.customer_id = data.get("customer_id")
    instance.source = data.get("source", "api")


def _apply_order(instance: Order, data: dict):
    instance.customer_id = data.get("customer_id")
    instance.status = OrderStatus(data["status"])
    instance.source = OrderSource(data["source"])
    if data.get("payment_status"):
        instance.payment_status = OrderPaymentStatus(data["payment_status"])
    if data.get("fulfillment_method"):
        instance.fulfillment_method = OrderFulfillmentMethod(data["fulfillment_method"])
    instance.market_id = data.get("market_id")
    instance.notes = data.get("notes")
    instance.internal_notes = data.get("internal_notes")
    instance.customer_name = data.get("customer_name")
    instance.customer_email = data.get("customer_email")
    instance.customer_phone = data.get("customer_phone")
    instance.shipping_name = data.get("shipping_name")
    instance.shipping_address_line_1 = data.get("shipping_address_line_1")
    instance.shipping_address_line_2 = data.get("shipping_address_line_2")
    instance.shipping_city = data.get("shipping_city")
    instance.shipping_state = data.get("shipping_state")
    instance.shipping_postal_code = data.get("shipping_postal_code")
    instance.subtotal = data.get("subtotal", 0) or 0
    instance.shipping_total = data.get("shipping_total", 0) or 0
    instance.tax_total = data.get("tax_total", 0) or 0
    instance.discount_total = data.get("discount_total", 0) or 0
    instance.total = data.get("total", 0) or 0
    instance.paid_amount = data.get("paid_amount", 0) or 0
    instance.payment_provider = data.get("payment_provider")
    instance.external_checkout_id = data.get("external_checkout_id")
    instance.external_checkout_url = data.get("external_checkout_url")
    instance.external_payment_reference = data.get("external_payment_reference")


def _apply_order_item(instance: OrderItem, data: dict):
    instance.order_id = data["order_id"]
    instance.product_id = data.get("product_id")
    instance.quantity = data.get("quantity", 1) or 1
    instance.unit_price = data.get("unit_price", 0) or 0
    instance.line_total = data.get("line_total", 0) or 0
    instance.is_custom_item = data.get("is_custom_item", False)
    instance.custom_description = data.get("custom_description")
    instance.notes = data.get("notes")


def _apply_payment(instance: Payment, data: dict):
    instance.order_id = data["order_id"]
    instance.amount = data.get("amount", 0) or 0
    instance.method = PaymentMethod(data["method"])
    instance.reference = data.get("reference")
    instance.notes = data.get("notes")


def _apply_print_job(instance: PrintJob, data: dict):
    instance.label = data["label"].strip()
    instance.status = PrintJobStatus(data["status"])
    instance.printer_id = data.get("printer_id")
    instance.order_item_id = data.get("order_item_id")
    instance.quantity = data.get("quantity", 1)
    instance.priority = data.get("priority", 0)
    instance.notes = data.get("notes")


def _apply_prep_task_template(instance: PrepTaskTemplate, data: dict):
    instance.title = data["title"].strip()
    instance.category = PrepTaskCategory(data["category"])
    instance.description = data.get("description")
    instance.default_due_days_before = data.get("default_due_days_before", 7)
    instance.default_enabled = data.get("default_enabled", True)


def _apply_prep_task(instance: PrepTask, data: dict):
    instance.market_id = data.get("market_id")
    instance.template_id = data.get("template_id")
    instance.title = data["title"].strip()
    instance.category = PrepTaskCategory(data["category"])
    instance.status = PrepTaskStatus(data["status"])
    instance.assigned_user_id = data.get("assigned_user_id")
    instance.due_at = data.get("due_at")
    instance.source = data.get("source", "api")
    instance.notes = data.get("notes")


def _apply_pos_session(instance: PosSession, data: dict):
    instance.opened_by_user_id = data.get("opened_by_user_id", instance.opened_by_user_id)
    instance.opening_cash = data.get("opening_cash", 0)
    instance.market_id = data.get("market_id")
    instance.inventory_location_id = data.get("inventory_location_id")
    instance.notes = data.get("notes")


def _apply_pos_sale(instance: PosSale, data: dict):
    if instance.id is not None and "status" in data:
        raise ValueError("POS sale status must be changed through POS workflow endpoints.")
    instance.payment_method = data["payment_method"]
    instance.total = data.get("total", 0)
    instance.amount_received = data.get("amount_received", 0)
    instance.notes = data.get("notes")


def _apply_market(instance: Market, data: dict):
    instance.name = data["name"].strip()
    instance.location_name = data.get("location_name")
    instance.address = data.get("address")
    instance.city = data.get("city")
    instance.state = data.get("state")
    instance.zip_code = data.get("zip_code")
    instance.event_date = data.get("event_date")
    instance.start_time = data.get("start_time")
    instance.end_time = data.get("end_time")
    instance.latitude = data.get("latitude")
    instance.longitude = data.get("longitude")
    instance.application_submitted_at = data.get("application_submitted_at")
    instance.application_approved_at = data.get("application_approved_at")
    instance.fee_paid_at = data.get("fee_paid_at")
    instance.booth_location = data.get("booth_location")
    instance.booth_size = data.get("booth_size")
    instance.power_available = data.get("power_available", False) or False
    instance.wifi_available = data.get("wifi_available", False) or False
    instance.food_available = data.get("food_available", False) or False
    instance.load_in_at = data.get("load_in_at")
    instance.load_out_at = data.get("load_out_at")
    instance.load_in_notes = data.get("load_in_notes")
    instance.load_out_notes = data.get("load_out_notes")
    instance.booth_fee = data.get("booth_fee", 0) or 0
    instance.application_fee = data.get("application_fee", 0) or 0
    instance.status = MarketStatus(data["status"])
    instance.expected_traffic = data.get("expected_traffic")
    instance.actual_revenue = data.get("actual_revenue")
    instance.actual_profit = data.get("actual_profit")
    instance.notes = data.get("notes")
    from app.services.markets import geocode_market_address

    geocode_market_address(instance)


def _apply_market_packing_list(instance: MarketPackingList, data: dict):
    instance.market_id = data["market_id"]
    instance.product_id = data["product_id"]
    instance.planned_quantity = data.get("planned_quantity", 0) or 0
    instance.packed_quantity = data.get("packed_quantity", 0) or 0
    instance.sold_quantity = data.get("sold_quantity", 0) or 0
    instance.returned_quantity = data.get("returned_quantity", 0) or 0
    instance.notes = data.get("notes")


def _apply_market_timeline_event(instance: MarketTimelineEvent, data: dict):
    instance.market_id = data["market_id"]
    instance.title = data["title"].strip()
    instance.starts_at = data.get("starts_at")
    instance.ends_at = data.get("ends_at")
    instance.location = data.get("location")
    instance.event_type = MarketTimelineEventType(data["event_type"])
    instance.notes = data.get("notes")
    instance.completed_at = data.get("completed_at")


def _apply_market_weather_snapshot(instance: MarketWeatherSnapshot, data: dict):
    from app.models.base import utc_now

    instance.market_id = data["market_id"]
    instance.provider = data.get("provider") or "weather.gov"
    instance.fetched_at = data.get("fetched_at") or utc_now()
    instance.forecast_for = data.get("forecast_for")
    instance.temperature = data.get("temperature")
    instance.short_forecast = data.get("short_forecast")
    instance.detailed_forecast = data.get("detailed_forecast")
    instance.precipitation_probability = data.get("precipitation_probability")
    instance.wind_speed = data.get("wind_speed")
    instance.wind_direction = data.get("wind_direction")
    instance.alert_summary = data.get("alert_summary")
    instance.raw_payload = data.get("raw_payload")


def _apply_market_hotel_booking(instance: MarketHotelBooking, data: dict):
    instance.market_id = data["market_id"]
    instance.hotel_name = data["hotel_name"].strip()
    instance.address = data.get("address")
    instance.check_in_date = data.get("check_in_date")
    instance.check_out_date = data.get("check_out_date")
    instance.confirmation_number = data.get("confirmation_number")
    instance.cost = data.get("cost")
    instance.status = MarketHotelBookingStatus(data["status"])
    instance.notes = data.get("notes")


def _apply_market_document(instance: MarketDocument, data: dict):
    instance.market_id = data["market_id"]
    if not instance.original_filename:
        instance.original_filename = "api-metadata-only"
    if not instance.stored_filename:
        instance.stored_filename = "api-metadata-only"
    instance.document_type = MarketDocumentType(data["document_type"])
    instance.notes = data.get("notes")


def _apply_receipt(instance: Receipt, data: dict):
    instance.merchant_name = data.get("merchant_name", instance.merchant_name)
    instance.store_name = data.get("store_name", instance.store_name)
    instance.receipt_number = data.get("receipt_number", instance.receipt_number)
    instance.date_time = data.get("date_time", instance.date_time)
    instance.subtotal = data.get("subtotal", instance.subtotal)
    instance.tax_total = data.get("tax_total", instance.tax_total)
    instance.grand_total = data.get("grand_total", instance.grand_total)
    instance.payment_method = data.get("payment_method", instance.payment_method)
    instance.currency = data.get("currency", instance.currency)
    instance.notes = data.get("notes", instance.notes)
    if instance.id is not None and "status" in data:
        raise ValueError("Receipt status must be changed through receipt workflow endpoints.")
    if instance.id is None and "status" in data:
        instance.status = ReceiptStatus(data["status"])


def _apply_receipt_line_item(instance: ReceiptLineItem, data: dict):
    instance.description = data.get("description", instance.description)
    instance.sku = data.get("sku", instance.sku)
    instance.quantity = data.get("quantity", instance.quantity)
    instance.unit_price = data.get("unit_price", instance.unit_price)
    instance.line_total = data.get("line_total", instance.line_total)
    instance.line_tax = data.get("line_tax", instance.line_tax)
    instance.needs_review = data.get("needs_review", instance.needs_review)


def _apply_expense(instance: Expense, data: dict):
    instance.date = data["date"]
    instance.vendor = data["vendor"].strip()
    instance.category = ExpenseCategory(data["category"])
    instance.description = data.get("description")
    instance.amount = data.get("amount", 0) or 0
    instance.payment_method = data.get("payment_method")
    instance.related_market_id = data.get("related_market_id")
    instance.related_order_id = data.get("related_order_id")
    instance.receipt_file_path = data.get("receipt_file_path")
    instance.tax_deductible = data.get("tax_deductible", False)
    instance.notes = data.get("notes")


def _apply_trend_report(instance: TrendReport, data: dict):
    instance.summary = data.get("summary")
    instance.growing_categories = data.get("growing_categories")
    instance.declining_trends = data.get("declining_trends")
    instance.pipeline_meta = data.get("pipeline_meta")
    if not instance.report_date:
        instance.report_date = datetime.now(timezone.utc)


def _apply_trend_opportunity_score(instance: TrendOpportunityScore, data: dict):
    instance.candidate_type = data.get("candidate_type", "potential")
    instance.product_id = data.get("product_id")
    instance.keyword = data.get("keyword", "")
    instance.title = data.get("title")
    instance.opportunity_score = data.get("opportunity_score", 0)
    instance.purchase_intent = data.get("purchase_intent", 0)
    instance.trend_velocity = data.get("trend_velocity", 0)
    instance.price_resilience = data.get("price_resilience", 0)
    instance.low_saturation = data.get("low_saturation", 0)
    instance.local_fit = data.get("local_fit", 0)
    instance.production_fit = data.get("production_fit", 0)
    instance.license_risk = data.get("license_risk", 0)
    instance.action = data.get("action", "monitor")
    instance.inventory_available = data.get("inventory_available", 0)
    instance.base_price = data.get("base_price", 0) or 0
    instance.license_status = data.get("license_status")
    instance.rank = data.get("rank")
    instance.sources = data.get("sources")
    instance.score_breakdown = data.get("score_breakdown")
    instance.source_health = data.get("source_health")
    instance.match_confidence = data.get("match_confidence")


def _apply_trend_source_health(instance: SourceHealthRecord, data: dict):
    instance.source = data.get("source", "")
    instance.status = data.get("status", "success")
    instance.keyword = data.get("keyword")
    instance.item_count = data.get("item_count", 0)
    instance.error_message = data.get("error_message")
    instance.metadata_json = data.get("metadata_json")


API_RESOURCES = {
    "businesses": ApiResourceConfig(
        "businesses", Business, BusinessSchema, ["name", "slug", "public_name"], _apply_business
    ),
    "feature-flags": ApiResourceConfig(
        "feature-flags", FeatureFlag, FeatureFlagSchema, ["key", "description"], _apply_feature_flag
    ),
    "categories": ApiResourceConfig(
        "categories", Category, CategorySchema, ["name", "slug"], _apply_category
    ),
    "collections": ApiResourceConfig(
        "collections", Collection, CollectionSchema, ["name", "slug"], _apply_collection
    ),
    "products": ApiResourceConfig(
        "products",
        Product,
        ProductSchema,
        ["name", "slug", "sku_base"],
        _apply_product,
        list_filters=lambda stmt: stmt.where(Product.deleted_at.is_(None)),
    ),
    "printers": ApiResourceConfig(
        "printers", Printer, PrinterSchema, ["name", "model", "serial_number"], _apply_printer
    ),
    "ams-units": ApiResourceConfig("ams-units", AMSUnit, AMSUnitSchema, ["name"], _apply_ams_unit),
    "filament-spools": ApiResourceConfig(
        "filament-spools",
        FilamentSpool,
        FilamentSpoolSchema,
        ["brand", "color_name"],
        _apply_filament,
    ),
    "inventory-locations": ApiResourceConfig(
        "inventory-locations",
        InventoryLocation,
        InventoryLocationSchema,
        ["name", "type"],
        _apply_location,
    ),
    "inventory-records": ApiResourceConfig(
        "inventory-records", InventoryRecord, InventoryRecordSchema, [], _apply_inventory_record
    ),
    "customers": ApiResourceConfig(
        "customers",
        Customer,
        CustomerSchema,
        ["first_name", "last_name", "email", "phone"],
        _apply_customer,
    ),
    "custom-requests": ApiResourceConfig(
        "custom-requests",
        CustomRequest,
        CustomRequestSchema,
        ["name", "email", "description"],
        _apply_custom_request,
    ),
    "orders": ApiResourceConfig(
        "orders",
        Order,
        OrderSchema,
        ["order_number"],
        _apply_order,
        list_filters=lambda stmt: stmt.where(Order.deleted_at.is_(None)),
    ),
    "order-items": ApiResourceConfig(
        "order-items", OrderItem, OrderItemSchema, [], _apply_order_item
    ),
    "payments": ApiResourceConfig(
        "payments", Payment, PaymentSchema, [], _apply_payment
    ),
    "print-jobs": ApiResourceConfig(
        "print-jobs",
        PrintJob,
        PrintJobSchema,
        ["label", "notes"],
        _apply_print_job,
    ),
    "prep-task-templates": ApiResourceConfig(
        "prep-task-templates",
        PrepTaskTemplate,
        PrepTaskTemplateSchema,
        ["title", "description"],
        _apply_prep_task_template,
    ),
    "prep-tasks": ApiResourceConfig(
        "prep-tasks",
        PrepTask,
        PrepTaskSchema,
        ["title", "notes", "source"],
        _apply_prep_task,
    ),
    "pos-sessions": ApiResourceConfig(
        "pos-sessions",
        PosSession,
        PosSessionSchema,
        ["session_number", "notes"],
        _apply_pos_session,
        list_filters=lambda stmt: stmt.order_by(PosSession.id.desc()),
    ),
    "pos-sales": ApiResourceConfig(
        "pos-sales",
        PosSale,
        PosSaleSchema,
        ["sale_number", "payment_method"],
        _apply_pos_sale,
        list_filters=lambda stmt: stmt.order_by(PosSale.id.desc()),
    ),
    "markets": ApiResourceConfig(
        "markets",
        Market,
        MarketSchema,
        ["name", "location_name", "city"],
        _apply_market,
    ),
    "market-packing-lists": ApiResourceConfig(
        "market-packing-lists",
        MarketPackingList,
        MarketPackingListSchema,
        [],
        _apply_market_packing_list,
    ),
    "market-timeline-events": ApiResourceConfig(
        "market-timeline-events",
        MarketTimelineEvent,
        MarketTimelineEventSchema,
        ["title", "location", "notes"],
        _apply_market_timeline_event,
    ),
    "market-weather-snapshots": ApiResourceConfig(
        "market-weather-snapshots",
        MarketWeatherSnapshot,
        MarketWeatherSnapshotSchema,
        ["short_forecast", "detailed_forecast", "alert_summary"],
        _apply_market_weather_snapshot,
    ),
    "market-hotel-bookings": ApiResourceConfig(
        "market-hotel-bookings",
        MarketHotelBooking,
        MarketHotelBookingSchema,
        ["hotel_name", "address", "confirmation_number"],
        _apply_market_hotel_booking,
    ),
    "market-documents": ApiResourceConfig(
        "market-documents",
        MarketDocument,
        MarketDocumentSchema,
        ["original_filename", "notes"],
        _apply_market_document,
    ),
    "expenses": ApiResourceConfig(
        "expenses",
        Expense,
        ExpenseSchema,
        ["vendor", "description", "category"],
        _apply_expense,
    ),
    "receipts": ApiResourceConfig(
        "receipts",
        Receipt,
        ReceiptSchema,
        ["merchant_name", "store_name", "receipt_number"],
        _apply_receipt,
        list_filters=lambda stmt: stmt.where(Receipt.deleted_at.is_(None)),
    ),
    "receipt-line-items": ApiResourceConfig(
        "receipt-line-items",
        ReceiptLineItem,
        ReceiptLineItemSchema,
        ["description", "sku"],
        _apply_receipt_line_item,
    ),
    "trend-reports": ApiResourceConfig(
        "trend-reports",
        TrendReport,
        TrendReportSchema,
        ["summary"],
        _apply_trend_report,
        list_filters=lambda stmt: stmt.order_by(TrendReport.report_date.desc()),
    ),
    "trend-opportunity-scores": ApiResourceConfig(
        "trend-opportunity-scores",
        TrendOpportunityScore,
        TrendOpportunityScoreSchema,
        ["keyword", "title", "action"],
        _apply_trend_opportunity_score,
        list_filters=lambda stmt: stmt.order_by(TrendOpportunityScore.opportunity_score.desc()),
    ),
    "trend-source-health": ApiResourceConfig(
        "trend-source-health",
        SourceHealthRecord,
        TrendSourceHealthRecordSchema,
        ["source", "keyword"],
        _apply_trend_source_health,
    ),
}


def _register_resource(config: ApiResourceConfig):
    schema_cls = config.schema
    query_schema = ListQuerySchema()
    tag = config.endpoint.replace("-", " ").title()

    @catalog_blp.route(f"/{config.endpoint}")
    class ResourceCollection(MethodView):
        @api_token_required
        @catalog_blp.doc(tags=[tag])
        @catalog_blp.response(200, ResourceListEnvelope)
        def get(self):
            denied = _scope_guard_for(config.endpoint)
            if denied:
                return denied
            args = query_schema.load(request.args)
            statement = select(config.model)
            if config.list_filters:
                statement = config.list_filters(statement)
            statement = apply_search(statement, config.model, args["q"], config.search_fields)
            pagination = paginate_query(
                statement.order_by(config.model.created_at.desc()),
                args["page"],
                args["per_page"],
            )
            return _list_response(pagination, config.schema)

        @api_token_required
        @catalog_blp.doc(tags=[tag])
        @catalog_blp.arguments(schema_cls)
        @catalog_blp.response(201, schema_cls)
        def post(self, body_data):
            denied = _scope_guard_for(config.endpoint)
            if denied:
                return denied
            instance = config.model()
            try:
                config.apply_data(instance, body_data)
                create_admin_resource(
                    instance,
                    actor_id=getattr(getattr(g, "api_token", None), "user_id", None),
                    entity_type=config.endpoint,
                )
            except ValueError as exc:
                db.session.rollback()
                return _validation_error(str(exc))
            except IntegrityError:
                db.session.rollback()
                return jsonify(
                    {
                        "error": {
                            "code": "validation_error",
                            "message": "Validation failed.",
                            "details": {"resource": f"Unable to save {config.endpoint}."},
                        }
                    },
                ), 400
            return instance, 201

    @catalog_blp.route(f"/{config.endpoint}/<int:resource_id>")
    class ResourceItem(MethodView):
        @api_token_required
        @catalog_blp.doc(tags=[tag])
        @catalog_blp.response(200, schema_cls)
        def get(self, resource_id: int):
            denied = _scope_guard_for(config.endpoint)
            if denied:
                return denied
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return jsonify(
                    {
                        "error": {
                            "code": "not_found",
                            "message": "Resource not found.",
                            "details": {},
                        }
                    },
                ), 404
            return instance

        @api_token_required
        @catalog_blp.doc(tags=[tag])
        @catalog_blp.arguments(schema_cls)
        @catalog_blp.response(200, schema_cls)
        def put(self, body_data, resource_id: int):
            denied = _scope_guard_for(config.endpoint)
            if denied:
                return denied
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return jsonify(
                    {
                        "error": {
                            "code": "not_found",
                            "message": "Resource not found.",
                            "details": {},
                        }
                    },
                ), 404
            before_state = _instance_state(instance)
            try:
                config.apply_data(instance, body_data)
                update_admin_resource(
                    instance,
                    before_state=before_state,
                    actor_id=getattr(getattr(g, "api_token", None), "user_id", None),
                    entity_type=config.endpoint,
                )
            except ValueError as exc:
                db.session.rollback()
                return _validation_error(str(exc))
            except IntegrityError:
                db.session.rollback()
                return jsonify(
                    {
                        "error": {
                            "code": "validation_error",
                            "message": "Validation failed.",
                            "details": {"resource": f"Unable to update {config.endpoint}."},
                        }
                    },
                ), 400
            return instance

        @api_token_required
        @catalog_blp.doc(tags=[tag])
        def delete(self, resource_id: int):
            denied = _scope_guard_for(config.endpoint)
            if denied:
                return denied
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return jsonify(
                    {
                        "error": {
                            "code": "not_found",
                            "message": "Resource not found.",
                            "details": {},
                        }
                    },
                ), 404
            archive_admin_resource(
                instance,
                actor_id=getattr(getattr(g, "api_token", None), "user_id", None),
                entity_type=config.endpoint,
            )
            return {"status": "archived"}


for resource_config in API_RESOURCES.values():
    _register_resource(resource_config)


@catalog_blp.route("/themes")
class ThemeCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Themes"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("catalog")
        if denied:
            return denied
        from app.theme_registry import ALL_THEMES
        return [
            {"slug": t.slug, "name": t.name, "mode": t.mode, "description": t.description}
            for t in ALL_THEMES
        ]


@catalog_blp.route("/themes/current")
class ThemeCurrent(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Themes"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("catalog")
        if denied:
            return denied
        from flask_login import current_user
        from app.theme_registry import THEME_MAP, DEFAULT_THEME
        slug = getattr(current_user, "theme_slug", DEFAULT_THEME)
        theme = THEME_MAP.get(slug)
        return {
            "slug": slug,
            "name": theme.name if theme else DEFAULT_THEME,
            "mode": theme.mode if theme else "light",
        }


@catalog_blp.route("/trend-reports/run")
class TrendReportRun(MethodView):
    @api_token_required
    @catalog_blp.arguments(EmptyBodySchema)
    @catalog_blp.doc(tags=["Trend Scout"])
    @catalog_blp.response(200)
    def post(self, body_data):
        denied = require_api_scopes("trend_scout")
        if denied:
            return denied
        from app.services.ai.trend_scout import run_full_pipeline
        from app.extensions import db

        result = run_full_pipeline(
            openai_api_key=current_app.config.get("OPENAI_API_KEY", ""),
            openai_model=current_app.config.get("OPENAI_MODEL_TREND_SCOUT", "gpt-4o-mini"),
        )
        db.session.commit()
        if result.get("success"):
            return {
                "data": {
                    "success": True,
                    "report_id": result.get("report_id"),
                    "total_snapshots": result.get("total_snapshots", 0),
                    "successful_sources": result.get("successful_sources", []),
                    "failed_sources": result.get("failed_sources", []),
                }
            }
        return {"error": {"code": "pipeline_failed", "message": result.get("error", "Pipeline failed"), "details": {}}}, 500


@catalog_blp.route("/trend-scout/opportunities/<int:score_id>/print-now")
class TrendOpportunityPrintNow(MethodView):
    @api_token_required
    @catalog_blp.arguments(EmptyBodySchema)
    @catalog_blp.doc(tags=["Trend Scout"])
    @catalog_blp.response(200)
    def post(self, body_data, score_id: int):
        denied = require_api_scopes("trend_scout")
        if denied:
            return denied
        score = db.session.get(TrendOpportunityScore, score_id)
        if not score:
            return {"error": {"code": "not_found", "message": "Opportunity score not found.", "details": {}}}, 404
        if not score.product_id:
            return {"error": {"code": "no_product", "message": "No product linked to this opportunity.", "details": {}}}, 400
        product = db.session.get(Product, score.product_id)
        if not product:
            return {"error": {"code": "product_not_found", "message": "Linked product not found.", "details": {}}}, 404
        job = PrintJob(
            product_id=product.id,
            label=f"Trend: {score.keyword}",
            notes=f"Created from Trend Scout opportunity #{score.id} ({score.action})",
            status=PrintJobStatus.QUEUED,
        )
        db.session.add(job)
        db.session.commit()
        record_audit_event(
            action="trend_opportunity.print_now",
            entity_type="trend_opportunity_score",
            entity_id=str(score.id),
            metadata={"product_id": product.id, "product_name": product.name, "print_job_id": job.id},
            source_module="api.routes",
        )
        return {"data": {"print_job_id": job.id, "product_id": product.id, "product_name": product.name}, "status": "created"}


@catalog_blp.route("/trend-scout/opportunities/<int:score_id>/create-product")
class TrendOpportunityCreateProduct(MethodView):
    @api_token_required
    @catalog_blp.arguments(EmptyBodySchema)
    @catalog_blp.doc(tags=["Trend Scout"])
    @catalog_blp.response(201)
    def post(self, body_data, score_id: int):
        denied = require_api_scopes("trend_scout")
        if denied:
            return denied
        score = db.session.get(TrendOpportunityScore, score_id)
        if not score:
            return {"error": {"code": "not_found", "message": "Opportunity score not found.", "details": {}}}, 404
        product = Product(
            name=score.title or score.keyword,
            slug=score.keyword.lower().replace(" ", "-")[:120],
            product_type=ProductType.PHYSICAL,
            status=ProductStatus.DRAFT,
            sku_base=score.keyword.lower().replace(" ", "-")[:50],
            is_public=False,
            is_pos_visible=False,
            base_price=score.base_price or 0,
        )
        db.session.add(product)
        db.session.flush()
        record_audit_event(
            action="trend_opportunity.create_product",
            entity_type="trend_opportunity_score",
            entity_id=str(score.id),
            metadata={"product_id": product.id, "product_name": product.name, "keyword": score.keyword},
            source_module="api.routes",
        )
        db.session.commit()
        return {"data": {"product_id": product.id, "product_name": product.name}, "status": "created"}, 201


@catalog_blp.route("/trend-scout/opportunities/<int:score_id>/action")
class TrendOpportunityRecommendationAction(MethodView):
    @api_token_required
    @catalog_blp.arguments(EmptyBodySchema)
    @catalog_blp.doc(tags=["Trend Scout"])
    @catalog_blp.response(200)
    def post(self, body_data, score_id: int):
        denied = require_api_scopes("trend_scout")
        if denied:
            return denied
        score = db.session.get(TrendOpportunityScore, score_id)
        if not score:
            return {"error": {"code": "not_found", "message": "Opportunity score not found.", "details": {}}}, 404

        product_id = score.product_id
        action_taken = {"action": score.action}
        notes = f"Trend Scout {score.action} for opportunity #{score.id}: {score.keyword}"

        if score.action in ("print_now", "keep_selling", "test_product", "improve_or_monitor"):
            if product_id:
                product = db.session.get(Product, product_id)
                if product:
                    job = PrintJob(
                        product_id=product.id,
                        label=f"Trend: {score.keyword}",
                        notes=notes,
                        status=PrintJobStatus.QUEUED,
                    )
                    db.session.add(job)
                    db.session.flush()
                    action_taken["print_job_id"] = job.id
        elif score.action == "clearance_candidate":
            if product_id:
                product = db.session.get(Product, product_id)
                if product:
                    old_notes = product.admin_notes or ""
                    product.admin_notes = f"[CLEARANCE - Trend Scout #{score.id}] {old_notes}".strip()
        elif score.action == "retire_review":
            if product_id:
                product = db.session.get(Product, product_id)
                if product:
                    old_notes = product.admin_notes or ""
                    product.admin_notes = f"[RETIRE REVIEW - Trend Scout #{score.id}] {old_notes}".strip()
        elif score.action == "license_review":
            if product_id:
                product = db.session.get(Product, product_id)
                if product:
                    old_notes = product.admin_notes or ""
                    product.admin_notes = f"[LICENSE REVIEW - Trend Scout #{score.id}] {old_notes}".strip()

        record_audit_event(
            action=f"trend_opportunity.{score.action}",
            entity_type="trend_opportunity_score",
            entity_id=str(score.id),
            metadata={"action": score.action, "product_id": product_id, "keyword": score.keyword},
            source_module="api.routes",
        )
        db.session.commit()
        return {"data": {"score_id": score.id, "action": score.action, "result": action_taken}}


@catalog_blp.route("/exports/markets.csv")
class MarketsExport(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Exports"])
    def get(self):
        denied = require_api_scopes("markets")
        if denied:
            return denied
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "name", "location_name", "address", "city", "state", "zip_code", "event_date", "booth_fee", "application_fee", "status", "actual_revenue", "actual_profit", "notes"])
        markets = Market.query.order_by(Market.event_date.desc()).all()
        for m in markets:
            writer.writerow([
                m.id, m.name, m.location_name or "", m.address or "", m.city or "", m.state or "", m.zip_code or "",
                m.event_date.isoformat() if m.event_date else "", m.booth_fee or 0, m.application_fee or 0,
                m.status.value, m.actual_revenue or 0, m.actual_profit or 0, m.notes or ""
            ])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=markets.csv"},
        )


@catalog_blp.route("/exports/expenses.csv")
class ExpensesExport(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Exports"])
    def get(self):
        denied = require_api_scopes("receipts")
        if denied:
            return denied
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "date", "vendor", "category", "description", "amount", "payment_method", "related_market_id", "tax_deductible"])
        expenses = Expense.query.order_by(Expense.date.desc()).all()
        for e in expenses:
            writer.writerow([
                e.id, e.date.isoformat() if e.date else "", e.vendor, e.category.value,
                e.description or "", e.amount, e.payment_method or "", e.related_market_id or "",
                "yes" if e.tax_deductible else "no"
            ])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=expenses.csv"},
        )


@catalog_blp.route("/exports/market-packing-lists.csv")
class MarketPackingListsExport(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Exports"])
    def get(self):
        denied = require_api_scopes("markets")
        if denied:
            return denied
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "market_id", "product_id", "planned_quantity", "packed_quantity", "sold_quantity", "returned_quantity"])
        items = MarketPackingList.query.order_by(MarketPackingList.market_id).all()
        for i in items:
            writer.writerow([
                i.id, i.market_id, i.product_id,
                i.planned_quantity or 0, i.packed_quantity or 0, i.sold_quantity or 0, i.returned_quantity or 0
            ])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=market-packing-lists.csv"},
        )


@catalog_blp.route("/inventory-records/<int:record_id>/transfer")
class InventoryRecordTransfer(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Inventory"])
    @catalog_blp.arguments(InventoryTransferRequestSchema)
    @catalog_blp.response(200)
    def post(self, body_data, record_id: int):
        denied = require_api_scopes("inventory")
        if denied:
            return denied
        try:
            source, destination = transfer_inventory(
                record_id=record_id,
                to_location_id=body_data["to_location_id"],
                quantity=body_data["quantity"],
                actor_id=g.api_user.id if getattr(g, "api_user", None) else None,
                notes=body_data.get("notes"),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return {"error": {"code": "validation_error", "message": str(exc), "details": {}}}, 400
        return {
            "data": {
                "source_record_id": source.id,
                "destination_record_id": destination.id,
                "source_quantity_on_hand": source.quantity_on_hand,
                "destination_quantity_on_hand": destination.quantity_on_hand,
            }
        }


@catalog_blp.route("/inventory-records/<int:record_id>/reserve")
class InventoryRecordReserve(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Inventory"])
    @catalog_blp.arguments(InventoryReservationRequestSchema)
    @catalog_blp.response(200)
    def post(self, body_data, record_id: int):
        denied = require_api_scopes("inventory")
        if denied:
            return denied
        try:
            record = reserve_inventory(
                record_id=record_id,
                quantity=body_data["quantity"],
                actor_id=g.api_user.id if getattr(g, "api_user", None) else None,
                notes=body_data.get("notes"),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return {"error": {"code": "validation_error", "message": str(exc), "details": {}}}, 400
        return {
            "data": {
                "record_id": record.id,
                "quantity_on_hand": record.quantity_on_hand,
                "quantity_reserved": record.quantity_reserved,
                "quantity_available": record.quantity_available,
            }
        }


@catalog_blp.route("/inventory-records/<int:record_id>/release")
class InventoryRecordRelease(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Inventory"])
    @catalog_blp.arguments(InventoryReservationRequestSchema)
    @catalog_blp.response(200)
    def post(self, body_data, record_id: int):
        denied = require_api_scopes("inventory")
        if denied:
            return denied
        try:
            record = release_inventory(
                record_id=record_id,
                quantity=body_data["quantity"],
                actor_id=g.api_user.id if getattr(g, "api_user", None) else None,
                notes=body_data.get("notes"),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return {"error": {"code": "validation_error", "message": str(exc), "details": {}}}, 400
        return {
            "data": {
                "record_id": record.id,
                "quantity_on_hand": record.quantity_on_hand,
                "quantity_reserved": record.quantity_reserved,
                "quantity_available": record.quantity_available,
            }
        }


@catalog_blp.route("/analytics/summary")
class AnalyticsSummary(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import executive_summary
        s = executive_summary()
        return {
            "today_revenue": float(s["today_revenue"]),
            "month_revenue": float(s["month_revenue"]),
            "month_pos_revenue": float(s["month_pos_revenue"]),
            "month_expenses": float(s["month_expenses"]),
            "estimated_month_profit": float(s["estimated_month_profit"]),
            "open_orders_count": s["open_orders_count"],
            "open_custom_requests": s["open_custom_requests"],
            "print_jobs_queued": s["print_jobs_queued"],
            "low_inventory_count": s["low_inventory_count"],
            "low_filament_count": s["low_filament_count"],
        }


@catalog_blp.route("/analytics/products")
class AnalyticsProducts(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import product_analytics
        products = product_analytics()
        return [{
            "id": p["id"],
            "name": p["name"],
            "sku": p["sku"],
            "units_sold": p["units_sold"],
            "revenue": float(p["revenue"]),
            "avg_price": float(p["avg_price"]),
            "inventory_on_hand": p["inventory_on_hand"],
            "failure_count": p["failure_count"],
        } for p in products]


@catalog_blp.route("/analytics/markets")
class AnalyticsMarkets(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import market_analytics
        markets = market_analytics()
        return [{
            "id": m["id"],
            "name": m["name"],
            "date": str(m["date"]) if m["date"] else None,
            "total_sales": float(m["total_sales"]),
            "total_expenses": float(m["total_expenses"]),
            "booth_cost": float(m["booth_cost"]),
            "profit": float(m["profit"]),
            "units_sold": m["units_sold"],
        } for m in markets]


@catalog_blp.route("/analytics/printing")
class AnalyticsPrinting(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import printing_analytics
        return printing_analytics()


@catalog_blp.route("/analytics/inventory")
class AnalyticsInventory(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import inventory_analytics
        inv = inventory_analytics()
        return {
            "low_stock_count": inv["low_stock_count"],
            "total_inventory_value": float(inv["total_inventory_value"]),
            "filament_low": inv["filament_low"],
            "filament_empty": inv["filament_empty"],
        }


@catalog_blp.route("/analytics/pos")
class AnalyticsPos(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import pos_analytics
        p = pos_analytics()
        return {
            "total_revenue": float(p["total_revenue"]),
            "total_sales": p["total_sales"],
            "avg_ticket": float(p["avg_ticket"]),
            "payment_totals": {k: float(v) for k, v in p["payment_totals"].items()},
            "open_sessions": p["open_sessions"],
        }


@catalog_blp.route("/analytics/expenses")
class AnalyticsExpenses(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import expense_analytics
        e = expense_analytics()
        return {
            "total_expenses": float(e["total_expenses"]),
            "by_category": [{"category": c["category"], "total": float(c["total"]), "count": c["count"]} for c in e["by_category"]],
        }


@catalog_blp.route("/pos-sales/<int:sale_id>/refund")
class PosSaleRefund(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["POS"])
    @catalog_blp.arguments(PosRefundRequestSchema)
    @catalog_blp.response(200)
    def post(self, body_data, sale_id: int):
        denied = require_api_scopes("pos")
        if denied:
            return denied
        try:
            sale = refund_sale(
                sale_id=sale_id,
                actor_id=g.api_user.id if getattr(g, "api_user", None) else None,
                restock=body_data.get("restock_inventory", True),
                notes=body_data.get("notes"),
            )
        except ValueError as exc:
            return {"error": {"code": "validation_error", "message": str(exc), "details": {}}}, 400
        return {
            "data": {
                "sale_id": sale.id,
                "status": sale.status.value,
                "order_id": sale.order_id,
            }
        }


@catalog_blp.route("/analytics/insights")
class AnalyticsInsights(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Analytics"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.analytics import analytics_insights

        return analytics_insights()


@catalog_blp.route("/modules")
class ModuleStatusCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Modules"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        from app.module_registry import module_statuses

        return {"data": module_statuses()}


@catalog_blp.route("/cost-engine/products/<int:product_id>")
class CostEngineProduct(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Cost Engine"])
    @catalog_blp.response(200)
    def get(self, product_id: int):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.cost_engine import build_pricing_scenarios, calculate_product_cost

        product = db.session.get(Product, product_id)
        if product is None:
            return {"error": {"code": "not_found", "message": "Product not found.", "details": {}}}, 404
        breakdown = calculate_product_cost(product=product)
        data = {key: str(value) for key, value in breakdown.as_dict().items()}
        data["pricing_scenarios"] = build_pricing_scenarios(product=product)
        return {"data": data}


@catalog_blp.route("/cost-engine/orders/<int:order_id>")
class CostEngineOrder(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Cost Engine"])
    @catalog_blp.response(200)
    def get(self, order_id: int):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.cost_engine import estimate_order_profit

        try:
            return {"data": {key: str(value) for key, value in estimate_order_profit(order_id).items()}}
        except ValueError:
            return {"error": {"code": "not_found", "message": "Order not found.", "details": {}}}, 404


@catalog_blp.route("/cost-engine/markets/<int:market_id>")
class CostEngineMarket(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Cost Engine"])
    @catalog_blp.response(200)
    def get(self, market_id: int):
        denied = require_api_scopes("analytics")
        if denied:
            return denied
        from app.services.cost_engine import estimate_market_profit

        return {"data": {key: str(value) for key, value in estimate_market_profit(market_id).items()}}


@catalog_blp.route("/prep-tasks/markets/<int:market_id>/generate")
class PrepTaskGenerate(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Prep Tasks"])
    @catalog_blp.arguments(EmptyBodySchema)
    @catalog_blp.response(201)
    def post(self, _body_data, market_id: int):
        denied = require_api_scopes("markets")
        if denied:
            return denied
        from app.services.prep_tasks import generate_market_prep_tasks

        try:
            tasks = generate_market_prep_tasks(market_id, actor_id=g.api_user.id)
        except ValueError:
            return {"error": {"code": "not_found", "message": "Market not found.", "details": {}}}, 404
        return {"data": [{"id": task.id, "title": task.title, "status": task.status.value} for task in tasks]}, 201


@catalog_blp.route("/prep-tasks/markets/<int:market_id>/readiness")
class PrepTaskReadiness(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Prep Tasks"])
    @catalog_blp.response(200)
    def get(self, market_id: int):
        denied = require_api_scopes("markets")
        if denied:
            return denied
        from app.services.prep_tasks import market_readiness_score

        data = market_readiness_score(market_id)
        data["score"] = str(data["score"])
        return {"data": data}


@catalog_blp.route("/api-tokens")
class ApiTokenCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["API Tokens"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        from app.models import ApiToken
        tokens = ApiToken.query.filter_by(user_id=g.api_user.id).order_by(ApiToken.created_at.desc()).all()
        schema = ApiTokenSchema(many=True)
        return {"data": schema.dump(tokens)}

    @api_token_required
    @catalog_blp.doc(tags=["API Tokens"])
    @catalog_blp.response(201)
    def post(self):
        denied = require_api_scopes("admin")
        if denied:
            return denied
        from app.services.api_tokens import create_api_token
        payload = request.get_json(silent=True) or {}
        name = payload.get("name", "").strip()
        if not name:
            return {"error": {"code": "validation_error", "message": "Token name is required.", "details": {}}}, 400
        scopes = payload.get("scopes", "")
        expires_at_str = payload.get("expires_at")

        expires_at = None
        if expires_at_str:
            try:
                from datetime import datetime, timezone
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return {"error": {"code": "validation_error", "message": "Invalid expires_at format (use YYYY-MM-DD).", "details": {}}}, 400

        token, raw_token = create_api_token(
            user=g.api_user,
            name=name,
            scopes=scopes.split(",") if scopes else None,
            expires_at=expires_at,
        )
        schema = ApiTokenSchema()
        result = schema.dump(token)
        result["raw_token"] = raw_token
        return {"data": result}, 201


@catalog_blp.route("/api-tokens/<int:token_id>")
class ApiTokenItem(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["API Tokens"])
    @catalog_blp.response(200)
    def get(self, token_id: int):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        token = db.session.get(ApiToken, token_id)
        if token is None or token.user_id != g.api_user.id:
            return {"error": {"code": "not_found", "message": "API token not found.", "details": {}}}, 404
        return {"data": ApiTokenSchema().dump(token)}

    @api_token_required
    @catalog_blp.doc(tags=["API Tokens"])
    def delete(self, token_id: int):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        token = db.session.get(ApiToken, token_id)
        if token is None or token.user_id != g.api_user.id:
            return {"error": {"code": "not_found", "message": "API token not found.", "details": {}}}, 404
        revoke_api_token(token, actor_id=g.api_user.id)
        return {"status": "revoked"}


@catalog_blp.route("/settings")
class SettingCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Settings"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        from app.services.settings import get_all_settings
        settings = get_all_settings()
        return {"data": SettingSchema(many=True).dump(settings)}


@catalog_blp.route("/settings/<string:key>")
class SettingItem(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Settings"])
    @catalog_blp.response(200)
    def get(self, key: str):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        from app.models import Setting
        from sqlalchemy import select
        setting = db.session.scalar(select(Setting).where(Setting.key == key))
        if setting is None:
            return {"error": {"code": "not_found", "message": "Setting not found.", "details": {}}}, 404
        return {"data": SettingSchema().dump(setting)}

    @api_token_required
    @catalog_blp.doc(tags=["Settings"])
    @catalog_blp.response(200)
    def put(self, key: str):
        denied = require_api_scopes("settings")
        if denied:
            return denied
        from app.services.settings import set_setting
        from app.services.audit import record_audit_event
        from app.models import Setting
        payload = request.get_json(silent=True) or {}
        if "value" not in payload:
            return {"error": {"code": "validation_error", "message": "value is required.", "details": {}}}, 400
        before = db.session.scalar(select(Setting).where(Setting.key == key))
        before_state = {"value": before.value, "type": before.type} if before else None
        setting = set_setting(
            key=key,
            value=payload["value"],
            description=payload.get("description"),
            type=payload.get("type", "string"),
        )
        record_audit_event(
            action="settings.changed",
            entity_type="setting",
            entity_id=key,
            before_state=before_state,
            after_state={"value": setting.value, "type": setting.type},
            source_module=__name__,
        )
        return {"data": SettingSchema().dump(setting)}


# --- Promotion: Content Drafts ---

@catalog_blp.route("/content-drafts")
class ContentDraftCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        from app.services.crud import apply_search, paginate_query
        from sqlalchemy import select
        page = request.args.get("page", 1, type=int)
        q = request.args.get("q", "").strip()
        stmt = select(ContentDraft).order_by(ContentDraft.updated_at.desc())
        if q:
            stmt = apply_search(stmt, ContentDraft, q, ["title", "caption", "notes"])
        pagination = paginate_query(stmt, page, 25)
        return {
            "data": ContentDraftSchema(many=True).dump(pagination.items),
            "pagination": {"page": page, "per_page": 25, "total": pagination.total},
        }

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(201)
    def post(self):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        payload = request.get_json(silent=True) or {}
        errors = ContentDraftSchema().validate(payload)
        if errors:
            return {"error": {"code": "validation_error", "message": str(errors), "details": errors}}, 400
        draft = ContentDraft(
            title=payload.get("title", ""),
            content_type=payload.get("content_type", "social_post"),
            channel=payload.get("channel", "other"),
            caption=payload.get("caption"),
            media_reference=payload.get("media_reference"),
            product_id=payload.get("product_id"),
            market_id=payload.get("market_id"),
            custom_request_id=payload.get("custom_request_id"),
            status=ContentStatus(payload.get("status", "draft")),
        )
        db.session.add(draft)
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="content_draft.created",
            entity_type="content_draft",
            entity_id=draft.id,
            source_module=__name__,
        )
        return {"data": ContentDraftSchema().dump(draft)}, 201


@catalog_blp.route("/content-drafts/<int:draft_id>")
class ContentDraftItem(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def get(self, draft_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        draft = db.session.get(ContentDraft, draft_id)
        if draft is None:
            return {"error": {"code": "not_found", "message": "Content draft not found.", "details": {}}}, 404
        return {"data": ContentDraftSchema().dump(draft)}

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def put(self, draft_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        draft = db.session.get(ContentDraft, draft_id)
        if draft is None:
            return {"error": {"code": "not_found", "message": "Content draft not found.", "details": {}}}, 404
        payload = request.get_json(silent=True) or {}
        errors = ContentDraftSchema().validate(payload)
        if errors:
            return {"error": {"code": "validation_error", "message": str(errors), "details": errors}}, 400
        from app.services.admin_mutations import snapshot_instance
        before_state = snapshot_instance(draft)
        for field in ("title", "content_type", "caption", "media_reference", "notes"):
            if field in payload:
                setattr(draft, field, payload[field])
        if "channel" in payload:
            draft.channel = payload["channel"]
        if "status" in payload:
            draft.status = ContentStatus(payload["status"])
        if "product_id" in payload:
            draft.product_id = payload.get("product_id")
        if "market_id" in payload:
            draft.market_id = payload.get("market_id")
        if "custom_request_id" in payload:
            draft.custom_request_id = payload.get("custom_request_id")
        if "planned_publish_date" in payload:
            draft.planned_publish_date = payload.get("planned_publish_date")
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="content_draft.updated",
            entity_type="content_draft",
            entity_id=draft.id,
            before_state=before_state,
            source_module=__name__,
        )
        return {"data": ContentDraftSchema().dump(draft)}

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def delete(self, draft_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        draft = db.session.get(ContentDraft, draft_id)
        if draft is None:
            return {"error": {"code": "not_found", "message": "Content draft not found.", "details": {}}}, 404
        draft.status = ContentStatus.ARCHIVED
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="content_draft.archived",
            entity_type="content_draft",
            entity_id=draft.id,
            source_module=__name__,
        )
        return {"status": "archived"}


@catalog_blp.route("/content-drafts/generate-ai", methods=["POST"])
@api_token_required
@catalog_blp.doc(tags=["Promotion"])
@catalog_blp.response(201)
def content_draft_generate_ai():
    denied = require_api_scopes("promotion")
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    source_type = payload.get("source_type", "").strip()
    source_id = payload.get("source_id", 0)
    if not source_type or not source_id:
        return {"error": {"code": "validation_error", "message": "source_type and source_id are required.", "details": {}}}, 400
    from app.services.promotion import generate_ai_assisted_draft
    actor_id = getattr(g, "api_user", None) and g.api_user.id
    draft = generate_ai_assisted_draft(source_type, int(source_id), actor_id=actor_id)
    if draft is None:
        return {"error": {"code": "not_found", "message": f"Could not find {source_type} with id {source_id}.", "details": {}}}, 404
    return {"data": ContentDraftSchema().dump(draft)}, 201


# --- Promotion: Sign Assets ---

@catalog_blp.route("/sign-assets")
class SignAssetCollection(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def get(self):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        from app.services.crud import apply_search, paginate_query
        from sqlalchemy import select
        page = request.args.get("page", 1, type=int)
        q = request.args.get("q", "").strip()
        stmt = select(SignAsset).order_by(SignAsset.updated_at.desc())
        if q:
            stmt = apply_search(stmt, SignAsset, q, ["title", "subtitle", "short_description"])
        pagination = paginate_query(stmt, page, 25)
        return {
            "data": SignAssetSchema(many=True).dump(pagination.items),
            "pagination": {"page": page, "per_page": 25, "total": pagination.total},
        }

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(201)
    def post(self):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        payload = request.get_json(silent=True) or {}
        errors = SignAssetSchema().validate(payload)
        if errors:
            return {"error": {"code": "validation_error", "message": str(errors), "details": errors}}, 400
        sign = SignAsset(
            title=payload.get("title", ""),
            subtitle=payload.get("subtitle"),
            price_display=payload.get("price_display"),
            short_description=payload.get("short_description"),
            care_note=payload.get("care_note"),
            qr_target_url=payload.get("qr_target_url"),
            layout=payload.get("layout", "text"),
            product_id=payload.get("product_id"),
            collection_id=payload.get("collection_id"),
            is_active=payload.get("is_active", True),
            status=SignStatus(payload.get("status", "draft")),
        )
        db.session.add(sign)
        db.session.flush()
        from app.services.promotion import save_sign_html
        save_sign_html(sign)
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="sign_asset.created",
            entity_type="sign_asset",
            entity_id=sign.id,
            source_module=__name__,
        )
        return {"data": SignAssetSchema().dump(sign)}, 201


@catalog_blp.route("/sign-assets/<int:sign_id>")
class SignAssetItem(MethodView):
    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def get(self, sign_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        sign = db.session.get(SignAsset, sign_id)
        if sign is None:
            return {"error": {"code": "not_found", "message": "Sign asset not found.", "details": {}}}, 404
        return {"data": SignAssetSchema().dump(sign)}

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def put(self, sign_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        sign = db.session.get(SignAsset, sign_id)
        if sign is None:
            return {"error": {"code": "not_found", "message": "Sign asset not found.", "details": {}}}, 404
        payload = request.get_json(silent=True) or {}
        errors = SignAssetSchema().validate(payload)
        if errors:
            return {"error": {"code": "validation_error", "message": str(errors), "details": errors}}, 400
        from app.services.admin_mutations import snapshot_instance
        before_state = snapshot_instance(sign)
        for field in ("title", "subtitle", "price_display", "short_description", "care_note", "qr_target_url", "layout"):
            if field in payload:
                setattr(sign, field, payload[field])
        if "product_id" in payload:
            sign.product_id = payload.get("product_id")
        if "collection_id" in payload:
            sign.collection_id = payload.get("collection_id")
        if "is_active" in payload:
            sign.is_active = bool(payload["is_active"])
        if "status" in payload:
            sign.status = SignStatus(payload["status"])
        from app.services.promotion import save_sign_html
        save_sign_html(sign)
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="sign_asset.updated",
            entity_type="sign_asset",
            entity_id=sign.id,
            before_state=before_state,
            source_module=__name__,
        )
        return {"data": SignAssetSchema().dump(sign)}

    @api_token_required
    @catalog_blp.doc(tags=["Promotion"])
    @catalog_blp.response(200)
    def delete(self, sign_id: int):
        denied = require_api_scopes("promotion")
        if denied:
            return denied
        sign = db.session.get(SignAsset, sign_id)
        if sign is None:
            return {"error": {"code": "not_found", "message": "Sign asset not found.", "details": {}}}, 404
        sign.status = SignStatus.ARCHIVED
        db.session.commit()
        from app.services.audit import record_audit_event
        record_audit_event(
            action="sign_asset.archived",
            entity_type="sign_asset",
            entity_id=sign.id,
            source_module=__name__,
        )
        return {"status": "archived"}


@catalog_blp.route("/report-studio/reports", methods=["GET"])
@api_token_required
@catalog_blp.doc(tags=["Report Studio"])
@catalog_blp.response(200)
def report_studio_reports():
    from app.services.report_studio import get_report_catalog, get_data_quality_summary

    denied = require_api_scopes("report_studio")
    if denied:
        return denied
    catalog = get_report_catalog()
    data_quality = get_data_quality_summary()
    return {"data": {"catalog": catalog, "data_quality": data_quality}}


@catalog_blp.route("/report-studio/heat-map", methods=["GET"])
@api_token_required
@catalog_blp.doc(tags=["Report Studio"])
@catalog_blp.response(200)
def report_studio_heat_map():
    from app.services.report_studio import get_vendor_market_heat_map

    denied = require_api_scopes("report_studio")
    if denied:
        return denied
    data = get_vendor_market_heat_map(dict(request.args))
    return {"data": data}


@catalog_blp.route("/report-studio/application-tracker", methods=["GET"])
@api_token_required
@catalog_blp.doc(tags=["Report Studio"])
@catalog_blp.response(200)
def report_studio_application_tracker():
    from app.services.report_studio import get_market_application_pipeline_report

    denied = require_api_scopes("report_studio")
    if denied:
        return denied
    data = get_market_application_pipeline_report(dict(request.args))
    return {"data": data}


@catalog_blp.route("/report-studio/heat-map/csv", methods=["GET"])
@api_token_required
@catalog_blp.doc(tags=["Report Studio"])
@catalog_blp.response(200)
def report_studio_heat_map_csv():
    from app.services.report_studio import get_vendor_market_heat_map

    denied = require_api_scopes("report_studio")
    if denied:
        return denied
    data = get_vendor_market_heat_map(dict(request.args))
    import csv, io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "City", "State", "Status", "Date", "Booth Fee", "Revenue", "Profit", "Margin %", "Has Coordinates", "Worth Repeating"])
    for m in data:
        writer.writerow([
            m["name"], m.get("city", ""), m.get("state", ""), m.get("status", ""),
            m.get("event_date", ""), m.get("booth_fee", 0), m.get("revenue", 0),
            m.get("profit", 0), m.get("margin_pct", ""),
            "Yes" if m.get("has_coordinates") else "No",
            "Yes" if m.get("worth_repeating") is True else ("No" if m.get("worth_repeating") is False else ""),
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=market_heat_map.csv"})


@catalog_blp.route("/report-studio/application-tracker/csv", methods=["GET"])
@api_token_required
@catalog_blp.doc(tags=["Report Studio"])
@catalog_blp.response(200)
def report_studio_application_tracker_csv():
    from app.services.report_studio import get_market_application_pipeline_report

    denied = require_api_scopes("report_studio")
    if denied:
        return denied
    data = get_market_application_pipeline_report(dict(request.args))
    import csv, io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Market", "City", "State", "Status", "Deadline", "App Fee", "Booth Fee", "Total Fee", "Has Documents", "Follow-Up Date", "Needs Follow-Up", "Worth Repeating"])
    for m in data.get("pipeline", []):
        writer.writerow([
            m["name"], m.get("city", ""), m.get("state", ""), m.get("status", ""),
            m.get("application_deadline", ""), m.get("application_fee", 0),
            m.get("booth_fee", 0), m.get("total_fee", 0),
            "Yes" if m.get("has_documents") else "No",
            m.get("follow_up_date", ""),
            "Yes" if m.get("needs_follow_up") else "No",
            "Yes" if m.get("worth_repeating") is True else ("No" if m.get("worth_repeating") is False else ""),
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=application_tracker.csv"})


@catalog_blp.route("/sign-assets/<int:sign_id>/generate-ai-image", methods=["POST"])
@api_token_required
@catalog_blp.doc(tags=["Promotion"])
@catalog_blp.response(200)
def sign_asset_generate_ai_image(sign_id: int):
    denied = require_api_scopes("promotion")
    if denied:
        return denied
    sign = db.session.get(SignAsset, sign_id)
    if sign is None:
        return {"error": {"code": "not_found", "message": "Sign asset not found.", "details": {}}}, 404
    from app.services.promotion import generate_ai_sign_image
    result = generate_ai_sign_image(sign)
    return {"data": SignAssetSchema().dump(result)}


def register_api_blueprints(api):
    api.register_blueprint(catalog_blp)
