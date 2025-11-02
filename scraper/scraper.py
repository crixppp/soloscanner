#!/usr/bin/env python3
"""Fetch latest Hard Rated pricing and update data/prices.json."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "prices.json"
CONFIG_FILE = Path(__file__).with_name("config.json")
CONFIG_EXAMPLE_FILE = Path(__file__).with_name("config.example.json")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("solo-scanner")


@dataclass
class PackConfig:
    retailer: str
    suburb: str
    pack_size: int
    url: str
    source: str
    product_id: Optional[str] = None
    store_id: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    extra: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PackConfig":
        return cls(
            retailer=raw["retailer"],
            suburb=raw.get("suburb", ""),
            pack_size=int(raw["pack_size"]),
            url=raw.get("url", ""),
            source=raw.get("source", "custom"),
            product_id=raw.get("product_id"),
            store_id=raw.get("store_id"),
            headers=raw.get("headers"),
            extra=raw.get("extra"),
        )


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    if CONFIG_EXAMPLE_FILE.exists():
        logger.warning("config.json missing; falling back to config.example.json")
        with CONFIG_EXAMPLE_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    raise FileNotFoundError(
        "No configuration found. Create scraper/config.json based on config.example.json"
    )


def normalise_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    return merged


def extract_path(data: Any, dotted_path: Optional[str]) -> Optional[Any]:
    if not dotted_path:
        return None
    current = data
    for part in dotted_path.split('.'):
        if current is None:
            return None
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx >= len(current):
                return None
            current = current[idx]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def fetch_dan_murphys(session: requests.Session, pack: PackConfig) -> Dict[str, Any]:
    if not pack.product_id:
        raise ValueError("product_id required for Dan Murphy's")
    store_id = pack.store_id or "DMONLINE"
    url = (
        f"https://api.danmurphys.com.au/apis/ui/product/v3/detail/{pack.product_id}?storeId={store_id}"
    )
    response = session.get(url, timeout=20)
    response.raise_for_status()
    data = response.json()

    price_info: Optional[Dict[str, Any]] = None
    if isinstance(data, dict):
        price_info = data.get("Price") or data.get("price")
        if not price_info and "Products" in data:
            products = data.get("Products") or data.get("products") or []
            if isinstance(products, list) and products:
                price_info = products[0].get("Price") or products[0].get("price")

    if not price_info:
        raise ValueError("Unable to locate price data for Dan Murphy's response")

    price_total = price_info.get("FinalPrice") or price_info.get("Price") or price_info.get("SalePrice")
    unit_price = price_info.get("UnitPrice") or price_info.get("CupPrice")

    if price_total is None:
        raise ValueError("Dan Murphy's response missing price value")

    if unit_price is None and pack.pack_size:
        unit_price = float(price_total) / pack.pack_size

    return {
        "price_total": float(price_total),
        "price_unit": float(unit_price),
        "checked_at": int(time.time()),
    }


def fetch_bws(session: requests.Session, pack: PackConfig) -> Dict[str, Any]:
    if not pack.product_id:
        raise ValueError("product_id required for BWS")
    headers = normalise_headers(pack.headers)
    headers.setdefault("Referer", "https://bws.com.au/")
    headers.setdefault("Origin", "https://bws.com.au")

    url = f"https://bws.com.au/api/products/{pack.product_id}"
    response = session.get(url, timeout=20, headers=headers)
    response.raise_for_status()
    data = response.json()

    price_info = data.get("price") or data.get("Price") or {}
    price_total = price_info.get("current") or price_info.get("ActualPrice") or data.get("price")
    unit_price = price_info.get("perItem") or price_info.get("CupPrice")

    if price_total is None:
        raise ValueError("BWS response missing price")

    if unit_price is None and pack.pack_size:
        unit_price = float(price_total) / pack.pack_size

    return {
        "price_total": float(price_total),
        "price_unit": float(unit_price),
        "checked_at": int(time.time()),
    }


def fetch_liquorland_like(session: requests.Session, pack: PackConfig) -> Dict[str, Any]:
    """Liquorland and First Choice share the same API shape."""

    if not pack.product_id:
        raise ValueError("product_id required for Liquorland/First Choice")

    headers = normalise_headers(pack.headers)
    origin = "https://www.firstchoiceliquor.com.au" if pack.source == "first_choice" else "https://www.liquorland.com.au"
    headers.setdefault("Origin", origin)
    headers.setdefault("Referer", f"{origin}/")

    query = (
        "query ProductPricing($id: String!) {"
        " product(productId: $id) {"
        " pricing { current }"
        " cupPrice"
        " }"
        "}"
    )
    payload = {"query": query, "variables": {"id": pack.product_id}}

    response = session.post("https://api.liquorland.com.au/graphql", json=payload, timeout=20, headers=headers)
    response.raise_for_status()
    data = response.json()

    product = extract_path(data, "data.product")
    if not product:
        raise ValueError("Liquorland API missing product node")

    price_total = extract_path(product, "pricing.current")
    unit_price = extract_path(product, "cupPrice")

    if price_total is None:
        raise ValueError("Liquorland API missing price")

    if unit_price is None and pack.pack_size:
        unit_price = float(price_total) / pack.pack_size

    return {
        "price_total": float(price_total),
        "price_unit": float(unit_price),
        "checked_at": int(time.time()),
    }


def fetch_coles(session: requests.Session, pack: PackConfig, credentials: Dict[str, Any]) -> Dict[str, Any]:
    api_key = credentials.get("coles_api_key") or os.getenv("COLES_API_KEY")
    if not api_key:
        raise ValueError("Coles API key missing. Set COLES_API_KEY env var or config credential")
    if not pack.product_id:
        raise ValueError("product_id required for Coles")

    headers = normalise_headers(pack.headers)
    headers["Ocp-Apim-Subscription-Key"] = api_key

    url = f"https://api.coles.com.au/product/v1/productdetail/{pack.product_id}"
    response = session.get(url, timeout=20, headers=headers)
    response.raise_for_status()
    data = response.json()

    price_total = extract_path(data, "product.price.current") or extract_path(data, "productPrice.current")
    unit_price = extract_path(data, "product.price.unit") or extract_path(data, "productPrice.unit")

    if price_total is None:
        raise ValueError("Coles response missing price")

    if unit_price is None and pack.pack_size:
        unit_price = float(price_total) / pack.pack_size

    return {
        "price_total": float(price_total),
        "price_unit": float(unit_price),
        "checked_at": int(time.time()),
    }


def fetch_woolworths(session: requests.Session, pack: PackConfig) -> Dict[str, Any]:
    if not pack.product_id:
        raise ValueError("product_id required for Woolworths")

    headers = normalise_headers(pack.headers)
    url = f"https://www.woolworths.com.au/apis/ui/products/{pack.product_id}"
    response = session.get(url, timeout=20, headers=headers)
    response.raise_for_status()
    data = response.json()

    product = extract_path(data, "ProductDetail") or data
    price_total = extract_path(product, "Price.FinalPrice") or extract_path(product, "Price.SalePrice")
    unit_price = extract_path(product, "Price.CupPrice")

    if price_total is None and isinstance(product, dict):
        price_total = product.get("Price")

    if price_total is None:
        raise ValueError("Woolworths response missing price")

    if unit_price is None and pack.pack_size:
        unit_price = float(price_total) / pack.pack_size

    return {
        "price_total": float(price_total),
        "price_unit": float(unit_price),
        "checked_at": int(time.time()),
    }


FETCHERS = {
    "dan_murphys": fetch_dan_murphys,
    "bws": fetch_bws,
    "liquorland": fetch_liquorland_like,
    "first_choice": fetch_liquorland_like,
    "coles": fetch_coles,
    "woolworths": fetch_woolworths,
}


def load_pack_configs(config: Dict[str, Any]) -> Iterable[PackConfig]:
    packs: List[Dict[str, Any]] = config.get("packs", [])
    for raw in packs:
        yield PackConfig.from_dict(raw)


def build_entry(pack: PackConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "retailer": pack.retailer,
        "suburb": pack.suburb,
        "pack_size": pack.pack_size,
        "price_total": round(payload["price_total"], 2),
        "price_unit": round(payload["price_unit"], 2),
        "url": pack.url,
        "checked_at": payload.get("checked_at", int(time.time())),
    }


def write_prices(entries: List[Dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": int(datetime.now(timezone.utc).timestamp()),
        "items": entries,
    }
    with DATA_FILE.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def main() -> int:
    config = load_config()
    credentials = config.get("credentials", {})
    packs = list(load_pack_configs(config))
    if not packs:
        logger.error("No packs configured. Add pack definitions to scraper/config.json")
        return 1

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    entries: List[Dict[str, Any]] = []
    for pack in packs:
        fetcher = FETCHERS.get(pack.source)
        if not fetcher:
            logger.warning("No fetcher for %s; skipping", pack.source)
            continue
        try:
            logger.info("Fetching %s %sx", pack.retailer, pack.pack_size)
            payload = (
                fetcher(session, pack, credentials) if pack.source == "coles" else fetcher(session, pack)
            )
            entries.append(build_entry(pack, payload))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s %sx: %s", pack.retailer, pack.pack_size, exc)

    if not entries:
        logger.error("No pricing data collected")
        return 1

    write_prices(entries)
    logger.info("Wrote %d price rows to %s", len(entries), DATA_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
