# ChannelCheck — прототип движка

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
- `tgcheck/metrics.py` — метрики и вердикт (пороги собраны в `THRESHOLDS`)
- `tgcheck/report.py` — текст отчёта на английском и русском, экспорт в JSON
- `tests/` — тестовые страницы и автоматические проверки
