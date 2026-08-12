# Bybit Reactive Trading Bot & Viewer

Асинхронный инструмент и бот для работы с криптобиржей **Bybit (v5 API)** на Python 3.11+.

Данный модуль содержит консольную утилиту `viewer.py` для отслеживания всех активных и частично исполненных ордеров по всем торговым парам с отображением визуального прогресса их исполнения.

---

## 🛠️ Технологический стек и требования

- **Python**: 3.11+
- **Менеджер пакетов**: `uv`
- **SDK**: `pybit` (Bybit v5 API)
- **Конкурентность**: `asyncio`
- **Форматирование CLI**: `rich`

---

## 🔑 Авторизация и конфигурация

Поддерживаются **два способа аутентификации**:
1. **RSA Private Key (`private.pem`)** — приватный ключ в формате PEM (рекомендуется).
2. **HMAC Secret Key** — стандартный секретный ключ API.

Создайте файл `.env` в корневой директории проекта:

```env
# Переключатель режимов (True - Testnet / False - Mainnet)
USE_TESTNET=True
DRY_RUN=True

# Математика ордеров (%)
SPREAD_PERCENT=1.25
SAVINGS_PERCENT=0.25

# Оффлайн-синхронизация сделок при старте
SYNC_OFFLINE_HISTORY=True
SYNC_HOURS=24

# Боевые ключи (Mainnet)
BYBIT_API_KEY=ваш_mainnet_api_key
BYBIT_BOT_NAME=имя_вашего_бота
BYBIT_PRIVATE_KEY_PATH=private.pem

# Тестовые ключи (Testnet)
BYBIT_TESTNET_API_KEY=ваш_testnet_api_key
BYBIT_TESTNET_BOT_NAME=имя_тестового_бота
BYBIT_TESTNET_PRIVATE_KEY_PATH=private_testnet.pem

# Торговые категории по умолчанию (через запятую)
BYBIT_CATEGORIES=spot,linear
```

### ⚙️ Описание ключевых переменных `.env`

| Переменная | Тип | Значение по умолчанию | Описание |
| :--- | :--- | :--- | :--- |
| `USE_TESTNET` | `bool` | `True` | `True` — переключение на **Testnet**, `False` — работа на реальной бирже **Mainnet**. |
| `DRY_RUN` | `bool` | `True` | `True` — режим симуляции (расчет ордеров без их отправки на Bybit), `False` — реальное выставление ордеров. |
| `SPREAD_PERCENT` | `float` | `1.25` | Процент скидки (зазора) от средневзвешенной цены продажи BTC для ордера покупки WBTC (`buy_price_wbtc = avg_sell_price * (1 - SPREAD_PERCENT / 100)`). |
| `SAVINGS_PERCENT` | `float` | `0.25` | Процент удержания от суммы USDT на комиссии биржи и долларовую копилку (`safe_usdt = total_usdt * (1 - SAVINGS_PERCENT / 100)`). |
| `SYNC_OFFLINE_HISTORY` | `bool` | `True` | `True` — запрашивать оффлайн-историю сделок при старте бота, `False` — полностью отключить REST-синхронизацию на старте. |
| `SYNC_HOURS` | `float` | `24` | Глубина временного окна в часах для первично запрашиваемой REST-истории сделок при включенной оффлайн-синхронизации. |

> 💡 **Автовыбор ключей и настроек**: В зависимости от `USE_TESTNET` (True/False) и значений остальных переменных в `.env`, бот автоматически подгружает соответствующую конфигурацию, торговую математику и параметры оффлайн-синхронизации.

---

## 🚀 Установка и запуск

1. **Установка зависимостей с помощью `uv`**:
   ```bash
   uv sync
   ```

2. **Запуск утилиты просмотра ордеров (`viewer.py`)**:
   ```bash
   uv run python viewer.py
   ```

---

## 📋 Описание флагов командной строки `viewer.py`

