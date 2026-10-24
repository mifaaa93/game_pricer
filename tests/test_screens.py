from bot.screens import ASSET_FILES, asset_key_for_genre, asset_path


def test_assets_exist() -> None:
    for key, name in ASSET_FILES.items():
        path = asset_path(key)
        assert path.exists(), f"missing {name} for {key}"


def test_genre_art_mapping() -> None:
    assert asset_key_for_genre("ACTION") == "genre_action"
    assert asset_key_for_genre("ROLE_PLAYING_GAMES") == "genre_rpg"
    assert asset_key_for_genre("SALE") == "sale"
    assert asset_key_for_genre("UNKNOWN", "PS4") == "ps4"
    assert asset_key_for_genre("UNKNOWN", "all") == "catalog"
