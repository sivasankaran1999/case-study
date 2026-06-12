"""Tool: order support via direct redirects to PartSelect.

We deliberately do NOT scrape order status or place orders. Transactions and
order tracking happen on the real PartSelect platform — this is safer (no
payment/credential handling), simpler, and better UX. The agent's job is to
hand the user the correct PartSelect link.
"""

from config.settings import settings

ORDER_STATUS_PATH = "/user/orders/"


def _base() -> str:
    return settings.PARTSELECT_BASE_URL.rstrip("/")


def _normalize_part_number(part_number: str) -> str:
    pn = (part_number or "").upper().strip()
    if pn and not pn.startswith("PS"):
        pn = f"PS{pn}"
    return pn


def get_part_order_link(part_number: str, product_url: str | None = None) -> dict:
    """
    Return a direct PartSelect product link for ordering a specific part.

    Args:
        part_number: e.g. "PS11752778" (or the bare digits).
        product_url: canonical product URL if the agent already resolved one
            (e.g. from a prior part lookup). Used as-is when provided.

    Returns a payload with response type ``order_redirect``.
    """
    pn = _normalize_part_number(part_number)
    url = product_url or f"{_base()}/{pn}-Part.htm"

    if pn:
        message = (
            f"You can order {pn} directly on PartSelect, where you'll see live "
            "pricing, stock, and secure checkout."
        )
    else:
        message = (
            "You can browse and order parts directly on PartSelect, where you'll "
            "see live pricing, stock, and secure checkout."
        )

    return {
        "type": "order_redirect",
        "message": message,
        "part_number": pn,
        "url": url,
    }


def get_order_status_link() -> dict:
    """
    Return the PartSelect order status page link.

    Returns a payload with response type ``order_status_redirect``.
    """
    url = f"{_base()}{ORDER_STATUS_PATH}"
    return {
        "type": "order_status_redirect",
        "message": (
            "You can check your order status and tracking directly on PartSelect. "
            "Sign in to your account to see the latest updates."
        ),
        "url": url,
    }


def get_returns_link() -> dict:
    """
    Return the PartSelect returns page link.

    Like order status, returns are redirect-only — the agent never processes a
    return itself. The 365-day returns page explains the policy and has the
    "Start a Return" button that walks the user through the self-service flow.

    Returns a payload with response type ``returns_redirect``.
    """
    return {
        "type": "returns_redirect",
        "message": (
            "PartSelect offers a 365-day return window. You can review the policy "
            "and start your return directly on PartSelect — you'll need your order "
            "number and the email used at checkout."
        ),
        "url": settings.RETURNS_URL,
    }