| Флаг / Опция | Полный флаг | Описание | Значение по умолчанию | Пример использования |
| :--- | :--- | :--- | :--- | :--- |
| `-h` | `--help` | Показать справку по всем доступным параметрам и выйти. | - | `uv run python viewer.py --help` |
| `-c` | `--category` | Указать категории торговли (`spot`, `linear`, `inverse`, `option`). | Из `.env` (`BYBIT_CATEGORIES`) | `uv run python viewer.py -c spot` |
| `-s` | `--settle-coin` | Указать монету расчета для деривативов (`USDT`, `USDC`, `BTC`). | Авто (`USDT`, `USDC`) | `uv run python viewer.py -c linear -s USDT` |
| `-w` | `--watch` | Включить режим **живого мониторинга** с автообновлением. | Отключен (однократный вывод) | `uv run python viewer.py -w` |
| `-i` | `--interval` | Интервал обновления (в секундах) при включенном режиме `-w`. | `5` | `uv run python viewer.py -w -i 3` |
| | `--testnet` | Принудительно использовать **Bybit Testnet** вместо Mainnet. | Из `.env` (`BYBIT_TESTNET`) | `uv run python viewer.py --testnet` |

---

## 💡 Примеры использования

### 1. Однократный вывод всех активных ордеров
```bash
uv run python viewer.py
```

### 2. Мониторинг ордеров в реальном времени с обновлением каждые 2 секунды
```bash
uv run python viewer.py --watch --interval 2
```

### 3. Просмотр ордеров только для категории Spot на Testnet
```bash
uv run python viewer.py --category spot --testnet
```

### 4. Просмотр фьючерсных ордеров (Linear) с расчетом в USDT
```bash
uv run python viewer.py --category linear --settle-coin USDT
```

---

---

## 🤖 Реактивный хедж-бот (`bot.py`)

Торговый daemon-бот с реактивной хедж-логикой и защитой от дублирования ордеров:
- **Мониторинг**: Отслеживает все исполнения (даже частичные) ордеров на **ПРОДАЖУ (Sell)** по `BTCUSDT`.
- **Накопление**: Накапливает суммы сделок в SQLite БД (`hedge_bot.db`), пока общая сумма pending-сделок не достигнет лимита **>= 6.0 USDT**.
- **Встречный ордер и Слияние (Amend)**:
  - Рассчитывает средневзвешенную цену продажи со скидкой `SPREAD_PERCENT` (цена покупки с округлением ВНИЗ до 1 знака) и объем со сбережением `SAVINGS_PERCENT` (объем с округлением ВНИЗ до 5 знаков).
  - Проверяет открытые ордера на `WBTCUSDT`: если уже есть активный BUY-ордер по **точно такой же цене**, увеличивает его объем через `amend_order(...)` вместо спама новыми ордерами.
  - Если активного ордера по такой цене нет, выставляет новый лимитный ордер через `place_order(...)`.
- **Восстановление**: При запуске синхронизирует историю сделок за 24 часа через REST API до подписки на WebSocket.

---

## 🐧 Развертывание и запуск на чистом сервере Arch Linux

Подробное руководство по настройке и запуску бота на новом сервере с **Arch Linux**.

### 1. Подготовка системы и установка пакетов

Обновите систему и установите необходимый базовый инструментарий:

```bash
# Обновление базы пакетов и системы
sudo pacman -Syu

# Установка Git, Python, SQLite и необходимых утилит
sudo pacman -S git python sqlite base-devel
```

> 💡 Установите менеджер пакетов `uv` (официальный рекомендованный способ):
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> source ~/.bashrc
> ```

### 2. Клонирование и настройка проекта

```bash
# Клонирование репозитория
git clone https://github.com/Antony-hash512/bybit-bot.git
cd bybit-bot

