from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import aiohttp

from .price import parse_discount, parse_price

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
STORE_PRODUCT = "https://store.playstation.com/{locale}/product/{product_id}"

SHA_CATEGORY_GRID = "4ce7d410a4db2c8b635a48c1dcec375906ff63b19dadd87e073f8fd0c0481d35"

CAT_PS4 = "44d8bb20-653e-431e-8ad0-c0a365f68d2f"
CAT_PS5 = "4cbf39e2-5749-4970-ba81-93a489e4570c"

CATEGORIES = (
    ("PS4", CAT_PS4),
    ("PS5", CAT_PS5),
)


@dataclass(slots=True)
class Offer:
    product_id: str
    name: str
    platforms: list[str]
    classification: str
    cover_url: str | None
    price: int | None
    base_price: int | None
    discount_text: str | None
    discount_percent: int | None
    is_free: bool
    plus_label: str | None = None
    plus_included: bool = False
    currency: str = "UAH"
    store_url: str = ""


@dataclass(slots=True)
class FacetValue:
    key: str
    name: str
    count: int


@dataclass(slots=True)
class Page:
    products: list[Offer] = field(default_factory=list)
    offset: int = 0
    size: int = 0
    total: int = 0
    is_last: bool = True
    facets: dict[str, list[FacetValue]] = field(default_factory=dict)


class PSNError(RuntimeError):
    pass


def thumb_url(url: str | None, width: int = 160) -> str | None:
    """PlayStation CDN can resize: full cover ~1MB, ?w=160 ~7KB JPEG."""
    if not url:
        return None
    host_ok = "image.api.playstation.com" in url or "playstation.net" in url
    if not host_ok:
        return url
    base = url.split("?", 1)[0]
    return f"{base}?w={width}&f=jpg"


def _cover(media: list[dict[str, Any]] | None) -> str | None:
    if not media:
        return None
    by_role = {m.get("role"): m.get("url") for m in media if m.get("type") == "IMAGE" and m.get("url")}
    for role in ("GAMEHUB_COVER_ART", "EDITION_KEY_ART", "MASTER", "BACKGROUND", "LOGO"):
        if by_role.get(role):
            return by_role[role]
    for m in media:
        if m.get("type") == "IMAGE" and m.get("url"):
            return m["url"]
    return None


_INCLUDED = frozenset(
    {"долучено", "включено", "included", "dahil", "incluido", "inclus"}
)
_BRAND_LABEL = {
    "PS_PLUS": "PS Plus",
    "EA_ACCESS": "EA Play",
    "EA_PLAY": "EA Play",
    "GTA_PLUS": "GTA+",
}
_TIERS = (
    ("deluxe", "Deluxe"),
    ("premium", "Premium"),
    ("extra", "Extra"),
    ("essential", "Essential"),
)


def _first_brand(values: Any) -> str | None:
    for item in values or []:
        if item and item != "NONE":
            return str(item)
    return None


def _included_text(text: Any) -> bool:
    if not text:
        return False
    return str(text).replace("\xa0", " ").strip().casefold() in _INCLUDED


def plus_label(branding: str | None, upsell: str | None) -> str | None:
    if not branding:
        return None
    name = _BRAND_LABEL.get(branding, branding.replace("_", " ").title())
    u = (upsell or "").casefold()
    for key, tier in _TIERS:
        if key in u:
            return f"{name} {tier}"
    return name


def parse_offer(raw: dict[str, Any], locale: str) -> Offer | None:
    product_id = raw.get("id")
    name = (raw.get("name") or "").strip()
    if not product_id or not name:
        return None
    price_raw = raw.get("price") or {}
    branding = _first_brand(price_raw.get("serviceBranding")) or _first_brand(
        price_raw.get("upsellServiceBranding")
    )
    upsell = price_raw.get("upsellText")
    tied = bool(price_raw.get("isTiedToSubscription"))
    is_free = bool(price_raw.get("isFree"))
    discount_text = price_raw.get("discountText")
    pct = parse_discount(discount_text)
    included = _included_text(price_raw.get("discountedPrice")) or _included_text(discount_text)
    plus_included = bool(
        branding
        and (
            (tied and is_free)
            or included
            or (pct == 100 and (tied or is_free))
        )
    )
    base = parse_price(price_raw.get("basePrice"))
    if plus_included:
        current = base
        is_free = False
        discount_text = None
        pct = None
    else:
        current = parse_price(price_raw.get("discountedPrice"), is_free=is_free)
    platforms = [p for p in (raw.get("platforms") or []) if p]
    return Offer(
        product_id=product_id,
        name=name,
        platforms=platforms,
        classification=raw.get("storeDisplayClassification") or "",
        cover_url=_cover(raw.get("media")),
        price=current,
        base_price=base,
        discount_text=discount_text,
        discount_percent=pct,
        is_free=is_free,
        plus_label=plus_label(branding, upsell),
        plus_included=plus_included,
        store_url=STORE_PRODUCT.format(locale=locale, product_id=product_id),
    )


