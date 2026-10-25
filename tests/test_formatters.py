from bot.formatters import change_line, channel_caption, game_card


def test_sale_card() -> None:
    html = game_card(
        {
            "name": "Ginga Force",
            "platforms": ["PS4"],
            "genres": [{"genre_name": "Экшен"}],
            "current_price": 6490,
            "base_price": 64900,
            "discount_percent": 90,
            "store_url": "https://store.playstation.com/uk-ua/product/X",
        },
        watching=False,
    )
    assert "<b>Ginga Force</b>" in html
    assert "PS4" in html
    assert "Экшен" in html
    assert "−90%" in html
    assert "<s>649 ₴</s>" in html
    assert "64,90 ₴" in html
    assert "выгода" in html
    assert "blockquote" in html
    assert "playstation.com" not in html


def test_plus_included_card() -> None:
    html = game_card(
        {
            "name": "DOOM (1993)",
            "platforms": ["PS4"],
            "current_price": 329900,
            "base_price": 329900,
            "plus_label": "PS Plus Deluxe",
            "plus_included": 1,
            "discount_percent": None,
        },
        watching=False,
    )
    assert "PS Plus Deluxe — в подписке" in html
    assert "−100%" not in html
    assert "3 299 ₴" in html
    assert "выгода" not in html


def test_channel_line_links_to_store() -> None:
    html = change_line(
        {
            "kind": "change",
            "name": "DOOM (1993)",
            "product_id": "EP1003-CUSA02092_00-DOOM1993",
            "store_url": "https://store.playstation.com/uk-ua/product/EP1003-CUSA02092_00-DOOM1993",
            "old_price": 329900,
            "new_price": 12980,
            "new_discount": "-80%",
        }
    )
    assert 'href="https://store.playstation.com/uk-ua/product/EP1003-CUSA02092_00-DOOM1993"' in html
    assert "DOOM (1993)" in html


def test_channel_caption_new_game() -> None:
    html = channel_caption(
        {"kind": "new", "new_price": 64900},
        {
            "name": "Ginga Force",
            "platforms": ["PS4"],
            "current_price": 64900,
            "base_price": 64900,
            "cover_url": "https://example.com/cover.jpg",
            "store_url": "https://store.playstation.com/uk-ua/product/X",
        },
    )
    assert "Новая игра" in html
    assert "Ginga Force" in html
    assert "649 ₴" in html


def test_channel_caption_has_drop_and_history() -> None:
    html = channel_caption(
        {
            "kind": "change",
            "old_price": 64900,
            "new_price": 6490,
            "new_discount": "-90%",
        },
        {
            "name": "Ginga Force",
            "platforms": ["PS4"],
            "genres": [{"genre_name": "Экшен"}],
            "current_price": 6490,
            "base_price": 64900,
            "discount_percent": 90,
        },
        history=[
            {"price": 6490, "discount_text": "-90%", "recorded_at": "2026-10-24T13:00:00+00:00"},
            {"price": 64900, "discount_text": None, "recorded_at": "2026-09-01T10:00:00+00:00"},
        ],
    )
    assert "Цена упала" in html
    assert "Ginga Force" in html
    assert "64,90 ₴" in html
    assert "История цен" in html
    assert "мин" in html
    assert len(html) <= 1024


def test_watch_and_history() -> None:
    html = game_card(
        {
            "name": "Game",
            "platforms": ["PS5"],
            "current_price": 10000,
            "base_price": 10000,
        },
        watching=True,
        history=[
            {"price": 10000, "discount_text": None, "recorded_at": "2026-10-24T13:00:00+00:00"},
            {"price": 20000, "discount_text": "-50%", "recorded_at": "2026-09-01T10:00:00+00:00"},
            {"price": 25000, "discount_text": None, "recorded_at": "2026-08-15T10:00:00+00:00"},
        ],
    )
    assert "★ в списке" in html
    assert "История цен" in html
    assert "100 ₴" in html
    assert "200 ₴" in html
    assert "-50%" in html
    assert "мин 100 ₴" in html
    assert "макс 250 ₴" in html
    assert "24.10.26" in html
