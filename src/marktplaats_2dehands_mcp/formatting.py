"""Helpers for parsing and formatting Adevinta listing API responses."""

import re
from datetime import datetime
from enum import Enum

BUSINESS_TRAITS = {
    "ADMARKT_CONSOLE",
    "CUSTOMER_SUPPORT_BUSINESS_LINE",
    "SELLER_PROFILE_URL",
    "VERIFIED_SELLER",
    "UNIQUE_SELLING_POINTS",
    "SHOPPING_CART",
}

BUSINESS_NAME_PATTERNS = [
    r"used products",
    r"buy\s*&?\s*sell",
    r"mediahoek",
    r"it[- ]?resale",
    r"\.nl$",
    r"\.com$",
    r"\.be$",
    r"b\.?v\.?$",
    r"webshop",
    r"shop\b",
    r"store\b",
    r"handel",
    r"electronics",
    r"refurbished",
    r"outlet",
]


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


def detect_seller_type(traits: list[str], seller_name: str = "") -> str:
    if set(traits) & BUSINESS_TRAITS:
        return "business"
    if seller_name:
        name_lower = seller_name.lower()
        for pattern in BUSINESS_NAME_PATTERNS:
            if re.search(pattern, name_lower):
                return "business"
    return "private"


def format_date_short(date_str: str) -> str:
    if not date_str:
        return ""

    date_lower = date_str.lower()
    if "vandaag" in date_lower:
        return "0d"
    if "eergisteren" in date_lower:
        return "2d"
    if "gisteren" in date_lower:
        return "1d"

    month_map = {
        "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
    }
    match = re.match(r"(\d{1,2})\s+(\w{3})\s+'?(\d{2})", date_str)
    if match:
        day, month_str, year = match.groups()
        month = month_map.get(month_str.lower())
        if month:
            try:
                listing_date = datetime(2000 + int(year), month, int(day))
                days_ago = (datetime.now() - listing_date).days
                if days_ago < 7:
                    return f"{days_ago}d"
                if days_ago < 30:
                    return f"{days_ago // 7}w"
                return f"{days_ago // 30}m"
            except ValueError:
                pass
    return date_str


def format_condition_short(condition: str | None) -> str:
    if not condition:
        return ""
    cond_lower = condition.lower()
    if "nieuw" in cond_lower and "zo goed" not in cond_lower:
        return "N"
    if "zo goed als nieuw" in cond_lower:
        return "Z"
    if "gebruikt" in cond_lower:
        return "G"
    if "refurbished" in cond_lower:
        return "R"
    if "defect" in cond_lower or "niet werkend" in cond_lower:
        return "D"
    return ""


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
            "type": detect_seller_type(traits, seller_name),
        },
        "date": listing.get("date"),
        "image": first_image,
        "link": listing_link,
    }


def format_listing_compact(listing: dict) -> dict:
    price_info = listing.get("priceInfo", {})
    location = listing.get("location", {})
    seller = listing.get("sellerInformation", {})
    traits = listing.get("traits", [])
    seller_name = seller.get("sellerName", "")

    distance_meters = location.get("distanceMeters")
    distance_km = None
    if distance_meters is not None and distance_meters >= 0:
        distance_km = round(distance_meters / 1000, 1)

    title = listing.get("title", "")
    condition = next(
        (a.get("value") for a in listing.get("attributes", []) if a.get("key") == "condition"),
        None,
    )

    price_type = price_info.get("priceType", "")
    price_cents = price_info.get("priceCents", 0)
    if price_type in ("FIXED", "RESERVED") and price_cents > 0:
        price = price_cents // 100
    elif price_type == "FREE" or price_cents == 0:
        price = 0
    elif price_type == "BID":
        price = "bid"
    elif price_type == "BID_FROM":
        price = f">{price_cents // 100}"
    elif price_type == "SEE_DESCRIPTION":
        price = "?"
    elif price_type == "TO_BE_AGREED_UPON":
        price = "notk"
    elif price_type == "EXCHANGE":
        price = "ruil"
    else:
        price = price_cents // 100 if price_cents > 0 else "?"

    result: dict = {
        "id": listing.get("itemId"),
        "title": title.strip(),
        "price": price,
        "city": location.get("cityName"),
        "seller": "B" if detect_seller_type(traits, seller_name) == "business" else "P",
    }
    if distance_km is not None:
        result["km"] = distance_km
    cond_short = format_condition_short(condition)
    if cond_short:
        result["cond"] = cond_short
    date_short = format_date_short(listing.get("date", ""))
    if date_short:
        result["age"] = date_short
    return result