# Синхронизация зависимостей (pybit, python-dotenv, rich, pycryptodome)
uv sync
```

### 3. Конфигурация ключей авторизации

Создайте или отредактируйте файл `.env` в корневой директории проекта (подробное описание и пример переменных см. в разделе [🔑 Авторизация и конфигурация](#-авторизация-и-конфигурация)):

```bash
nano .env
```

Если вы используете **RSA PEM-ключи**:
Положите файл ключа `private_testnet.pem` (для теста) или `private.pem` (для боевого режима) в корень проекта и ограничьте права доступа:
```bash
chmod 600 private*.pem
```

---

### 🧪 4. Тестирование в Testnet

Для безопасной проверки работы бота без риска реальными средствами используйте режим **Testnet** + **DRY_RUN**.

#### Этап 4.1: Безопасный прогон (Симуляция без отправки ордеров)
1. В `.env` установите:
   ```env
   USE_TESTNET=True
   DRY_RUN=True
   ```
2. Запустите бота:
   ```bash
   uv run python bot.py
   ```
3. **Что происходит**:
   - Бот считывает историю сделок за 24 часа через REST API.
   - Подключается к приватной сокет-сессии Testnet.
   - При накоплении сделок >= 6.0 USDT выводит в консоль красивый лог симуляции:
     `DRY_RUN: Выставил бы ордер Buy WBTCUSDT на сумму X по цене Y (Qty: Z)`
   - Обновляет статусы в SQLite БД `hedge_bot_testnet.db`.

#### Этап 4.2: Тестирование с реальным ордером в Testnet
1. В файле `.env` установите:
   ```env
   USE_TESTNET=True
   DRY_RUN=False
   ```
2. Запустите бота: `uv run python bot.py`.
3. Совершите продажу BTC на тестовом сайте [testnet.bybit.com](https://testnet.bybit.com).
4. Убедитесь в консоли и на сайте Bybit Testnet, что выставлен реальный лимитный ордер на покупку `WBTCUSDT`.

---

### ⚡ 5. Запуск в "боевых условиях" (Mainnet / Реальная биржа)

Перед запуском на реальном счете переключите конфигурацию в `.env`:

1. **Конфигурация `.env`**:
   ```env
   USE_TESTNET=False
   DRY_RUN=False
   ```

#### Способ А: Запуск как фоновая служба Systemd (Рекомендуется для 24/7 работы)

Создайте файл службы systemd:

```bash
sudo nano /etc/systemd/system/bybit-hedge-bot.service
```

Вставьте следующую конфигурацию (замените `username` и путь на ваши):

```ini
[Unit]
Description=Bybit Reactive Hedge Trading Bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=username
WorkingDirectory=/home/username/bybit-bot
ExecStart=/home/username/.local/bin/uv run python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Перезагрузите демон systemd и запустите сервис:

```bash
# Перезагрузить конфигурацию systemd
sudo systemctl daemon-reload

# Включить автозапуск при старте сервера и запустить службу прямо сейчас
sudo systemctl enable --now bybit-hedge-bot

# Проверить статус работы бота
sudo systemctl status bybit-hedge-bot

# Просмотр логов бота в реальном времени
journalctl -u bybit-hedge-bot -f
```

#### Способ Б: Запуск в сессии `tmux` / `screen`

```bash
# Создание новой сессии tmux
tmux new -s hedge-bot

# Запуск бота
uv run python bot.py

# Для выхода из сессии с сохранением работы нажмите: Ctrl+B, затем D
# Для повторного подключения к сессии:
tmux attach -t hedge-bot
```

---

### 📊 6. Мониторинг и проверка логов / SQLite базы данных

Вы можете параллельно проверять логи работы бота, состояние открытых ордеров и историю обработанных сделок:

```bash
# Просмотр логов бота из ротируемого текстового файла bot.log
tail -f bot.log

# Мониторинг ордеров на бирже через viewer.py
uv run python viewer.py --watch --interval 3

# Проверка последних 10 записей в базе SQLite (hedge_bot.db для Mainnet / hedge_bot_testnet.db для Testnet)
sqlite3 hedge_bot.db "SELECT exec_id, exec_qty, exec_price, exec_value_usdt, status, created_at FROM executions ORDER BY created_at DESC LIMIT 10;"
```

---

## 🧪 Запуск юнит-тестов

Проверка работы утилит просмотра и торговой математики хедж-бота:

```bash
# Тесты viewer.py
uv run python test_viewer.py

# Тесты hedge-бота (БД, математика 5% скидки, 1% буфера, DRY_RUN)
uv run python test_hedge_bot.py
```
