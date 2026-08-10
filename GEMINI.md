# Project: Bybit Reactive Trading Bot

## Role
Act as a senior Python developer and algorithmic trader. Write concise, production-ready, and asynchronous code. 

## Core Logic
- Connect to Bybit via WebSockets (Private Channel).
- Monitor `Order` events.
- **Trigger:** IF a `Sell` order status changes to `Filled`:
  - Calculate the corresponding `Buy` order parameters (price, quantity).
  - Place a new `Buy` order via REST API immediately.

## Tech Stack & Tools
- **Language:** Python 3.11+
- **Environment & Dependencies:** `uv` (strictly use `uv` for package management and script execution)
- **Bybit SDK:** `pybit`
- **Concurrency:** `asyncio`
- **Configuration:** `.env` for API keys and trading parameters

## Constraints & Development Guidelines
1. **No Polling:** Rely exclusively on WebSocket streams for order updates to minimize latency.
2. **Resilience:** Implement automatic reconnects for WebSockets. Handle REST API rate limits gracefully.
3. **Architecture:** Keep the code modular. Separate the WebSocket listener, order execution logic, and configuration loader.
4. **Logging:** Use standard Python `logging`. Log critical state changes (order filled, order placed) and errors. Do not over-log.
5. **Simplicity:** Avoid over-engineering. Do not introduce complex state machines or external databases unless strictly necessary.
