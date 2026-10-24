from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ints(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return tuple(out)


@dataclass(slots=True)
class Config:
    token: str
    channel_id: int | None
    admin_ids: tuple[int, ...]
    locale: str
    page_size: int
    request_delay: float
    cycle_pause: float
    genre_every: int
    db_path: Path
    log_path: Path

    @classmethod
    def from_env(cls) -> Config:
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env")
        channel_raw = os.getenv("CHANNEL_ID", "").strip()
        channel_id = int(channel_raw) if channel_raw else None
        data_dir = ROOT / "data"
        return cls(
            token=token,
            channel_id=channel_id,
            admin_ids=_ints(os.getenv("ADMIN_IDS", "")),
            locale=os.getenv("LOCALE", "uk-ua").strip() or "uk-ua",
            page_size=max(1, min(int(os.getenv("PAGE_SIZE", "100")), 100)),
            request_delay=float(os.getenv("REQUEST_DELAY", "2")),
            cycle_pause=float(os.getenv("CYCLE_PAUSE", "7200")),
            genre_every=max(1, int(os.getenv("GENRE_EVERY", "6"))),
            db_path=data_dir / "psn.sqlite3",
            log_path=data_dir / "bot.log",
        )
