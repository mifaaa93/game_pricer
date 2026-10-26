import pytest

from bot.db import Database
from bot.psn import Offer


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    await database.connect()
    yield database
    await database.close()


def _offer(pid: str, price: int, **kwargs) -> Offer:
    return Offer(
        product_id=pid,
        name=kwargs.get("name", "God of War"),
        platforms=kwargs.get("platforms", ["PS4"]),
        classification="FULL_GAME",
        cover_url=None,
        price=price,
        base_price=kwargs.get("base_price", 69900),
        discount_text=kwargs.get("discount_text"),
        discount_percent=kwargs.get("discount_percent"),
        is_free=price == 0,
        plus_label=kwargs.get("plus_label"),
        plus_included=kwargs.get("plus_included", False),
        store_url="https://store.playstation.com/uk-ua/product/" + pid,
    )


@pytest.mark.asyncio
async def test_purge_demos(db: Database) -> None:
    await db.apply_offer(_offer("A", 0, name="Fracked Demo"), notify=False)
    await db.apply_offer(_offer("B", 10000, name="God of War"), notify=False)
    n = await db.purge_demos()
    assert n == 1
    assert await db.get_game("A") is None
    assert await db.get_game("B") is not None


@pytest.mark.asyncio
async def test_seed_has_history_without_event(db: Database) -> None:
    event = await db.apply_offer(_offer("A", 69900), notify=False)
    assert event is None
    game = await db.get_game("A")
    assert game["current_price"] == 69900
    hist = await db.history("A")
    assert len(hist) == 1
    pending = await db.pending_events("notified_channel")
    assert pending == []


@pytest.mark.asyncio
async def test_price_drop_creates_event(db: Database) -> None:
    await db.apply_offer(_offer("A", 69900), notify=False)
    event = await db.apply_offer(_offer("A", 34900, discount_text="-50%", discount_percent=50), notify=True)
    assert event is not None
    assert event["kind"] == "change"
    assert event["old_price"] == 69900
    assert event["new_price"] == 34900
    hist = await db.history("A")
    assert len(hist) == 2
    pending = await db.pending_events("notified_channel")
    assert len(pending) == 1
    many = await db.history_many(["A", "missing"], limit=10)
    assert len(many["A"]) == 2
    assert many["missing"] == []


@pytest.mark.asyncio
async def test_sale_start_same_base_creates_drop(db: Database) -> None:
    await db.apply_offer(_offer("A", 64900, base_price=64900, name="GoW"), notify=False)
    event = await db.apply_offer(
        _offer("A", 6490, base_price=64900, discount_text="-90%", discount_percent=90, name="GoW"),
        notify=True,
    )
    assert event is not None
    assert event["old_price"] == 64900
    assert event["new_price"] == 6490


@pytest.mark.asyncio
async def test_discount_text_only_does_not_notify(db: Database) -> None:
    await db.apply_offer(_offer("A", 0, base_price=0, discount_text="foo"), notify=False)
    event = await db.apply_offer(_offer("A", 0, base_price=0, discount_text="bar"), notify=True)
    assert event is None


@pytest.mark.asyncio
async def test_same_price_no_event(db: Database) -> None:
    await db.apply_offer(_offer("A", 69900), notify=True)
    event = await db.apply_offer(_offer("A", 69900), notify=True)
    assert event is None
    assert len(await db.history("A")) == 1


