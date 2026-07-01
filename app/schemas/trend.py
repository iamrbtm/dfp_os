from __future__ import annotations

from marshmallow import Schema, fields


class TrendReportSchema(Schema):
    id = fields.Integer(dump_only=True)
    report_date = fields.DateTime(dump_only=True)
    summary = fields.String(allow_none=True)
    top_opportunities = fields.Raw(allow_none=True)
    growing_categories = fields.Raw(allow_none=True)
    declining_trends = fields.Raw(allow_none=True)
    pipeline_meta = fields.Raw(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    opportunity_scores = fields.List(
        fields.Nested("TrendOpportunityScoreSchema"), dump_only=True, attribute="opportunity_scores"
    )
    source_health_records = fields.List(
        fields.Nested("TrendSourceHealthRecordSchema"), dump_only=True, attribute="source_health_records"
    )


class TrendOpportunityScoreSchema(Schema):
    id = fields.Integer(dump_only=True)
    report_id = fields.Integer(dump_only=True)
    candidate_type = fields.String()
    product_id = fields.Integer(allow_none=True)
    keyword = fields.String()
    title = fields.String(allow_none=True)
    opportunity_score = fields.Integer()
    purchase_intent = fields.Integer()
    trend_velocity = fields.Integer()
    price_resilience = fields.Integer()
    low_saturation = fields.Integer()
    local_fit = fields.Integer()
    production_fit = fields.Integer()
    license_risk = fields.Integer()
    action = fields.String()
    inventory_available = fields.Integer()
    base_price = fields.Decimal(as_string=True)
    license_status = fields.String(allow_none=True)
    rank = fields.Integer(allow_none=True)
    sources = fields.Raw(allow_none=True)
    score_breakdown = fields.Raw(allow_none=True)
    source_health = fields.Raw(allow_none=True)
    match_confidence = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class TrendSourceHealthRecordSchema(Schema):
    id = fields.Integer(dump_only=True)
    report_id = fields.Integer(dump_only=True, allow_none=True)
    source = fields.String()
    status = fields.String()
    keyword = fields.String(allow_none=True)
    item_count = fields.Integer()
    error_message = fields.String(allow_none=True)
    scraped_at = fields.DateTime(allow_none=True, dump_only=True)
    metadata_json = fields.Raw(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
