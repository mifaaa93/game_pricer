from __future__ import annotations

import asyncio
import logging

from .config import Config
from .db import Database
from .genres import genre_label
from .psn import CATEGORIES, PSNClient

log = logging.getLogger(__name__)


class Collector:
    def __init__(self, db: Database, psn: PSNClient, config: Config) -> None:
        self.db = db
        self.psn = psn
        self.config = config
        self._stop = asyncio.Event()
        self._cycle_n = 0

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("collector cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.config.cycle_pause)
            except asyncio.TimeoutError:
                pass

    async def run_cycle(self) -> dict[str, int]:
        self._cycle_n += 1
        seeded = await self.db.games_count() == 0
        notify = not seeded
        if seeded:
            log.info("empty catalog — first cycle only fills the database, no notifications")
        stats = {"offers": 0, "events": 0}
        for platform, category_id in CATEGORIES:
            log.info("crawl %s catalog", platform)
            n = 0
            async for offer in self.psn.iter_category(category_id):
                event = await self.db.apply_offer(offer, notify=notify)
                n += 1
                stats["offers"] += 1
                if event:
                    stats["events"] += 1
                if n % 500 == 0:
                    log.info("%s: %s games processed", platform, n)
                if self._stop.is_set():
                    break
            log.info("%s: %s games", platform, n)
            if self._stop.is_set():
                break
        tag_genres = (
            seeded
            or not await self.db.has_genres()
            or self._cycle_n % self.config.genre_every == 0
        )
        if tag_genres:
            await self._tag_genres(notify=notify)
        else:
            log.info("skip genre pass (every %s cycles)", self.config.genre_every)
        log.info(
            "cycle %s done offers=%s events=%s seed=%s",
            self._cycle_n,
            stats["offers"],
            stats["events"],
            seeded,
        )
        return stats

    async def _tag_genres(self, notify: bool) -> None:
        try:
            facets = await self.psn.genre_facets()
        except Exception:
            log.exception("failed to load genre facets")
            return
        log.info("tagging %s genres", len(facets))
        tagged = 0
        for facet in facets:
            label = genre_label(facet.key, facet.name)
            ids: list[str] = []
            for _platform, category_id in CATEGORIES:
                if self._stop.is_set():
                    return
                async for offer in self.psn.iter_category(
                    category_id, filter_by=[f"productGenres:{facet.key}"]
                ):
                    await self.db.apply_offer(offer, notify=notify)
                    ids.append(offer.product_id)
            if ids:
                await self.db.add_genres_bulk(ids, facet.key, label)
                tagged += len(ids)
            log.info("genre %s (%s): %s games", facet.key, label, len(ids))
        log.info("genre tags written: %s", tagged)