@pytest.mark.asyncio
async def test_browse_genre_and_watch(db: Database) -> None:
    await db.apply_offer(_offer("A", 10000, name="Alpha"), notify=False)
    await db.apply_offer(_offer("B", 20000, name="Beta", platforms=["PS5"]), notify=False)
    await db.add_genre("A", "ACTION", "Экшен")
    await db.add_genre("B", "ACTION", "Экшен")
    games, total = await db.browse("PS4", "ACTION", 0)
    assert total == 1
    assert games[0]["product_id"] == "A"
    await db.upsert_user(1, "u", "U")
    assert await db.toggle_watch(1, "A") is True
    assert await db.is_watching(1, "A")
    assert await db.watchers("A") == [1]
    assert await db.genre_keys() == {"ACTION"}
    await db.apply_offer(_offer("C", 15000, name="Charlie"), notify=False)
    await db.add_genre("C", "ACTION", "Экшен")
    pid, total = await db.browse_at("PS4", "ACTION", 1)
    assert total == 2
    assert pid in {"A", "C"}
    await db.toggle_watch(1, "C")
    wid, wtotal = await db.watch_at(1, 0)
    assert wtotal == 2
    assert wid in {"A", "C"}


@pytest.mark.asyncio
async def test_sale_sort_percent_and_amount(db: Database) -> None:
    await db.apply_offer(
        _offer("A", 5000, base_price=10000, discount_text="-50%", discount_percent=50, name="Small"),
        notify=False,
    )
    await db.apply_offer(
        _offer("B", 40000, base_price=50000, discount_text="-20%", discount_percent=20, name="Big"),
        notify=False,
    )
    by_pct, _ = await db.browse("PS4", "SALE", 0, sale_sort="pct")
    assert [g["product_id"] for g in by_pct] == ["A", "B"]
    by_amt, _ = await db.browse("PS4", "SALE", 0, sale_sort="amt")
    assert [g["product_id"] for g in by_amt] == ["B", "A"]


@pytest.mark.asyncio
async def test_browse_sale_skips_plus_catalog(db: Database) -> None:
    await db.apply_offer(
        _offer("A", 5000, base_price=10000, discount_text="-50%", discount_percent=50, name="Sale"),
        notify=False,
    )
    await db.apply_offer(
        _offer(
            "B",
            329900,
            base_price=329900,
            name="DOOM",
            plus_label="PS Plus Deluxe",
            plus_included=True,
        ),
        notify=False,
    )
    games, total = await db.browse("PS4", "SALE", 0)
    assert total == 1
    assert games[0]["product_id"] == "A"


@pytest.mark.asyncio
async def test_plus_correction_does_not_notify(db: Database) -> None:
    await db.apply_offer(
        _offer("A", 0, base_price=0, discount_text="-100%", discount_percent=100, name="DOOM"),
        notify=False,
    )
    event = await db.apply_offer(
        _offer(
            "A",
            329900,
            base_price=329900,
            name="DOOM",
            plus_label="PS Plus Deluxe",
            plus_included=True,
        ),
        notify=True,
    )
    assert event is None
    assert await db.pending_events("notified_channel") == []
    game = await db.get_game("A")
    assert game["current_price"] == 329900
    assert game["plus_included"] == 1


@pytest.mark.asyncio
async def test_search(db: Database) -> None:
    await db.apply_offer(_offer("A", 10000, name="The Last of Us Remastered"), notify=False)
    found = await db.search("last of us")
    assert found and found[0]["product_id"] == "A"
    assert "PS4" in found[0]["platforms"]


@pytest.mark.asyncio
async def test_search_short_query_shows_deals(db: Database) -> None:
    await db.apply_offer(
        _offer("A", 5000, base_price=10000, discount_text="-50%", discount_percent=50, name="Sale Game"),
        notify=False,
    )
    await db.apply_offer(_offer("B", 10000, name="Full Price"), notify=False)
    found = await db.search("")
    assert [g["product_id"] for g in found] == ["A"]


@pytest.mark.asyncio
async def test_search_offset(db: Database) -> None:
    await db.apply_offer(_offer("A", 10000, name="Alpha Quest"), notify=False)
    await db.apply_offer(_offer("B", 10000, name="Alpha Run"), notify=False)
    page1 = await db.search("alpha", limit=1, offset=0)
    page2 = await db.search("alpha", limit=1, offset=1)
    assert page1[0]["product_id"] != page2[0]["product_id"]
