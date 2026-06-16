from __future__ import annotations

from dataclasses import dataclass

from flask import g, jsonify, request
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
    Category,
    Collection,
    CustomRequest,
    CustomRequestStatus,
    Customer,
    Expense,
    ExpenseCategory,
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    InventoryRecord,
    LicenseStatus,
    Market,
    MarketPackingList,
    MarketStatus,
    ModelAsset,
    ModelSourceType,
    Order,
    OrderItem,
    OrderStatus,
    OrderSource,
    Payment,
    PaymentMethod,
    PosSale,
    PosSaleStatus,
    PosSession,
    Printer,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
)
from app.schemas import (
    AMSUnitSchema,
    ApiTokenSchema,
    CategorySchema,
    CollectionSchema,
    CustomRequestSchema,
    CustomerSchema,
    ExpenseSchema,
    FilamentSpoolSchema,
    InventoryLocationSchema,
    InventoryRecordSchema,
    MarketPackingListSchema,
    MarketSchema,
    ModelAssetSchema,
    OrderItemSchema,
    OrderSchema,
    PaymentSchema,
    PosSaleSchema,
    PosSessionSchema,
    PrinterSchema,
    PrintJobSchema,
    ProductSchema,
    ProductVariantSchema,
)
from app.services.crud import (
    apply_search,
    archive_instance,
    get_by_id,
    paginate_query,
    save_instance,
)
from app.extensions import db
from app.utils.auth import api_token_required

catalog_blp = Blueprint("catalog_api", __name__, url_prefix="/api/v1")


class ListQuerySchema(Schema):
    page = fields.Integer(load_default=1)
    per_page = fields.Integer(load_default=25)
    q = fields.String(load_default="")


@dataclass(frozen=True)
class ApiResourceConfig:
    endpoint: str
    model: type
    schema: type[Schema]
    search_fields: list[str]
    apply_data: callable
    list_filters: callable | None = None


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


def _apply_category(instance: Category, data: dict):
    instance.name = data["name"].strip()
    instance.slug = data["slug"].strip()
    instance.description = data.get("description")
    instance.sort_order = data.get("sort_order", 0) or 0
    instance.is_public = data.get("is_public", True)
    instance.is_pos_visible = data.get("is_pos_visible", True)


def _apply_collection(instance: Collection, data: dict):
    instance.name = data["name"].strip()
    instance.slug = data["slug"].strip()
    instance.description = data.get("description")
    instance.is_public = data.get("is_public", True)
    instance.sort_order = data.get("sort_order", 0) or 0


def _apply_product(instance: Product, data: dict):
    instance.name = data["name"].strip()
    instance.slug = data["slug"].strip()
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


def _apply_variant(instance: ProductVariant, data: dict):
    instance.product_id = data["product_id"]
    instance.sku = data["sku"].strip()
    instance.name = data["name"].strip()
    instance.colorway = data.get("colorway")
    instance.size = data.get("size")
    instance.material_type = data.get("material_type")
    instance.price = data.get("price", 0) or 0
    instance.material_cost = data.get("material_cost", 0) or 0
    instance.estimated_print_minutes = data.get("estimated_print_minutes", 0) or 0
    instance.estimated_filament_grams = data.get("estimated_filament_grams", 0) or 0
    instance.active = data.get("active", True)
    instance.pos_button_label = data.get("pos_button_label")
    instance.pos_sort_order = data.get("pos_sort_order", 0) or 0
    instance.barcode_or_qr_code = data.get("barcode_or_qr_code")


def _apply_model_asset(instance: ModelAsset, data: dict):
    instance.title = data["title"].strip()
    instance.source_type = ModelSourceType(data["source_type"])
    instance.source_url = data.get("source_url")
    instance.designer_name = data.get("designer_name")
    instance.license_type = data.get("license_type")
    instance.commercial_use_allowed = data.get("commercial_use_allowed", False)
    instance.license_expiration = data.get("license_expiration")
    instance.proof_of_license_path = data.get("proof_of_license_path")
    instance.file_location = data.get("file_location")
    instance.related_product_id = data.get("related_product_id")
    instance.notes = data.get("notes")
    instance.status = LicenseStatus(data["status"])


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


