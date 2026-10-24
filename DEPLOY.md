# Развёртывание на сервере (от root)

Бот работает long polling + SQLite (`data/psn.sqlite3`). Вебхук не нужен.

На один `BOT_TOKEN` — один процесс. Перед запуском на сервере останови бота на компьютере, иначе Telegram ответит `409 Conflict`.

Репозиторий: https://github.com/mifaaa93/game_pricer.git

## 0. Telegram

1. [@BotFather](https://t.me/BotFather) → токен.
2. Inline Mode: `/mybots` → бот → **Bot Settings** → **Inline Mode** → Turn on. Placeholder: `Название игры`.
3. Канал для скидок. Добавь бота **админом** с правом публиковать сообщения.
4. `CHANNEL_ID`: перешли любой пост канала боту [@userinfobot](https://t.me/userinfobot) или открой `https://api.telegram.org/bot<TOKEN>/getUpdates` после сообщения в канале. Для канала это `-100...`.
5. Свой id для `/stats` — у [@userinfobot](https://t.me/userinfobot).

## 1. Система

Linux, Python 3.10 или новее.

```bash
apt update
apt install -y git python3 python3-venv python3-pip
```

## 2. Код

```bash
cd /root
git clone https://github.com/mifaaa93/game_pricer.git game_pricer
cd /root/game_pricer
```

Обновление уже установленного:

```bash
cd /root/game_pricer
systemctl stop game-pricer
git pull
.venv/bin/pip install -r requirements.txt
systemctl start game-pricer
```

## 3. Секреты

`.env` в git не попадает.

```bash
cd /root/game_pricer
cp .env.example .env
nano .env
chmod 600 .env
```

Минимум:

```env
BOT_TOKEN=123456:ABC-DEF
CHANNEL_ID=-1001234567890
ADMIN_IDS=480055341
```

Опционально (уже стоят в коде, если не прописать):

```env
LOCALE=uk-ua
REQUEST_DELAY=2
CYCLE_PAUSE=7200
GENRE_EVERY=6
```

## 4. Окружение

```bash
cd /root/game_pricer
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

Проверка вручную (Ctrl+C чтобы остановить):

```bash
cd /root/game_pricer
.venv/bin/python main.py
```

В логе: `bot started`, `Start polling`, `crawl PS4 catalog`. Первый обход каталога — десятки минут, уведомлений в канал на нём нет.

## 5. systemd от root

Файл `/etc/systemd/system/game-pricer.service`:

```ini
[Unit]
Description=PlayStation Store UA price bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/game_pricer
ExecStart=/root/game_pricer/.venv/bin/python -u main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Можно скопировать из репозитория:

```bash
cp /root/game_pricer/deploy/game-pricer.service /etc/systemd/system/game-pricer.service
systemctl daemon-reload
systemctl enable --now game-pricer
systemctl status game-pricer
```

Логи:

```bash
journalctl -u game-pricer -f
tail -f /root/game_pricer/data/bot.log
```

## 6. Данные

Каталог и история цен: `/root/game_pricer/data/psn.sqlite3`.  
В git не коммитится.

Бэкап (бот лучше остановить):

```bash
systemctl stop game-pricer
cp /root/game_pricer/data/psn.sqlite3 /root/game_pricer/data/psn.sqlite3.bak
systemctl start game-pricer
```

## 7. Частые проблемы

| Симптом | Что сделать |
|---|---|
| `409 Conflict` | Второй процесс с тем же токеном. `systemctl stop game-pricer` и выключи локальный `python main.py` |
| Бот молчит в канале | Бот не админ канала или неверный `CHANNEL_ID` |
| Инлайн не открывается | Не включён Inline Mode у BotFather |
| Каталог пустой | Коллектор ещё не закончил первый круг. Смотри `data/bot.log` |
