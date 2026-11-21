# ChannelCheck — движок и Telegram-бот

Проверяет публичный Telegram-канал перед покупкой рекламы: охват, признаки накрутки,
доля рекламы, цена за 1000 просмотров и итоговый вердикт 🟢 / 🟡 / 🔴.
Работает по публичным страницам t.me без Telegram-аккаунта.

## Установка (один раз)

```
cd C:\ProjectsAI\tgcheck
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

Включите VPN (t.me в России замедлен), затем:

```
python -m tgcheck durov --lang ru
python -m tgcheck https://t.me/имя_канала --lang ru --price 50
python -m tgcheck имя_канала --posts 150 --json result.json
```

- `--lang ru` — отчёт на русском (по умолчанию английский)
- `--price 50` — цена рекламы, которую просит админ: посчитает цену за 1000 просмотров
- `--posts 150` — сколько последних постов анализировать (по умолчанию 100)
- `--json файл.json` — сохранить полный результат

## Проверка многих каналов сразу

Создайте текстовый файл со списком каналов (по одному в строке, пример: `channels.example.txt`) и запустите:

```
python -m tgcheck --batch channels.txt --csv results.csv
```

Результаты сохранятся в таблицу `results.csv`, она открывается в Excel. Между каналами программа делает паузу 3 секунды (`--batch-delay`), чтобы не перегружать t.me. Если какой-то канал не удалось проверить, причина будет в колонке `error`, а остальные каналы проверятся как обычно.

## Если что-то пошло не так

Запустите с сохранением страниц и пришлите папку `debug` (в архиве):

```
python -m tgcheck имя_канала --save-html debug
```

Потом можно повторять анализ без интернета: `python -m tgcheck имя_канала --from-html debug`

## Проверки

```
python -m pytest -q
```

## Структура

- `tgcheck/fetch.py` — загрузка страниц t.me
- `tgcheck/parse.py` — разбор HTML: подписчики, посты, просмотры, реакции, реклама
- `tgcheck/metrics.py` — метрики и вердикт (пороги собраны в `THRESHOLDS`, поправки на частоту постов — в `FREQUENCY_FACTORS`)
- `tgcheck/report.py` — текст отчёта на английском и русском, экспорт в JSON
- `tests/` — тестовые страницы и автоматические проверки


---

# Telegram-бот

Бот принимает канал от пользователя, ставит проверку в очередь, воркер запускает движок `tgcheck` и присылает отчёт. Оплата — Telegram Stars (пакеты 1 / 5 / 20 проверок, цены в `app/products.py`). Первая проверка бесплатная. Проверка списывается только после выдачи отчёта.

## Состав

- `app/bot/` — бот на aiogram 3: команды, диалог, оплата (`handlers.py`), запуск (`main.py`), имена и описания бота на разных языках (`setup.py`).
- `app/worker/` — воркер на arq: выполняет проверки из очереди Redis, правит сообщение «Проверяю…» на отчёт.
- `app/repo.py` — работа с базой: пользователи, баланс, кэш, оплаты, события.
- `app/locales/` — тексты интерфейса (`en.json`, `ru.json`). Новый язык = новый файл с теми же ключами.
- `docker-compose.yml` — bot, worker, postgres, redis, backup.
- `.github/workflows/deploy.yml` — тесты на каждый push, деплой на сервер после зелёных тестов.

## 1. Создать бота

1. В Telegram откройте @BotFather → `/newbot`. Имя можно любое (потом поменяет `setup.py`), юзернейм — один из вариантов из плана, например `ChannelCheckerBot`.
2. Сохраните токен — он пойдёт в `.env` как `BOT_TOKEN`. Никому не показывайте и не коммитьте.
3. В BotFather для оплаты Stars ничего подключать не нужно: валюта `XTR` работает без платёжного провайдера.

## 2. Сервер (Timeweb Cloud, Нидерланды или Германия)

```
sudo apt update && sudo apt install -y git docker.io docker-compose-v2
sudo usermod -aG docker $USER   # перелогиньтесь после этого
git clone git@github.com:newLisa2024/channel-check.git /opt/channel-check
cd /opt/channel-check
cp .env.example .env   # и заполните BOT_TOKEN, POSTGRES_PASSWORD, ADMIN_IDS, ALERT_CHAT_ID, SUPPORT_CONTACT
docker compose up -d --build
docker compose run --rm bot python -m app.bot.setup   # имена и описания бота на EN и RU
docker compose logs -f bot worker
```

Для `git clone` на сервере нужен deploy key только на чтение: GitHub → репозиторий → Settings → Deploy keys.

## 3. Автодеплой

GitHub → Settings → Secrets and variables → Actions:

- Secrets: `DEPLOY_SSH_KEY` (приватный ключ для входа на сервер), `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH` (`/opt/channel-check`).
- Variables: `DEPLOY_ENABLED` = `true`.

После этого каждый push в `main`: тесты → `git pull` и `docker compose up -d --build` на сервере. Пока `DEPLOY_ENABLED` не задан, выполняются только тесты.

## 4. Бэкапы

Контейнер `backup` раз в сутки делает `pg_dump` в папку `./backups` на сервере и хранит 14 дней. Копию за пределы сервера настройте, например, через `rclone` в S3-хранилище Timeweb (cron на сервере: `rclone sync /opt/channel-check/backups timeweb-s3:channel-check-backups`).

## 5. Полезные команды

- Возврат оплаты (только для `ADMIN_IDS`): в чате с ботом `/refund <telegram_payment_charge_id>`. ID платежа — в таблице `payments`.
- Тесты бота и движка: `pip install -r requirements-dev.txt` и `python -m pytest -q`.

## Ограничения MVP

- Таблицы создаются при старте (`create_all`). Перед изменениями схемы на рабочей базе подключить Alembic.
- Режим long polling: домен и SSL не нужны. Webhook — позже, если понадобится.
- Одна проверка канала за раз (`max_jobs = 1` в воркере), чтобы не нагружать t.me.