def _apply_inventory_record(instance: InventoryRecord, data: dict):
    instance.product_id = data["product_id"]
    instance.variant_id = data.get("variant_id")
    instance.location_id = data["location_id"]
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
    instance.market_id = data.get("market_id")
    instance.notes = data.get("notes")
    instance.internal_notes = data.get("internal_notes")
    instance.subtotal = data.get("subtotal", 0) or 0
    instance.tax_total = data.get("tax_total", 0) or 0
    instance.discount_total = data.get("discount_total", 0) or 0
    instance.total = data.get("total", 0) or 0
    instance.paid_amount = data.get("paid_amount", 0) or 0


def _apply_order_item(instance: OrderItem, data: dict):
    instance.order_id = data["order_id"]
    instance.product_id = data.get("product_id")
    instance.variant_id = data.get("variant_id")
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


def _apply_pos_session(instance: PosSession, data: dict):
    instance.opened_by_user_id = data.get("opened_by_user_id", instance.opened_by_user_id)
    instance.opening_cash = data.get("opening_cash", 0)
    instance.market_id = data.get("market_id")
    instance.inventory_location_id = data.get("inventory_location_id")
    instance.notes = data.get("notes")


def _apply_pos_sale(instance: PosSale, data: dict):
    instance.payment_method = data["payment_method"]
    instance.total = data.get("total", 0)
    instance.amount_received = data.get("amount_received", 0)
    instance.notes = data.get("notes")

    if "status" in data:
        instance.status = PosSaleStatus(data["status"])


def _apply_market(instance: Market, data: dict):
    instance.name = data["name"].strip()
    instance.location_name = data.get("location_name")
    instance.address = data.get("address")
    instance.city = data.get("city")
    instance.state = data.get("state")
    instance.event_date = data.get("event_date")
    instance.start_time = data.get("start_time")
    instance.end_time = data.get("end_time")
    instance.booth_fee = data.get("booth_fee", 0) or 0
    instance.application_fee = data.get("application_fee", 0) or 0
    instance.status = MarketStatus(data["status"])
    instance.expected_traffic = data.get("expected_traffic")
    instance.actual_revenue = data.get("actual_revenue")
    instance.actual_profit = data.get("actual_profit")
    instance.notes = data.get("notes")


def _apply_market_packing_list(instance: MarketPackingList, data: dict):
    instance.market_id = data["market_id"]
    instance.product_id = data["product_id"]
    instance.variant_id = data.get("variant_id")
    instance.planned_quantity = data.get("planned_quantity", 0) or 0
    instance.packed_quantity = data.get("packed_quantity", 0) or 0
    instance.sold_quantity = data.get("sold_quantity", 0) or 0
    instance.returned_quantity = data.get("returned_quantity", 0) or 0
    instance.notes = data.get("notes")


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


