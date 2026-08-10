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

> 💡 **Автовыбор ключей**: В зависимости от `USE_TESTNET` (True/False), модуль `config.py` автоматически подтягивает соответствующие API-ключи, имя бота и путь к RSA PEM ключу.

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

## 🧪 Запуск юнит-тестов

Проверка корректности расчетов прогресса и формирования таблиц:
```bash
uv run python test_viewer.py
```
