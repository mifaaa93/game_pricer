from __future__ import annotations

# Ключи как в PS Store (productGenres). Подписи — для меню бота.
GENRE_RU: dict[str, str] = {
    "ACTION": "Экшен",
    "ADVENTURE": "Приключения",
    "ARCADE": "Аркада",
    "BATTLE_ROYALE": "Battle Royale",
    "BOARD": "Настольные",
    "CARD": "Карточные",
    "CASUAL": "Казуальные",
    "COMBAT": "Военные",
    "COOP": "Кооп",
    "EDUCATIONAL": "Обучающие",
    "FAMILY": "Семейные",
    "FANTASY": "Фэнтези",
    "FIGHTING": "Файтинг",
    "FIRST_PERSON_SHOOTER": "Шутер от 1 лица",
    "FITNESS": "Фитнес",
    "HORROR": "Хоррор",
    "METROIDVANIA": "Метроидвания",
    "MMORPG": "MMORPG",
    "MOBA": "MOBA",
    "MUSIC": "Музыка",
    "OPEN_WORLD": "Открытый мир",
    "PARTY": "Вечеринка",
    "PLATFORMER": "Платформеры",
    "PUZZLE": "Головоломки",
    "QUIZ": "Викторины",
    "RACING": "Гонки",
    "ROLE_PLAYING_GAMES": "RPG",
    "ROGUELIKE": "Roguelike",
    "SCIENCE_FICTION": "Научная фантастика",
    "SHOOTER": "Шутеры",
    "SIMULATION": "Симуляторы",
    "SPORTS": "Спорт",
    "STEALTH": "Стелс",
    "STORY_RICH": "Сюжетные",
    "STRATEGY": "Стратегии",
    "SURVIVAL": "Выживание",
    "TACTICAL": "Тактика",
    "TRIVIA": "Trivia",
    "UNIQUE": "Уникальные",
    "VISUAL_NOVEL": "Визуальная новелла",
}


def genre_label(key: str, fallback: str | None = None) -> str:
    return GENRE_RU.get(key) or fallback or key