API_RESOURCES = {
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
    "variants": ApiResourceConfig(
        "variants", ProductVariant, ProductVariantSchema, ["name", "sku"], _apply_variant
    ),
    "model-assets": ApiResourceConfig(
        "model-assets", ModelAsset, ModelAssetSchema, ["title", "designer_name"], _apply_model_asset
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
    "expenses": ApiResourceConfig(
        "expenses",
        Expense,
        ExpenseSchema,
        ["vendor", "description", "category"],
        _apply_expense,
    ),
}


def _register_resource(config: ApiResourceConfig):
    item_schema = config.schema()
    query_schema = ListQuerySchema()

    @catalog_blp.route(f"/{config.endpoint}")
    class ResourceCollection(MethodView):
        @api_token_required
        def get(self):
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
            return jsonify(_list_response(pagination, config.schema))

        @api_token_required
        def post(self):
            payload = item_schema.load(request.get_json() or {})
            instance = config.model()
            config.apply_data(instance, payload)
            try:
                save_instance(instance)
            except IntegrityError:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "validation_error",
                                "message": "Validation failed.",
                                "details": {"resource": f"Unable to save {config.endpoint}."},
                            }
                        }
                    ),
                    400,
                )
            return jsonify(item_schema.dump(instance)), 201

    @catalog_blp.route(f"/{config.endpoint}/<int:resource_id>")
    class ResourceItem(MethodView):
        @api_token_required
        def get(self, resource_id: int):
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "not_found",
                                "message": "Resource not found.",
                                "details": {},
                            }
                        }
                    ),
                    404,
                )
            return jsonify(item_schema.dump(instance))

        @api_token_required
        def put(self, resource_id: int):
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "not_found",
                                "message": "Resource not found.",
                                "details": {},
                            }
                        }
                    ),
                    404,
                )
            payload = item_schema.load(request.get_json() or {})
            config.apply_data(instance, payload)
            try:
                save_instance(instance)
            except IntegrityError:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "validation_error",
                                "message": "Validation failed.",
                                "details": {"resource": f"Unable to update {config.endpoint}."},
                            }
                        }
                    ),
                    400,
                )
            return jsonify(item_schema.dump(instance))

        @api_token_required
        def delete(self, resource_id: int):
            instance = get_by_id(config.model, resource_id)
            if instance is None:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "not_found",
                                "message": "Resource not found.",
                                "details": {},
                            }
                        }
                    ),
                    404,
                )
            archive_instance(instance)
            return jsonify({"status": "archived"})


for resource_config in API_RESOURCES.values():
    _register_resource(resource_config)


@catalog_blp.route("/themes")
class ThemeCollection(MethodView):
    @api_token_required
    def get(self):
        from app.theme_registry import ALL_THEMES
        return jsonify([
            {"slug": t.slug, "name": t.name, "mode": t.mode, "description": t.description}
            for t in ALL_THEMES
        ])


@catalog_blp.route("/themes/current")
class ThemeCurrent(MethodView):
    @api_token_required
    def get(self):
        from flask_login import current_user
        from app.theme_registry import THEME_MAP, DEFAULT_THEME
        slug = getattr(current_user, "theme_slug", DEFAULT_THEME)
        theme = THEME_MAP.get(slug)
        return jsonify({
            "slug": slug,
            "name": theme.name if theme else DEFAULT_THEME,
            "mode": theme.mode if theme else "light",
        })


@catalog_blp.route("/exports/markets.csv")
class MarketsExport(MethodView):
    @api_token_required
    def get(self):
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "name", "location_name", "address", "city", "state", "event_date", "booth_fee", "application_fee", "status", "actual_revenue", "actual_profit", "notes"])
        markets = Market.query.order_by(Market.event_date.desc()).all()
        for m in markets:
            writer.writerow([
                m.id, m.name, m.location_name or "", m.address or "", m.city or "", m.state or "",
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
    def get(self):
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
    def get(self):
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "market_id", "product_id", "variant_id", "planned_quantity", "packed_quantity", "sold_quantity", "returned_quantity"])
        items = MarketPackingList.query.order_by(MarketPackingList.market_id).all()
        for i in items:
            writer.writerow([
                i.id, i.market_id, i.product_id, i.variant_id or "",
                i.planned_quantity or 0, i.packed_quantity or 0, i.sold_quantity or 0, i.returned_quantity or 0
            ])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=market-packing-lists.csv"},
        )


