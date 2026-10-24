from bot.price import format_price, parse_discount, parse_price


def test_parse_uah_simple() -> None:
    assert parse_price("UAH 329,00") == 32900


def test_parse_uah_thousands() -> None:
    assert parse_price("UAH 2 499,00") == 249900
    assert parse_price("UAH\u00a02 499,00") == 249900


def test_parse_uah_kopecks() -> None:
    assert parse_price("UAH 249,90") == 24990
    assert parse_price("UAH 843,80") == 84380


def test_parse_free() -> None:
    assert parse_price("Безкоштовно") == 0
    assert parse_price("anything", is_free=True) == 0


def test_parse_empty() -> None:
    assert parse_price(None) is None
    assert parse_price("") is None


def test_discount() -> None:
    assert parse_discount("-90%") == 90
    assert parse_discount("−50%") == 50
    assert parse_discount(None) is None


def test_format() -> None:
    assert format_price(0) == "бесплатно"
    assert format_price(32900) == "329 ₴"
    assert format_price(24990) == "249,90 ₴"
    assert format_price(249900) == "2 499 ₴"
    assert format_price(None) == "н/д"
