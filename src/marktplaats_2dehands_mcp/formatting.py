"""Helpers for parsing and formatting Adevinta listing API responses."""

from enum import Enum

BUSINESS_TRAITS = {
    "ADMARKT_CONSOLE",
    "CUSTOMER_SUPPORT_BUSINESS_LINE",
    "SELLER_PROFILE_URL",
    "VERIFIED_SELLER",
    "UNIQUE_SELLING_POINTS",
    "SHOPPING_CART",
}


class SortBy(str, Enum):
    DATE = "SORT_INDEX"
    PRICE = "PRICE"
    OPTIMIZED = "OPTIMIZED"
    LOCATION = "LOCATION"


class SortOrder(str, Enum):
    ASC = "INCREASING"
    DESC = "DECREASING"


class Condition(int, Enum):
    NEW = 30
    REFURBISHED = 14050
    AS_GOOD_AS_NEW = 31
    USED = 32
    NOT_WORKING = 13940


CONDITION_MAP = {
    "new": Condition.NEW.value,
    "as_good_as_new": Condition.AS_GOOD_AS_NEW.value,
    "used": Condition.USED.value,
    "refurbished": Condition.REFURBISHED.value,
    "not_working": Condition.NOT_WORKING.value,
}


def parse_price(price_type: str, price_cents: int) -> str:
    price_map = {
        "FIXED": f"€ {price_cents / 100:,.2f}",
        "BID": "Bieden",
        "BID_FROM": f"Bieden vanaf € {price_cents / 100:,.2f}",
        "FREE": "Gratis",
        "RESERVED": "Gereserveerd",
        "SEE_DESCRIPTION": "Zie omschrijving",
        "TO_BE_AGREED_UPON": "N.o.t.k.",
        "ON_REQUEST": "Op aanvraag",
        "EXCHANGE": "Ruilen",
    }
    return price_map.get(price_type, f"€ {price_cents / 100:,.2f}")


def detect_seller_type(traits: list[str]) -> str:
    if set(traits) & BUSINESS_TRAITS:
        return "business"
    return "private"


def format_listing(listing: dict, listing_link: str) -> dict:
    price_info = listing.get("priceInfo", {})
    location = listing.get("location", {})
    seller = listing.get("sellerInformation", {})
    traits = listing.get("traits", [])
    seller_name = seller.get("sellerName", "")

    pictures = listing.get("pictures", [])
    first_image = pictures[0].get("mediumUrl", "") if pictures else ""
    if first_image and not first_image.startswith("http"):
        first_image = "https:" + first_image

    distance_meters = location.get("distanceMeters")
    distance_km = None
    if distance_meters is not None and distance_meters >= 0:
        distance_km = round(distance_meters / 1000, 1)

    description = listing.get("description", "") or ""
    title = listing.get("title", "")

    return {
        "id": listing.get("itemId"),
        "title": title,
        "description": description[:200] + "..." if len(description) > 200 else description,
        "price": parse_price(price_info.get("priceType", ""), price_info.get("priceCents", 0)),
        "price_cents": price_info.get("priceCents", 0),
        "condition": next(
            (a.get("value") for a in listing.get("attributes", []) if a.get("key") == "condition"),
            None,
        ),
        "location": {"city": location.get("cityName"), "distance_km": distance_km},
        "seller": {
            "id": seller.get("sellerId"),
            "name": seller_name,
            "is_verified": seller.get("isVerified", False),
            "type": detect_seller_type(traits),
        },
        "date": listing.get("date"),
        "image": first_image,
        "link": listing_link,
    }