@catalog_blp.route("/analytics/summary")
class AnalyticsSummary(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import executive_summary
        s = executive_summary()
        return jsonify({
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
        })


@catalog_blp.route("/analytics/products")
class AnalyticsProducts(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import product_analytics
        products = product_analytics()
        return jsonify([{
            "id": p["id"],
            "name": p["name"],
            "sku": p["sku"],
            "units_sold": p["units_sold"],
            "revenue": float(p["revenue"]),
            "avg_price": float(p["avg_price"]),
            "inventory_on_hand": p["inventory_on_hand"],
            "failure_count": p["failure_count"],
        } for p in products])


@catalog_blp.route("/analytics/markets")
class AnalyticsMarkets(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import market_analytics
        markets = market_analytics()
        return jsonify([{
            "id": m["id"],
            "name": m["name"],
            "date": str(m["date"]) if m["date"] else None,
            "total_sales": float(m["total_sales"]),
            "total_expenses": float(m["total_expenses"]),
            "booth_cost": float(m["booth_cost"]),
            "profit": float(m["profit"]),
            "units_sold": m["units_sold"],
        } for m in markets])


@catalog_blp.route("/analytics/printing")
class AnalyticsPrinting(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import printing_analytics
        return jsonify(printing_analytics())


@catalog_blp.route("/analytics/inventory")
class AnalyticsInventory(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import inventory_analytics
        inv = inventory_analytics()
        return jsonify({
            "low_stock_count": inv["low_stock_count"],
            "total_inventory_value": float(inv["total_inventory_value"]),
            "filament_low": inv["filament_low"],
            "filament_empty": inv["filament_empty"],
        })


@catalog_blp.route("/analytics/pos")
class AnalyticsPos(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import pos_analytics
        p = pos_analytics()
        return jsonify({
            "total_revenue": float(p["total_revenue"]),
            "total_sales": p["total_sales"],
            "avg_ticket": float(p["avg_ticket"]),
            "payment_totals": {k: float(v) for k, v in p["payment_totals"].items()},
            "open_sessions": p["open_sessions"],
        })


@catalog_blp.route("/analytics/expenses")
class AnalyticsExpenses(MethodView):
    @api_token_required
    def get(self):
        from app.services.analytics import expense_analytics
        e = expense_analytics()
        return jsonify({
            "total_expenses": float(e["total_expenses"]),
            "by_category": [{"category": c["category"], "total": float(c["total"]), "count": c["count"]} for c in e["by_category"]],
        })


@catalog_blp.route("/api-tokens")
class ApiTokenCollection(MethodView):
    @api_token_required
    def get(self):
        from app.models import ApiToken
        tokens = ApiToken.query.filter_by(user_id=g.api_user.id).order_by(ApiToken.created_at.desc()).all()
        schema = ApiTokenSchema(many=True)
        return jsonify({"data": schema.dump(tokens)})

    @api_token_required
    def post(self):
        from app.services.api_tokens import create_api_token
        payload = request.get_json(silent=True) or {}
        name = payload.get("name", "").strip()
        if not name:
            return jsonify({"error": {"code": "validation_error", "message": "Token name is required.", "details": {}}}), 400
        scopes = payload.get("scopes", "")
        expires_at_str = payload.get("expires_at")

        expires_at = None
        if expires_at_str:
            try:
                from datetime import datetime, timezone
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return jsonify({"error": {"code": "validation_error", "message": "Invalid expires_at format (use YYYY-MM-DD).", "details": {}}}), 400

        token, raw_token = create_api_token(
            user=g.api_user,
            name=name,
            scopes=scopes.split(",") if scopes else None,
            expires_at=expires_at,
        )
        schema = ApiTokenSchema()
        result = schema.dump(token)
        result["raw_token"] = raw_token
        return jsonify({"data": result}), 201


@catalog_blp.route("/api-tokens/<int:token_id>")
class ApiTokenItem(MethodView):
    @api_token_required
    def get(self, token_id: int):
        token = db.session.get(ApiToken, token_id)
        if token is None or token.user_id != g.api_user.id:
            return jsonify({"error": {"code": "not_found", "message": "API token not found.", "details": {}}}), 404
        return jsonify({"data": ApiTokenSchema().dump(token)})

    @api_token_required
    def delete(self, token_id: int):
        token = db.session.get(ApiToken, token_id)
        if token is None or token.user_id != g.api_user.id:
            return jsonify({"error": {"code": "not_found", "message": "API token not found.", "details": {}}}), 404
        from app.models.base import utc_now
        token.revoked_at = utc_now()
        db.session.commit()
        return jsonify({"status": "revoked"})


def register_api_blueprints(api):
    api.register_blueprint(catalog_blp)