def _facets(raw: list[dict[str, Any]] | None) -> dict[str, list[FacetValue]]:
    out: dict[str, list[FacetValue]] = {}
    for facet in raw or []:
        name = facet.get("name")
        if not name:
            continue
        values = [
            FacetValue(
                key=v["key"],
                name=v.get("displayName") or v["key"],
                count=int(v.get("count") or 0),
            )
            for v in facet.get("values") or []
            if v.get("key")
        ]
        if values:
            out[name] = values
    return out


class PSNClient:
    def __init__(self, locale: str = "uk-ua", delay: float = 0.3, page_size: int = 100) -> None:
        self.locale = locale
        self.delay = delay
        self.page_size = page_size
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=40, connect=15)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
                ),
                "apollographql-client-name": "Next.js (web)",
                "content-type": "application/json",
                "x-psn-store-locale-override": self.locale,
                "Accept-Language": self.locale,
            },
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("PSN client is not started")
        return self._session

    async def _get(self, operation: str, variables: dict[str, Any], sha: str) -> dict[str, Any]:
        params = urlencode(
            {
                "operationName": operation,
                "variables": json.dumps(variables, separators=(",", ":")),
                "extensions": json.dumps(
                    {"persistedQuery": {"version": 1, "sha256Hash": sha}},
                    separators=(",", ":"),
                ),
            }
        )
        url = f"{GRAPHQL_URL}?{params}"
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                async with self.session.get(url) as resp:
                    if resp.status in {429, 500, 502, 503, 504}:
                        wait = self.delay * (2 ** attempt) + 1
                        log.warning("PSN %s, retry in %.1fs", resp.status, wait)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        raise PSNError(f"HTTP {resp.status}: {body[:300]}")
                    data = await resp.json(content_type=None)
                if data.get("errors"):
                    msg = data["errors"][0].get("message", "graphql error")
                    raise PSNError(msg)
                await asyncio.sleep(self.delay)
                return data
            except (aiohttp.ClientError, asyncio.TimeoutError, PSNError) as exc:
                last_exc = exc
                wait = self.delay * (2 ** attempt) + 1
                log.warning("PSN request failed (%s), retry in %.1fs", exc, wait)
                await asyncio.sleep(wait)
        raise PSNError(f"request failed after retries: {last_exc}")

    async def category_page(
        self,
        category_id: str,
        offset: int = 0,
        size: int | None = None,
        filter_by: list[str] | None = None,
    ) -> Page:
        payload = await self._get(
            "categoryGridRetrieve",
            {
                "id": category_id,
                "pageArgs": {"size": size or self.page_size, "offset": offset},
                "sortBy": None,
                "filterBy": filter_by or [],
                "facetOptions": [],
            },
            SHA_CATEGORY_GRID,
        )
        grid = (payload.get("data") or {}).get("categoryGridRetrieve") or {}
        info = grid.get("pageInfo") or {}
        products: list[Offer] = []
        for raw in grid.get("products") or []:
            offer = parse_offer(raw, self.locale)
            if offer:
                products.append(offer)
        return Page(
            products=products,
            offset=int(info.get("offset") or offset),
            size=int(info.get("size") or len(products)),
            total=int(info.get("totalCount") or 0),
            is_last=bool(info.get("isLast", not products)),
            facets=_facets(grid.get("facetOptions")),
        )

    async def iter_category(
        self,
        category_id: str,
        filter_by: list[str] | None = None,
    ) -> AsyncIterator[Offer]:
        offset = 0
        seen = 0
        safety = 0
        while True:
            page = await self.category_page(category_id, offset=offset, filter_by=filter_by)
            if not page.products:
                break
            for offer in page.products:
                yield offer
            seen += len(page.products)
            safety += 1
            if page.is_last or seen >= page.total:
                break
            if safety > 500:
                log.error("category %s pagination safety stop at offset %s", category_id, offset)
                break
            offset = page.offset + page.size

    async def genre_facets(self) -> list[FacetValue]:
        page = await self.category_page(CAT_PS4, offset=0, size=24)
        return page.facets.get("productGenres") or []
