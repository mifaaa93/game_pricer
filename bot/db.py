from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from .psn import Offer, is_demo

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_search TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT '',
    cover_url TEXT,
    store_url TEXT,
    current_price INTEGER,
    base_price INTEGER,
    discount_text TEXT,
    discount_percent INTEGER,
    is_free INTEGER NOT NULL DEFAULT 0,
    plus_label TEXT,
    plus_included INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'UAH',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_platforms (
    product_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    PRIMARY KEY (product_id, platform),
    FOREIGN KEY (product_id) REFERENCES games(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_genres (
    product_id TEXT NOT NULL,
    genre_key TEXT NOT NULL,
    genre_name TEXT NOT NULL,
    PRIMARY KEY (product_id, genre_key),
    FOREIGN KEY (product_id) REFERENCES games(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    price INTEGER,
    base_price INTEGER,
    discount_text TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES games(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS price_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    old_price INTEGER,
    new_price INTEGER,
    old_base INTEGER,
    new_base INTEGER,
    old_discount TEXT,
    new_discount TEXT,
    created_at TEXT NOT NULL,
    notified_channel INTEGER NOT NULL DEFAULT 0,
    notified_users INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES games(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watches (
    user_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES games(product_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_games_search ON games(name_search);
CREATE INDEX IF NOT EXISTS idx_games_discount ON games(discount_percent);
CREATE INDEX IF NOT EXISTS idx_history_product ON price_history(product_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_events_channel ON price_events(notified_channel, id);
CREATE INDEX IF NOT EXISTS idx_events_users ON price_events(notified_users, id);
CREATE INDEX IF NOT EXISTS idx_watches_product ON watches(product_id);
CREATE INDEX IF NOT EXISTS idx_platforms_platform ON game_platforms(platform);
CREATE INDEX IF NOT EXISTS idx_genres_key ON game_genres(genre_key);

CREATE TABLE IF NOT EXISTS media_cache (
    key TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

PAGE = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _normalize_game(game: dict[str, Any]) -> dict[str, Any]:
    csv = game.pop("platforms_csv", None)
    if not isinstance(game.get("platforms"), list):
        game["platforms"] = [p for p in str(csv or "").split(",") if p]
    game.setdefault("genres", [])
    return game


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected")
        return self._db

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.executescript(SCHEMA)
        await self._migrate()
        await self.purge_demos()
        await self.db.commit()

    async def _migrate(self) -> None:
        cur = await self.db.execute("PRAGMA table_info(games)")
        cols = {r[1] for r in await cur.fetchall()}
        if "plus_label" not in cols:
            await self.db.execute("ALTER TABLE games ADD COLUMN plus_label TEXT")
        if "plus_included" not in cols:
            await self.db.execute(
                "ALTER TABLE games ADD COLUMN plus_included INTEGER NOT NULL DEFAULT 0"
            )

    async def purge_demos(self) -> int:
        cur = await self.db.execute("SELECT product_id, name, classification FROM games")
        ids = [row[0] for row in await cur.fetchall() if is_demo(row[2], row[1])]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        await self.db.execute(f"DELETE FROM games WHERE product_id IN ({placeholders})", ids)
        return len(ids)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get_media(self, key: str) -> str | None:
        cur = await self.db.execute("SELECT file_id FROM media_cache WHERE key=?", (key,))
        row = await cur.fetchone()
        return str(row[0]) if row else None

    async def set_media(self, key: str, file_id: str) -> None:
        async with self._lock:
            await self.db.execute(
                """
                INSERT INTO media_cache (key, file_id, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id, updated_at=excluded.updated_at
                """,
                (key, file_id, _now()),
            )
            await self.db.commit()

    async def drop_media(self, key: str) -> None:
        async with self._lock:
            await self.db.execute("DELETE FROM media_cache WHERE key=?", (key,))
            await self.db.commit()

    async def games_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) FROM games")
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def genre_keys(self) -> set[str]:
        cur = await self.db.execute("SELECT DISTINCT genre_key FROM game_genres")
        return {str(r[0]) for r in await cur.fetchall()}

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        now = _now()
        async with self._lock:
            await self.db.execute(
                """
                INSERT INTO users (user_id, username, first_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    is_active=1,
                    updated_at=excluded.updated_at
                """,
                (user_id, username, first_name, now, now),
            )
            await self.db.commit()

    async def set_user_active(self, user_id: int, is_active: bool) -> None:
        async with self._lock:
            await self.db.execute(
                "UPDATE users SET is_active=?, updated_at=? WHERE user_id=?",
                (1 if is_active else 0, _now(), user_id),
            )
            await self.db.commit()

    async def apply_offer(self, offer: Offer, notify: bool = True) -> dict[str, Any] | None:
        """Insert or update a game. Returns a price_event payload when the price changed."""
        now = _now()
        async with self._lock:
            cur = await self.db.execute(
                "SELECT current_price, base_price, discount_text FROM games WHERE product_id=?",
                (offer.product_id,),
            )
            prev = await cur.fetchone()
            is_new = prev is None
            changed = False
            if prev is not None:
                changed = (
                    prev["current_price"] != offer.price
                    or prev["base_price"] != offer.base_price
                    or (prev["discount_text"] or "") != (offer.discount_text or "")
                )
            await self.db.execute(
                """
                INSERT INTO games (
                    product_id, name, name_search, classification, cover_url, store_url,
                    current_price, base_price, discount_text, discount_percent, is_free,
                    plus_label, plus_included,
                    currency, first_seen_at, last_seen_at, last_changed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    name=excluded.name,
                    name_search=excluded.name_search,
                    classification=excluded.classification,
                    cover_url=COALESCE(excluded.cover_url, games.cover_url),
                    store_url=excluded.store_url,
                    current_price=excluded.current_price,
                    base_price=excluded.base_price,
                    discount_text=excluded.discount_text,
                    discount_percent=excluded.discount_percent,
                    is_free=excluded.is_free,
                    plus_label=excluded.plus_label,
                    plus_included=excluded.plus_included,
                    currency=excluded.currency,
                    last_seen_at=excluded.last_seen_at,
                    last_changed_at=CASE WHEN excluded.current_price IS games.current_price
                        AND excluded.base_price IS games.base_price
                        AND COALESCE(excluded.discount_text,'') = COALESCE(games.discount_text,'')
                        THEN games.last_changed_at ELSE excluded.last_changed_at END,
                    updated_at=excluded.updated_at
                """,
                (
                    offer.product_id,
                    offer.name,
                    offer.name.casefold(),
                    offer.classification,
                    offer.cover_url,
                    offer.store_url,
                    offer.price,
                    offer.base_price,
                    offer.discount_text,
                    offer.discount_percent,
                    1 if offer.is_free else 0,
                    offer.plus_label,
                    1 if offer.plus_included else 0,
                    offer.currency,
                    now,
                    now,
                    now if is_new or changed else None,
                    now,
                ),
            )
            for platform in offer.platforms:
                await self.db.execute(
                    "INSERT OR IGNORE INTO game_platforms (product_id, platform) VALUES (?, ?)",
                    (offer.product_id, platform),
                )
            event: dict[str, Any] | None = None
            if (
                notify
                and changed
                and offer.plus_included
                and prev is not None
                and prev["current_price"] == 0
                and offer.price == offer.base_price
            ):
                notify = False
            if is_new or changed:
                await self.db.execute(
                    """
                    INSERT INTO price_history (product_id, price, base_price, discount_text, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (offer.product_id, offer.price, offer.base_price, offer.discount_text, now),
                )
            if notify and (is_new or changed):
                kind = "new" if is_new else "change"
                old_price = None if is_new else prev["current_price"]
                old_base = None if is_new else prev["base_price"]
                old_discount = None if is_new else prev["discount_text"]
                await self.db.execute(
                    """
                    INSERT INTO price_events (
                        product_id, kind, old_price, new_price, old_base, new_base,
                        old_discount, new_discount, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        offer.product_id,
                        kind,
                        old_price,
                        offer.price,
                        old_base,
                        offer.base_price,
                        old_discount,
                        offer.discount_text,
                        now,
                    ),
                )
                event = {
                    "product_id": offer.product_id,
                    "kind": kind,
                    "old_price": old_price,
                    "new_price": offer.price,
                    "old_base": old_base,
                    "new_base": offer.base_price,
                    "old_discount": old_discount,
                    "new_discount": offer.discount_text,
                    "name": offer.name,
                    "cover_url": offer.cover_url,
                    "store_url": offer.store_url,
                    "platforms": offer.platforms,
                }
            await self.db.commit()
            return event

    async def add_genre(self, product_id: str, genre_key: str, genre_name: str) -> None:
        async with self._lock:
            await self.db.execute(
                """
                INSERT INTO game_genres (product_id, genre_key, genre_name)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id, genre_key) DO UPDATE SET genre_name=excluded.genre_name
                """,
                (product_id, genre_key, genre_name),
            )
            await self.db.commit()

    async def add_genres_bulk(self, product_ids: Iterable[str], genre_key: str, genre_name: str) -> None:
        rows = [(pid, genre_key, genre_name) for pid in product_ids]
        if not rows:
            return
        async with self._lock:
            await self.db.executemany(
                """
                INSERT INTO game_genres (product_id, genre_key, genre_name)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id, genre_key) DO UPDATE SET genre_name=excluded.genre_name
                """,
                rows,
            )
            await self.db.commit()

    def _platform_join(self, platform: str | None) -> tuple[str, list[Any]]:
        if not platform or platform == "all":
            return "", []
        return (
            "JOIN game_platforms gp ON gp.product_id = g.product_id AND gp.platform = ?",
            [platform],
        )

    async def list_genres(self, platform: str | None) -> list[dict[str, Any]]:
        join, args = self._platform_join(platform)
        sql = f"""
            SELECT gg.genre_key AS genre_key, gg.genre_name AS genre_name, COUNT(DISTINCT g.product_id) AS n
            FROM game_genres gg
            JOIN games g ON g.product_id = gg.product_id
            {join}
            WHERE g.classification NOT IN ('DEMO', 'SOUNDTRACK', 'GAME_APPLICATION')
            GROUP BY gg.genre_key
            ORDER BY n DESC, gg.genre_name
        """
        cur = await self.db.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]

    def _browse_parts(
        self, platform: str | None, genre: str, sale_sort: str = "pct"
    ) -> tuple[str, str, list[Any], str]:
        join, args = self._platform_join(platform)
        where = ["g.classification NOT IN ('DEMO', 'SOUNDTRACK', 'GAME_APPLICATION')"]
        if genre == "SALE":
            where.append("g.discount_percent IS NOT NULL AND g.discount_percent > 0")
            where.append("COALESCE(g.plus_included, 0) = 0")
            amount = "(COALESCE(g.base_price, 0) - COALESCE(g.current_price, 0))"
            if sale_sort == "amt":
                order = f"{amount} DESC, g.discount_percent DESC, g.name"
            else:
                order = f"g.discount_percent DESC, {amount} DESC, g.name"
        elif genre and genre not in {"ALL", "*"}:
            join += " JOIN game_genres gg ON gg.product_id = g.product_id AND gg.genre_key = ?"
            args.append(genre)
            order = "g.name"
        else:
            order = "g.name"
        return join, " AND ".join(where), args, order

    async def browse(
        self,
        platform: str | None,
        genre: str,
        page: int,
        per_page: int = PAGE,
        sale_sort: str = "pct",
    ) -> tuple[list[dict[str, Any]], int]:
        join, where_sql, args, order = self._browse_parts(platform, genre, sale_sort)
        count_sql = f"SELECT COUNT(DISTINCT g.product_id) FROM games g {join} WHERE {where_sql}"
        cur = await self.db.execute(count_sql, args)
        total = int((await cur.fetchone())[0])
        offset = max(page, 0) * per_page
        list_sql = f"""
            SELECT g.* FROM games g
            {join}
            WHERE {where_sql}
            GROUP BY g.product_id
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """
        cur = await self.db.execute(list_sql, [*args, per_page, offset])
        return [dict(r) for r in await cur.fetchall()], total

    async def browse_at(
        self, platform: str | None, genre: str, index: int, sale_sort: str = "pct"
    ) -> tuple[str | None, int]:
        join, where_sql, args, order = self._browse_parts(platform, genre, sale_sort)
        cur = await self.db.execute(
            f"SELECT COUNT(DISTINCT g.product_id) FROM games g {join} WHERE {where_sql}",
            args,
        )
        total = int((await cur.fetchone())[0])
        if total <= 0:
            return None, 0
        index = max(0, min(index, total - 1))
        cur = await self.db.execute(
            f"""
            SELECT g.product_id FROM games g
            {join}
            WHERE {where_sql}
            GROUP BY g.product_id
            ORDER BY {order}
            LIMIT 1 OFFSET ?
            """,
            [*args, index],
        )
        row = await cur.fetchone()
        return (str(row[0]) if row else None), total

    async def watch_at(self, user_id: int, index: int) -> tuple[str | None, int]:
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM watches WHERE user_id=?", (user_id,)
        )
        total = int((await cur.fetchone())[0])
        if total <= 0:
            return None, 0
        index = max(0, min(index, total - 1))
        cur = await self.db.execute(
            """
            SELECT g.product_id FROM watches w
            JOIN games g ON g.product_id = w.product_id
            WHERE w.user_id=?
            ORDER BY g.name
            LIMIT 1 OFFSET ?
            """,
            (user_id, index),
        )
        row = await cur.fetchone()
        return (str(row[0]) if row else None), total

    async def search(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        q = query.strip().casefold()
        offset = max(offset, 0)
        select = """
            SELECT g.*,
                (SELECT GROUP_CONCAT(platform)
                 FROM game_platforms gp WHERE gp.product_id = g.product_id) AS platforms_csv
            FROM games g
        """
        if len(q) < 2:
            cur = await self.db.execute(
                select
                + """
                WHERE g.discount_percent IS NOT NULL AND g.discount_percent > 0
                  AND COALESCE(g.plus_included, 0) = 0
                  AND g.classification NOT IN ('DEMO', 'SOUNDTRACK', 'GAME_APPLICATION')
                ORDER BY g.discount_percent DESC, g.name
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        else:
            cur = await self.db.execute(
                select
                + """
                WHERE g.name_search LIKE ?
                ORDER BY
                    CASE WHEN g.name_search LIKE ? THEN 0 ELSE 1 END,
                    CASE WHEN g.discount_percent IS NOT NULL THEN 0 ELSE 1 END,
                    g.name
                LIMIT ? OFFSET ?
                """,
                (f"%{q}%", f"{q}%", limit, offset),
            )
        return [_normalize_game(dict(r)) for r in await cur.fetchall()]

    async def get_game(self, product_id: str) -> dict[str, Any] | None:
        cur = await self.db.execute("SELECT * FROM games WHERE product_id=?", (product_id,))
        game = _row(await cur.fetchone())
        if not game:
            return None
        cur = await self.db.execute(
            "SELECT platform FROM game_platforms WHERE product_id=? ORDER BY platform",
            (product_id,),
        )
        game["platforms"] = [r[0] for r in await cur.fetchall()]
        cur = await self.db.execute(
            "SELECT genre_key, genre_name FROM game_genres WHERE product_id=? ORDER BY genre_name",
            (product_id,),
        )
        game["genres"] = [dict(r) for r in await cur.fetchall()]
        return game

    async def history(self, product_id: str, limit: int = 10) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT price, base_price, discount_text, recorded_at
            FROM price_history
            WHERE product_id=?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (product_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def history_many(
        self, product_ids: list[str], limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        if not product_ids:
            return {}
        placeholders = ",".join("?" * len(product_ids))
        cur = await self.db.execute(
            f"""
            SELECT product_id, price, base_price, discount_text, recorded_at
            FROM (
                SELECT product_id, price, base_price, discount_text, recorded_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY product_id ORDER BY recorded_at DESC
                       ) AS rn
                FROM price_history
                WHERE product_id IN ({placeholders})
            )
            WHERE rn <= ?
            ORDER BY recorded_at DESC
            """,
            (*product_ids, limit),
        )
        out: dict[str, list[dict[str, Any]]] = {pid: [] for pid in product_ids}
        for row in await cur.fetchall():
            item = dict(row)
            out[item["product_id"]].append(item)
        return out

    async def is_watching(self, user_id: int, product_id: str) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM watches WHERE user_id=? AND product_id=?",
            (user_id, product_id),
        )
        return await cur.fetchone() is not None

    async def watching_ids(self, user_id: int, product_ids: list[str]) -> set[str]:
        if not product_ids:
            return set()
        placeholders = ",".join("?" * len(product_ids))
        cur = await self.db.execute(
            f"SELECT product_id FROM watches WHERE user_id=? AND product_id IN ({placeholders})",
            (user_id, *product_ids),
        )
        return {str(r[0]) for r in await cur.fetchall()}

    async def toggle_watch(self, user_id: int, product_id: str) -> bool:
        async with self._lock:
            cur = await self.db.execute(
                "SELECT 1 FROM watches WHERE user_id=? AND product_id=?",
                (user_id, product_id),
            )
            exists = await cur.fetchone() is not None
            if exists:
                await self.db.execute(
                    "DELETE FROM watches WHERE user_id=? AND product_id=?",
                    (user_id, product_id),
                )
                watching = False
            else:
                await self.db.execute(
                    "INSERT INTO watches (user_id, product_id, created_at) VALUES (?, ?, ?)",
                    (user_id, product_id, _now()),
                )
                watching = True
            await self.db.commit()
            return watching

    async def user_watches(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT g.* FROM watches w
            JOIN games g ON g.product_id = w.product_id
            WHERE w.user_id=?
            ORDER BY g.name
            """,
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def watchers(self, product_id: str) -> list[int]:
        cur = await self.db.execute(
            """
            SELECT w.user_id FROM watches w
            JOIN users u ON u.user_id = w.user_id
            WHERE w.product_id=? AND u.is_active=1
            """,
            (product_id,),
        )
        return [int(r[0]) for r in await cur.fetchall()]

    async def pending_events(self, field: str, limit: int = 200) -> list[dict[str, Any]]:
        if field not in {"notified_channel", "notified_users"}:
            raise ValueError(field)
        cur = await self.db.execute(
            f"""
            SELECT e.*, g.name, g.cover_url, g.store_url, g.discount_percent
            FROM price_events e
            JOIN games g ON g.product_id = e.product_id
            WHERE e.{field}=0
            ORDER BY e.id
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def mark_events(self, ids: list[int], field: str) -> None:
        if not ids:
            return
        if field not in {"notified_channel", "notified_users"}:
            raise ValueError(field)
        async with self._lock:
            await self.db.execute(
                f"UPDATE price_events SET {field}=1 WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            await self.db.commit()

    async def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for key, sql in {
            "games": "SELECT COUNT(*) FROM games",
            "ps4": "SELECT COUNT(*) FROM game_platforms WHERE platform='PS4'",
            "ps5": "SELECT COUNT(*) FROM game_platforms WHERE platform='PS5'",
            "on_sale": (
                "SELECT COUNT(*) FROM games "
                "WHERE discount_percent IS NOT NULL AND discount_percent > 0 "
                "AND COALESCE(plus_included, 0) = 0"
            ),
            "watches": "SELECT COUNT(*) FROM watches",
            "users": "SELECT COUNT(*) FROM users",
            "history": "SELECT COUNT(*) FROM price_history",
        }.items():
            cur = await self.db.execute(sql)
            out[key] = int((await cur.fetchone())[0])
        return out
