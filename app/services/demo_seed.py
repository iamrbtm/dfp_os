from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    AMSUnit,
    AMSUnitStatus,
    AMSUnitType,
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
    OrderSource,
    OrderStatus,
    Payment,
    PaymentMethod,
    PosSale,
    PosSaleItem,
    PosSaleItemType,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
    Printer,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
    Setting,
    User,
    UserRole,
)
from app.models.receipt import (
    AllocationType,
    Receipt,
    ReceiptLineItem,
    ReceiptSourceType,
    ReceiptStatus,
)
from app.services.receipt_allocations import set_line_allocation
from app.services.users import ensure_admin_user, ensure_user
from app.services.business import ensure_default_business
from app.services.prep_tasks import seed_default_prep_templates


def _upsert(model, lookup: dict, values: dict):
    instance = model.query.filter_by(**lookup).first()
    if instance is None:
        instance = model(**lookup)
        db.session.add(instance)

    for key, value in values.items():
        setattr(instance, key, value)
    db.session.flush()
    return instance


def seed_demo_data(admin_email: str, admin_password: str) -> dict[str, int]:
    business = ensure_default_business()
    seed_default_prep_templates()
    ensure_admin_user(admin_email, admin_password, "Admin", "User")
    ensure_user("staff@example.com", "change-me-now", "Market", "Helper", UserRole.STAFF)

    categories = {
        item.slug: item
        for item in [
            _upsert(
                Category,
                {"slug": "dragons"},
                {
                    "name": "Dragons",
                    "description": "Articulated dragons and eggs.",
                    "sort_order": 10,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "fidgets"},
                {
                    "name": "Fidgets",
                    "description": "Pocket-sized focus toys.",
                    "sort_order": 20,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "flexi-animals"},
                {
                    "name": "Flexi Animals",
                    "description": "Friendly flexi critters.",
                    "sort_order": 30,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "personalized-gifts"},
                {
                    "name": "Personalized Gifts",
                    "description": "Custom names and keepsakes.",
                    "sort_order": 40,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "clarksville-collection"},
                {
                    "name": "Clarksville Collection",
                    "description": "Clarksville and Tennessee-themed gifts.",
                    "sort_order": 50,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "military-family-safe-gifts"},
                {
                    "name": "Military-Family-Safe Gifts",
                    "description": "Family-safe, non-branded celebratory items.",
                    "sort_order": 60,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "small-business-products"},
                {
                    "name": "Small Business Products",
                    "description": "Displays, signs, and market helpers.",
                    "sort_order": 70,
                    "is_public": True,
                    "is_pos_visible": True,
                },
            ),
            _upsert(
                Category,
                {"slug": "custom-orders"},
                {
                    "name": "Custom Orders",
                    "description": "Deposit and consultation products.",
                    "sort_order": 80,
                    "is_public": False,
                    "is_pos_visible": True,
                },
            ),
        ]
    }

    collections = {
        item.slug: item
        for item in [
            _upsert(
                Collection,
                {"slug": "the-dragon-den"},
                {
                    "name": "The Dragon Den",
                    "description": "Best-selling dragon lineup.",
                    "is_public": True,
                    "sort_order": 10,
                },
            ),
            _upsert(
                Collection,
                {"slug": "fidget-fish-and-friends"},
                {
                    "name": "Fidget Fish & Friends",
                    "description": "Fidgets and tactile toys.",
                    "is_public": True,
                    "sort_order": 20,
                },
            ),
            _upsert(
                Collection,
                {"slug": "clarksville-collection"},
                {
                    "name": "Clarksville Collection",
                    "description": "Local pride and relocation themes.",
                    "is_public": True,
                    "sort_order": 30,
                },
            ),
            _upsert(
                Collection,
                {"slug": "small-biz-boosters"},
                {
                    "name": "Small Biz Boosters",
                    "description": "Display and signage tools for local shops.",
                    "is_public": True,
                    "sort_order": 40,
                },
            ),
            _upsert(
                Collection,
                {"slug": "market-best-sellers"},
                {
                    "name": "Market Best Sellers",
                    "description": "Impulse-friendly top movers.",
                    "is_public": True,
                    "sort_order": 50,
                },
            ),
        ]
    }

    product_definitions = [
        {
            "slug": "rainbow-dragon",
            "name": "Rainbow Dragon",
            "category": "dragons",
            "collection": "the-dragon-den",
            "sku_base": "DRG-RAINBOW",
            "short_description": "A colorful articulated dragon made for market-table wow factor.",
            "base_price": Decimal("28.00"),
        },
        {
            "slug": "small-articulated-dragon",
            "name": "Small Articulated Dragon",
            "category": "dragons",
            "collection": "market-best-sellers",
            "sku_base": "DRG-SMALL",
            "short_description": "A smaller, fast-moving dragon for impulse buys.",
            "base_price": Decimal("14.00"),
        },
        {
            "slug": "mystery-dragon-egg",
            "name": "Mystery Dragon Egg",
            "category": "dragons",
            "collection": "the-dragon-den",
            "sku_base": "DRG-EGG",
            "short_description": "A dragon egg surprise perfect for gifting.",
            "base_price": Decimal("18.00"),
        },
        {
            "slug": "fidget-slider",
            "name": "Fidget Slider",
            "category": "fidgets",
            "collection": "fidget-fish-and-friends",
            "sku_base": "FGT-SLIDER",
            "short_description": "Pocket-sized fidget with smooth, satisfying movement.",
            "base_price": Decimal("8.00"),
        },
        {
            "slug": "flexi-turtle",
            "name": "Flexi Turtle",
            "category": "flexi-animals",
            "collection": "market-best-sellers",
            "sku_base": "FLX-TURTLE",
            "short_description": "Cute flexi turtle for kids and collector shelves.",
            "base_price": Decimal("10.00"),
        },
        {
            "slug": "flexi-axolotl",
            "name": "Flexi Axolotl",
            "category": "flexi-animals",
            "collection": "market-best-sellers",
            "sku_base": "FLX-AXOLOTL",
            "short_description": "A cheerful axolotl with articulated movement.",
            "base_price": Decimal("11.00"),
        },
        {
            "slug": "clarksville-tn-magnet",
            "name": "Clarksville TN Magnet",
            "category": "clarksville-collection",
            "collection": "clarksville-collection",
            "sku_base": "CLK-MAGNET",
            "short_description": "A lightweight hometown magnet for newcomers and locals alike.",
            "base_price": Decimal("7.00"),
        },
        {
            "slug": "tennessee-ornament",
            "name": "Tennessee Ornament",
            "category": "clarksville-collection",
            "collection": "clarksville-collection",
            "sku_base": "TN-ORNAMENT",
            "short_description": "A warm Tennessee-themed keepsake.",
            "base_price": Decimal("12.00"),
        },
        {
            "slug": "custom-name-keychain",
            "name": "Custom Name Keychain",
            "category": "personalized-gifts",
            "collection": "market-best-sellers",
            "sku_base": "PRS-KEYCHAIN",
            "short_description": "Personalized keychains made to order.",
            "base_price": Decimal("9.00"),
        },
        {
            "slug": "qr-code-counter-sign",
            "name": "QR Code Counter Sign",
            "category": "small-business-products",
            "collection": "small-biz-boosters",
            "sku_base": "B2B-QR-SIGN",
            "short_description": "A practical QR sign for vendor booths and checkout counters.",
            "base_price": Decimal("20.00"),
        },
        {
            "slug": "business-card-holder",
            "name": "Business Card Holder",
            "category": "small-business-products",
            "collection": "small-biz-boosters",
            "sku_base": "B2B-CARD-HOLDER",
            "short_description": "A clean, useful countertop business card display.",
            "base_price": Decimal("15.00"),
        },
        {
            "slug": "vendor-price-tag-stand",
            "name": "Vendor Price Tag Stand",
            "category": "small-business-products",
            "collection": "small-biz-boosters",
            "sku_base": "B2B-TAG-STAND",
            "short_description": "Easy-to-read price display for vendor markets.",
            "base_price": Decimal("6.00"),
        },
        {
            "slug": "custom-order-deposit",
            "name": "Custom Order Deposit",
            "category": "custom-orders",
            "collection": "market-best-sellers",
            "sku_base": "CSTM-DEPOSIT",
            "short_description": "Used to collect deposits for custom work.",
            "base_price": Decimal("25.00"),
        },
    ]

    products = {}
    for definition in product_definitions:
        product = _upsert(
            Product,
            {"slug": definition["slug"]},
            {
                "name": definition["name"],
                "business_id": business.id,
                "category": categories[definition["category"]],
                "collection": collections[definition["collection"]],
                "sku_base": definition["sku_base"],
                "short_description": definition["short_description"],
                "description": definition["short_description"],
                "product_type": ProductType.FINISHED_GOOD,
                "status": ProductStatus.ACTIVE,
                "is_public": definition["slug"] != "custom-order-deposit",
                "is_pos_visible": True,
                "is_featured": definition["slug"]
                in {"rainbow-dragon", "fidget-slider", "qr-code-counter-sign"},
                "base_price": definition["base_price"],
                "estimated_material_cost": Decimal("2.50"),
                "estimated_labor_minutes": 10,
                "estimated_print_minutes": 180,
                "estimated_profit": definition["base_price"] - Decimal("2.50"),
                "tags": "demo,phase-2",
                "license_status": LicenseStatus.COMMERCIAL_ALLOWED,
                "design_source": "Seeded demo catalog",
                "commercial_license_notes": "Seed data for Phase 2 catalog.",
            },
        )
        products[definition["slug"]] = product

    variants = [
        (
            "rainbow-dragon",
            "DRG-RAINBOW-STD",
            "Standard Rainbow",
            "Rainbow",
            "Large",
            "PLA",
            Decimal("28.00"),
        ),
        (
            "small-articulated-dragon",
            "DRG-SMALL-SUNSET",
            "Sunset Small Dragon",
            "Sunset",
            "Small",
            "PLA",
            Decimal("14.00"),
        ),
        (
            "mystery-dragon-egg",
            "DRG-EGG-MYSTERY",
            "Mystery Egg",
            "Mystery",
            "Medium",
            "PLA",
            Decimal("18.00"),
        ),
        (
            "fidget-slider",
            "FGT-SLIDER-TEAL",
            "Teal Slider",
            "Teal",
            "Pocket",
            "PLA",
            Decimal("8.00"),
        ),
        (
            "flexi-turtle",
            "FLX-TURTLE-SEAFOAM",
            "Seafoam Turtle",
            "Seafoam",
            "Standard",
            "PLA",
            Decimal("10.00"),
        ),
        (
            "flexi-axolotl",
            "FLX-AXOLOTL-BLOSSOM",
            "Blossom Axolotl",
            "Blossom",
            "Standard",
            "PLA",
            Decimal("11.00"),
        ),
        (
            "clarksville-tn-magnet",
            "CLK-MAGNET-BLUE",
            "Clarksville Magnet",
            "Blue",
            "Standard",
            "PLA",
            Decimal("7.00"),
        ),
        (
            "tennessee-ornament",
            "TN-ORNAMENT-WOOD",
            "Wood-Tone Ornament",
            "Wood Tone",
            "Standard",
            "PLA",
            Decimal("12.00"),
        ),
        (
            "custom-name-keychain",
            "PRS-KEYCHAIN-BASIC",
            "Basic Name Keychain",
            "Custom",
            "Standard",
            "PLA",
            Decimal("9.00"),
        ),
        (
            "qr-code-counter-sign",
            "B2B-QR-SIGN-BLACK",
            "Black QR Sign",
            "Black",
            "Standard",
            "PETG",
            Decimal("20.00"),
        ),
        (
            "business-card-holder",
            "B2B-CARD-HOLDER-WHITE",
            "White Card Holder",
            "White",
            "Standard",
            "PLA",
            Decimal("15.00"),
        ),
        (
            "vendor-price-tag-stand",
            "B2B-TAG-STAND-CLEAR",
            "Clear Tag Stand",
            "Clear",
            "Standard",
            "PLA",
            Decimal("6.00"),
        ),
        (
            "custom-order-deposit",
            "CSTM-DEPOSIT-BASE",
            "Deposit Placeholder",
            "N/A",
            "N/A",
            "N/A",
            Decimal("25.00"),
        ),
    ]

    product_variants = {}
    for index, (product_slug, sku, name, colorway, size, material_type, price) in enumerate(
        variants, start=1
    ):
        variant = _upsert(
            ProductVariant,
            {"sku": sku},
            {
                "product": products[product_slug],
                "business_id": business.id,
                "name": name,
                "colorway": colorway,
                "size": size,
                "material_type": material_type,
                "price": price,
                "material_cost": Decimal("2.00"),
                "estimated_print_minutes": 120,
                "estimated_filament_grams": 85,
                "active": True,
                "pos_button_label": name,
                "pos_sort_order": index,
                "barcode_or_qr_code": f"SKU:{sku}",
            },
        )
        product_variants[sku] = variant

    for slug, product in products.items():
        _upsert(
            ModelAsset,
            {"title": f"{product.name} Master Asset"},
            {
                "source_type": ModelSourceType.SELF_DESIGNED,
                "source_url": None,
                "designer_name": "Dude Fish Printing",
                "license_type": "Internal Commercial",
                "commercial_use_allowed": True,
                "proof_of_license_path": "uploads/licenses/demo-proof.pdf",
                "file_location": f"uploads/models/{slug}.3mf",
                "product": product,
                "notes": "Demo asset record for Phase 2.",
                "status": LicenseStatus.COMMERCIAL_ALLOWED,
            },
        )

    printers = [
        ("Bambu A1 #1", "Bambu A1", PrinterStatus.ACTIVE, True),
        ("Bambu A1 #2", "Bambu A1", PrinterStatus.ACTIVE, True),
        ("Bambu A1 #3", "Bambu A1", PrinterStatus.IDLE, True),
        ("Bambu A1 #4", "Bambu A1", PrinterStatus.IDLE, True),
        ("Bambu X1 Carbon #1", "Bambu X1 Carbon", PrinterStatus.ACTIVE, True),
        ("Bambu X1 Carbon #2 - Broken", "Bambu X1 Carbon", PrinterStatus.BROKEN, True),
        ("Bambu P1P #1", "Bambu P1P", PrinterStatus.ACTIVE, False),
        ("Bambu P1P #2", "Bambu P1P", PrinterStatus.IDLE, False),
    ]
    printer_map = {}
    for name, model, status, has_ams in printers:
        printer = _upsert(
            Printer,
            {"name": name},
            {
                "model": model,
                "status": status,
                "location": "Shop Floor",
                "has_ams": has_ams,
                "default_nozzle_size": "0.4mm",
                "notes": "Seeded printer fleet record.",
                "total_print_hours": 0,
            },
        )
        printer_map[name] = printer

    ams_units = [
        ("AMS Lite #1", AMSUnitType.AMS_LITE, AMSUnitStatus.ASSIGNED, "Bambu A1 #1"),
        ("AMS Lite #2", AMSUnitType.AMS_LITE, AMSUnitStatus.ASSIGNED, "Bambu A1 #2"),
        ("AMS Lite #3", AMSUnitType.AMS_LITE, AMSUnitStatus.ASSIGNED, "Bambu A1 #3"),
        ("AMS Lite #4", AMSUnitType.AMS_LITE, AMSUnitStatus.ASSIGNED, "Bambu A1 #4"),
        ("Standard AMS #1", AMSUnitType.STANDARD_AMS, AMSUnitStatus.ASSIGNED, "Bambu X1 Carbon #1"),
    ]
    for name, unit_type, status, printer_name in ams_units:
        _upsert(
            AMSUnit,
            {"name": name},
            {
                "type": unit_type,
                "status": status,
                "assigned_printer": printer_map.get(printer_name),
                "slot_count": 4,
                "notes": "Seeded AMS unit.",
            },
        )

    locations = {
        item.name: item
        for item in [
            _upsert(
                InventoryLocation,
                {"name": "Home Inventory"},
                {"business_id": business.id, "type": "Storage", "description": "Primary home stock.", "active": True},
            ),
            _upsert(
                InventoryLocation,
                {"name": "Market Bin"},
                {"business_id": business.id, "type": "Travel", "description": "Packed for vendor markets.", "active": True},
            ),
            _upsert(
                InventoryLocation,
                {"name": "Website Stock"},
                {
                    "business_id": business.id,
                    "type": "Fulfillment",
                    "description": "Ready for online requests.",
                    "active": True,
                },
            ),
            _upsert(
                InventoryLocation,
                {"name": "Finished Goods Shelf"},
                {
                    "business_id": business.id,
                    "type": "Storage",
                    "description": "Finished display-ready products.",
                    "active": True,
                },
            ),
            _upsert(
                InventoryLocation,
                {"name": "Custom Order Hold"},
                {"business_id": business.id, "type": "Reserved", "description": "Customer-specific holds.", "active": True},
            ),
            _upsert(
                InventoryLocation,
                {"name": "Damaged/Seconds"},
                {"business_id": business.id, "type": "Exception", "description": "Seconds and damaged items.", "active": True},
            ),
        ]
    }

    filament_spools = [
        (
            "Bambu",
            "PLA",
            "Rainbow Silk",
            "#d946ef",
            1000,
            620,
            Decimal("24.99"),
            Decimal("0.0250"),
            FilamentStatus.ACTIVE,
        ),
        (
            "PolyTerra",
            "PLA",
            "Teal",
            "#14b8a6",
            1000,
            540,
            Decimal("21.99"),
            Decimal("0.0220"),
            FilamentStatus.ACTIVE,
        ),
        (
            "Overture",
            "PLA",
            "Seafoam",
            "#67e8f9",
            1000,
            200,
            Decimal("19.99"),
            Decimal("0.0200"),
            FilamentStatus.LOW,
        ),
        (
            "eSUN",
            "PETG",
            "Black",
            "#111827",
            1000,
            720,
            Decimal("23.99"),
            Decimal("0.0240"),
            FilamentStatus.ACTIVE,
        ),
    ]
    for (
        brand,
        material,
        color_name,
        color_hex,
        spool_weight,
        remaining,
        cost_spool,
        cost_gram,
        status,
    ) in filament_spools:
        _upsert(
            FilamentSpool,
            {"brand": brand, "material_type": material, "color_name": color_name},
            {
                "business_id": business.id,
                "color_hex": color_hex,
                "spool_weight_grams": spool_weight,
                "remaining_weight_grams": remaining,
                "cost_per_spool": cost_spool,
                "cost_per_gram": cost_gram,
                "supplier": "Seed Supplier",
                "storage_location": "Filament Rack",
                "status": status,
                "reorder_threshold_grams": 150,
                "notes": "Seeded spool.",
            },
        )

    inventory_records = [
        ("Rainbow Dragon", "DRG-RAINBOW-STD", "Finished Goods Shelf", 4, 1, 2, 6),
        ("Small Articulated Dragon", "DRG-SMALL-SUNSET", "Market Bin", 8, 0, 4, 10),
        ("Mystery Dragon Egg", "DRG-EGG-MYSTERY", "Finished Goods Shelf", 5, 0, 2, 6),
        ("Fidget Slider", "FGT-SLIDER-TEAL", "Market Bin", 18, 2, 8, 24),
        ("Flexi Turtle", "FLX-TURTLE-SEAFOAM", "Website Stock", 9, 1, 3, 12),
        ("Flexi Axolotl", "FLX-AXOLOTL-BLOSSOM", "Market Bin", 7, 0, 3, 10),
        ("Clarksville TN Magnet", "CLK-MAGNET-BLUE", "Finished Goods Shelf", 12, 0, 5, 18),
        ("Tennessee Ornament", "TN-ORNAMENT-WOOD", "Website Stock", 6, 0, 2, 8),
        ("Custom Name Keychain", "PRS-KEYCHAIN-BASIC", "Home Inventory", 10, 2, 4, 16),
        ("QR Code Counter Sign", "B2B-QR-SIGN-BLACK", "Website Stock", 3, 0, 1, 5),
        ("Business Card Holder", "B2B-CARD-HOLDER-WHITE", "Website Stock", 4, 0, 2, 6),
        ("Vendor Price Tag Stand", "B2B-TAG-STAND-CLEAR", "Market Bin", 14, 0, 5, 18),
        ("Custom Order Deposit", "CSTM-DEPOSIT-BASE", "Custom Order Hold", 1, 0, 0, 1),
    ]
    product_by_name = {product.name: product for product in products.values()}
    variant_by_sku = {variant.sku: variant for variant in product_variants.values()}
    for (
        product_name,
        variant_sku,
        location_name,
        on_hand,
        reserved,
        threshold,
        target,
    ) in inventory_records:
        _upsert(
            InventoryRecord,
            {
                "product": product_by_name[product_name],
                "variant": variant_by_sku[variant_sku],
                "location": locations[location_name],
            },
            {
                "business_id": business.id,
                "quantity_on_hand": on_hand,
                "quantity_reserved": reserved,
                "reorder_threshold": threshold,
                "reorder_target": target,
            },
        )

    _upsert(
        Market,
        {"name": "Clarksville Saturday Market"},
        {
            "name": "Clarksville Saturday Market",
            "business_id": business.id,
            "location_name": "Downtown Clarksville",
            "address": "100 Public Square",
            "city": "Clarksville",
            "state": "TN",
            "event_date": date(2026, 5, 10),
            "booth_fee": Decimal("75.00"),
            "application_fee": Decimal("10.00"),
            "status": MarketStatus.COMPLETED,
            "expected_traffic": "High",
            "actual_revenue": Decimal("450.00"),
            "actual_profit": Decimal("320.00"),
            "notes": "Great first market. Sold lots of dragons and fidgets.",
        },
    )
    _upsert(
        Market,
        {"name": "Riverside Craft Fair"},
        {
            "name": "Riverside Craft Fair",
            "business_id": business.id,
            "location_name": "Riverside Park",
            "address": "200 River Road",
            "city": "Clarksville",
            "state": "TN",
            "event_date": date(2026, 6, 21),
            "booth_fee": Decimal("100.00"),
            "status": MarketStatus.SCHEDULED,
            "expected_traffic": "Medium",
            "notes": "Outdoor event. Need tent and weights.",
        },
    )

    _upsert(
        MarketPackingList,
        {"market_id": 1, "product_id": products["rainbow-dragon"].id},
        {
            "market_id": 1,
            "product_id": products["rainbow-dragon"].id,
            "planned_quantity": 10,
            "packed_quantity": 8,
            "sold_quantity": 6,
            "returned_quantity": 2,
        },
    )
    _upsert(
        MarketPackingList,
        {"market_id": 1, "product_id": products["fidget-slider"].id},
        {
            "market_id": 1,
            "product_id": products["fidget-slider"].id,
            "planned_quantity": 20,
            "packed_quantity": 18,
            "sold_quantity": 15,
            "returned_quantity": 3,
        },
    )

    customers = {
        item.email: item
        for item in [
            _upsert(
                Customer,
                {"email": "sarah@example.com"},
                {
                    "first_name": "Sarah",
                    "last_name": "Johnson",
                    "phone": "931-555-0101",
                    "city": "Clarksville",
                    "state": "TN",
                    "is_active": True,
                    "notes": "Regular customer from vendor markets.",
                },
            ),
            _upsert(
                Customer,
                {"email": "mike@example.com"},
                {
                    "first_name": "Mike",
                    "last_name": "Chen",
                    "phone": "931-555-0102",
                    "city": "Clarksville",
                    "state": "TN",
                    "is_active": True,
                    "notes": "Custom order repeat client.",
                },
            ),
        ]
    }

    _upsert(
        CustomRequest,
        {"name": "Emily Davis", "email": "emily@example.com"},
        {
            "description": "I'd like a custom articulated dragon in purple and teal, about 12 inches long.",
            "estimated_budget": Decimal("35.00"),
            "subtotal": Decimal("45.00"),
            "tax": Decimal("3.60"),
            "discount": Decimal("0"),
            "total": Decimal("48.60"),
            "amount_paid": Decimal("25.00"),
            "source": "website",
            "status": CustomRequestStatus.APPROVED,
        },
    )
    _upsert(
        CustomRequest,
        {"name": "Tom Wilson", "email": "tom@example.com"},
        {
            "description": "Need a custom business card holder that fits thicker cards, in matte black.",
            "estimated_budget": Decimal("18.00"),
            "subtotal": Decimal("25.00"),
            "tax": Decimal("2.00"),
            "discount": Decimal("0"),
            "total": Decimal("27.00"),
            "amount_paid": Decimal("27.00"),
            "source": "website",
            "status": CustomRequestStatus.COMPLETED,
        },
    )

    demo_order = _upsert(
        Order,
        {"order_number": "DFP-DEMO-001"},
        {
            "customer": customers.get("sarah@example.com"),
            "status": OrderStatus.CONFIRMED,
            "source": OrderSource.MANUAL,
            "subtotal": Decimal("36.00"),
            "total": Decimal("36.00"),
            "paid_amount": Decimal("36.00"),
            "notes": "Demo order for Phase 3 testing.",
        },
    )

    rainbow_item = OrderItem(
        order=demo_order,
        product=products["rainbow-dragon"],
        variant=product_variants["DRG-RAINBOW-STD"],
        quantity=1,
        unit_price=Decimal("28.00"),
        line_total=Decimal("28.00"),
    )
    db.session.add(rainbow_item)

    fidget_item = OrderItem(
        order=demo_order,
        product=products["fidget-slider"],
        variant=product_variants["FGT-SLIDER-TEAL"],
        quantity=1,
        unit_price=Decimal("8.00"),
        line_total=Decimal("8.00"),
    )
    db.session.add(fidget_item)
    db.session.flush()

    _upsert(
        Payment,
        {"order_id": demo_order.id, "amount": Decimal("36.00")},
        {
            "amount": Decimal("36.00"),
            "method": PaymentMethod.CASH,
            "notes": "Cash payment at market.",
        },
    )

    _upsert(
        PrintJob,
        {"label": "Rainbow Dragon - Market Stock Replenish"},
        {
            "order_item_id": rainbow_item.id,
            "product_id": products["rainbow-dragon"].id,
            "variant_id": product_variants["DRG-RAINBOW-STD"].id,
            "status": PrintJobStatus.QUEUED,
            "priority": 1,
            "estimated_minutes": 180,
            "label": "Rainbow Dragon - Market Stock Replenish",
        },
    )

    admin_user = User.query.filter_by(email=admin_email).first()

    demo_session = _upsert(
        PosSession,
        {"session_number": "POS-DEMO-001"},
        {
            "session_number": "POS-DEMO-001",
            "opened_by_user_id": admin_user.id,
            "status": PosSessionStatus.OPEN,
            "opening_cash": Decimal("100.00"),
            "market_id": 1,
            "notes": "Demo POS session for vendor market.",
        },
    )

    if not PosSale.query.filter_by(sale_number="SALE-DEMO-001").first():
        demo_sale = PosSale(
            pos_session_id=demo_session.id,
            sale_number="SALE-DEMO-001",
            subtotal=Decimal("45.00"),
            total=Decimal("45.00"),
            payment_method="cash",
            amount_received=Decimal("50.00"),
            change_due=Decimal("5.00"),
            status=PosSaleStatus.COMPLETED,
            notes="Demo POS sale.",
            items=[
                PosSaleItem(
                    product_id=products["rainbow-dragon"].id,
                    variant_id=product_variants["DRG-RAINBOW-STD"].id,
                    quantity=1,
                    unit_price=Decimal("25.00"),
                    line_total=Decimal("25.00"),
                    item_type=PosSaleItemType.PRODUCT,
                    description="Rainbow Dragon",
                ),
                PosSaleItem(
                    product_id=products["fidget-slider"].id,
                    variant_id=product_variants["FGT-SLIDER-TEAL"].id,
                    quantity=2,
                    unit_price=Decimal("10.00"),
                    line_total=Decimal("20.00"),
                    item_type=PosSaleItemType.PRODUCT,
                    description="Fidget Slider",
                ),
            ],
        )
        db.session.add(demo_sale)

    _upsert(
        Expense,
        {"date": date(2026, 5, 8), "vendor": "ProtoPasta", "amount": Decimal("45.00")},
        {
            "date": date(2026, 5, 8),
            "business_id": business.id,
            "vendor": "ProtoPasta",
            "category": ExpenseCategory.FILAMENT,
            "description": "Rainbow silk PLA filament 1kg",
            "amount": Decimal("45.00"),
            "payment_method": "credit_card",
            "related_market_id": 1,
            "tax_deductible": True,
        },
    )
    _upsert(
        Expense,
        {"date": date(2026, 5, 10), "vendor": "Clarksville Market", "amount": Decimal("85.00")},
        {
            "date": date(2026, 5, 10),
            "business_id": business.id,
            "vendor": "Clarksville Market",
            "category": ExpenseCategory.BOOTH_FEES,
            "description": "Booth fee plus application fee for Saturday Market",
            "amount": Decimal("85.00"),
            "payment_method": "cash",
            "related_market_id": 1,
            "tax_deductible": True,
        },
    )
    _upsert(
        Expense,
        {"date": date(2026, 5, 12), "vendor": "Uline", "amount": Decimal("22.50")},
        {
            "date": date(2026, 5, 12),
            "business_id": business.id,
            "vendor": "Uline",
            "category": ExpenseCategory.PACKAGING,
            "description": "Poly bags and tissue paper for product packaging",
            "amount": Decimal("22.50"),
            "payment_method": "credit_card",
            "tax_deductible": True,
        },
    )

    from app.services.settings import seed_default_settings
    seed_default_settings()

    def _seed_demo_receipts(admin_user):
        if Receipt.query.filter_by(receipt_number="DEMO-RCP-001").first():
            return

        receipt = Receipt(
            user_id=admin_user.id,
            business_id=business.id,
            status=ReceiptStatus.APPROVED,
            source_type=ReceiptSourceType.UPLOAD,
            merchant_name="ProtoPasta",
            store_name="ProtoPasta Store",
            receipt_number="DEMO-RCP-001",
            date_time=datetime(2026, 5, 8, 11, 30, tzinfo=timezone.utc),
            subtotal=Decimal("45.00"),
            tax_total=Decimal("3.60"),
            grand_total=Decimal("48.60"),
            payment_method="credit_card",
            currency="USD",
            file_hash="demo-hash-001",
            confidence_overall=Decimal("0.95"),
            approved_by_id=admin_user.id,
            approved_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            notes="Demo receipt for ProtoPasta filament purchase.",
        )
        db.session.add(receipt)
        db.session.flush()

        line_item = ReceiptLineItem(
            receipt_id=receipt.id,
            row_order=0,
            description="Rainbow Silk PLA Filament 1kg",
            sku="FIL-PLA-RNB",
            quantity=Decimal("1"),
            unit_price=Decimal("45.00"),
            line_subtotal=Decimal("45.00"),
            line_total=Decimal("45.00"),
            line_tax=Decimal("3.60"),
            taxable_status="taxable",
            needs_review=False,
        )
        db.session.add(line_item)
        db.session.flush()

        set_line_allocation(line_item.id, AllocationType.INVENTORY, amount=Decimal("48.60"), percent=Decimal("100"))

        receipt2 = Receipt(
            user_id=admin_user.id,
            business_id=business.id,
            status=ReceiptStatus.NEEDS_REVIEW,
            source_type=ReceiptSourceType.UPLOAD,
            merchant_name="Clarksville Market",
            receipt_number="DEMO-RCP-002",
            date_time=datetime(2026, 5, 10, 8, 0, tzinfo=timezone.utc),
            subtotal=Decimal("85.00"),
            tax_total=Decimal("0"),
            grand_total=Decimal("85.00"),
            payment_method="cash",
            currency="USD",
            file_hash="demo-hash-002",
            confidence_overall=Decimal("0.85"),
            notes="Demo receipt for booth fee payment.",
        )
        db.session.add(receipt2)
        db.session.flush()

        line_item2 = ReceiptLineItem(
            receipt_id=receipt2.id,
            row_order=0,
            description="Booth Fee + Application Fee",
            unit_price=Decimal("85.00"),
            line_subtotal=Decimal("85.00"),
            line_total=Decimal("85.00"),
            taxable_status="non_taxable",
            needs_review=True,
        )
        db.session.add(line_item2)
        db.session.flush()

        set_line_allocation(line_item2.id, AllocationType.MARKET, amount=Decimal("85.00"), percent=Decimal("100"), market_id=1)

        db.session.flush()

    _seed_demo_receipts(admin_user)

    db.session.commit()
    return {
        "categories": Category.query.count(),
        "collections": Collection.query.count(),
        "products": Product.query.count(),
        "variants": ProductVariant.query.count(),
        "model_assets": ModelAsset.query.count(),
        "printers": Printer.query.count(),
        "ams_units": AMSUnit.query.count(),
        "filament_spools": FilamentSpool.query.count(),
        "inventory_locations": InventoryLocation.query.count(),
        "inventory_records": InventoryRecord.query.count(),
        "customers": Customer.query.count(),
        "custom_requests": CustomRequest.query.count(),
        "orders": Order.query.count(),
        "order_items": OrderItem.query.count(),
        "payments": Payment.query.count(),
        "expenses": Expense.query.count(),
        "markets": Market.query.count(),
        "market_packing_lists": MarketPackingList.query.count(),
        "print_jobs": PrintJob.query.count(),
        "pos_sessions": PosSession.query.count(),
        "pos_sales": PosSale.query.count(),
        "pos_sale_items": PosSaleItem.query.count(),
        "receipts": Receipt.query.count(),
        "settings": Setting.query.count(),
    }
