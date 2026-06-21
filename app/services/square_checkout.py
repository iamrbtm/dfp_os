from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import Order

SQUARE_API_VERSION = "2026-05-20"


class SquareCheckoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class SquarePaymentLink:
    payment_link_id: str
    url: str
    long_url: str | None = None


def square_checkout_enabled(config: dict) -> bool:
    return bool(config.get("SQUARE_ACCESS_TOKEN") and config.get("SQUARE_LOCATION_ID"))


def decimal_to_cents(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def create_payment_link(order: Order, config: dict) -> SquarePaymentLink:
    if not square_checkout_enabled(config):
        raise SquareCheckoutError("Square checkout is not configured.")

    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "description": f"Dude Fish Printing order {order.order_number}",
        "payment_note": f"Order {order.order_number}",
        "quick_pay": {
            "name": f"Dude Fish Printing order {order.order_number}",
            "price_money": {
                "amount": decimal_to_cents(order.total),
                "currency": config.get("SHOP_DEFAULT_CURRENCY", "USD"),
            },
            "location_id": config["SQUARE_LOCATION_ID"],
        },
    }

    request = Request(
        url=f"{config['SQUARE_API_BASE_URL'].rstrip('/')}/v2/online-checkout/payment-links",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['SQUARE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Square-Version": SQUARE_API_VERSION,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise SquareCheckoutError(f"Square checkout request failed: {details or exc.reason}") from exc
    except URLError as exc:
        raise SquareCheckoutError(f"Square checkout request failed: {exc.reason}") from exc

    payment_link = payload.get("payment_link") or {}
    url = payment_link.get("long_url") or payment_link.get("url")
    if not payment_link.get("id") or not url:
        raise SquareCheckoutError("Square checkout did not return a payment link.")

    return SquarePaymentLink(
        payment_link_id=payment_link["id"],
        url=url,
        long_url=payment_link.get("long_url"),
    )
