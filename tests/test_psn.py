from bot.psn import is_demo, parse_offer, thumb_url


SAMPLE = {
    "id": "EP9000-CUSA10249_00-THELASTOFUSPART2",
    "name": "The Last of Us Part II",
    "platforms": ["PS4"],
    "storeDisplayClassification": "FULL_GAME",
    "media": [
        {
            "role": "GAMEHUB_COVER_ART",
            "type": "IMAGE",
            "url": "https://example.com/cover.jpg",
        }
    ],
    "price": {
        "basePrice": "UAH 1 749,00",
        "discountText": "-50%",
        "discountedPrice": "UAH 874,50",
        "isFree": False,
    },
}


def test_parse_offer() -> None:
    offer = parse_offer(SAMPLE, "uk-ua")
    assert offer is not None
    assert offer.product_id.endswith("THELASTOFUSPART2")
    assert offer.price == 87450
    assert offer.base_price == 174900
    assert offer.discount_percent == 50
    assert offer.cover_url.endswith("cover.jpg")
    assert "uk-ua/product/" in offer.store_url
    assert offer.plus_included is False


def test_is_demo() -> None:
    assert is_demo("DEMO", "Fracked Demo")
    assert is_demo("FULL_GAME", "Tormented Souls Demo")
    assert is_demo("GAME_BUNDLE", "Демо-версія Bramble: The Mountain King")
    assert is_demo("GAME_BUNDLE", "Tales of Arise Demo Version")
    assert not is_demo("FULL_GAME", "Demonschool")
    assert not is_demo("FULL_GAME", "Democracy 4: Console Edition")
    assert not is_demo("FULL_GAME", "The Last of Us")


def test_parse_skips_demo() -> None:
    raw = {
        "id": "EP0000-CUSA00000_00-DEMO",
        "name": "Fracked Demo",
        "platforms": ["PS4"],
        "storeDisplayClassification": "DEMO",
        "price": {"basePrice": "Безкоштовно", "discountedPrice": "Безкоштовно", "isFree": True},
    }
    assert parse_offer(raw, "uk-ua") is None


def test_parse_plus_catalog_not_a_sale() -> None:
    raw = {
        "id": "UP0000-CUSA00000_00-DOOM1993",
        "name": "DOOM (1993)",
        "platforms": ["PS4"],
        "storeDisplayClassification": "FULL_GAME",
        "price": {
            "basePrice": "UAH 3 299,00",
            "discountText": "-100%",
            "discountedPrice": "Долучено",
            "isExclusive": True,
            "isFree": True,
            "isTiedToSubscription": True,
            "serviceBranding": ["PS_PLUS"],
            "upsellServiceBranding": ["PS_PLUS"],
            "upsellText": "Deluxe",
        },
    }
    offer = parse_offer(raw, "uk-ua")
    assert offer is not None
    assert offer.plus_included is True
    assert offer.plus_label == "PS Plus Deluxe"
    assert offer.price == 329900
    assert offer.base_price == 329900
    assert offer.discount_percent is None
    assert offer.is_free is False


def test_parse_sale_with_plus_catalog() -> None:
    raw = {
        "id": "UP0000-CUSA00000_00-BLOODBORNE",
        "name": "Bloodborne",
        "platforms": ["PS4"],
        "storeDisplayClassification": "FULL_GAME",
        "price": {
            "basePrice": "UAH 649,00",
            "discountText": "-75%",
            "discountedPrice": "UAH 162,25",
            "isFree": False,
            "isTiedToSubscription": False,
            "serviceBranding": ["NONE"],
            "upsellServiceBranding": ["PS_PLUS"],
            "upsellText": "Extra",
        },
    }
    offer = parse_offer(raw, "uk-ua")
    assert offer is not None
    assert offer.plus_included is False
    assert offer.plus_label == "PS Plus Extra"
    assert offer.discount_percent == 75
    assert offer.price == 16225


def test_thumb_url_resizes_psn_cdn() -> None:
    full = "https://image.api.playstation.com/vulcan/ap/rnd/cover.png"
    assert thumb_url(full) == full.replace(".png", ".png?w=160&f=jpg")
    assert thumb_url(full + "?already=1") == full + "?w=160&f=jpg"
    assert thumb_url("https://example.com/a.jpg") == "https://example.com/a.jpg"
    assert thumb_url(None) is None
