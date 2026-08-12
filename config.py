"""
Configuration loader for Bybit Trading Bot.
Reads API credentials, RSA PEM keys, and trading parameters from environment variables (.env).
Supports mode switching via USE_TESTNET (True/False).
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("bybit_bot.config")


@dataclass
class Config:
    api_key: str
    api_secret: str
    bot_name: str
    rsa_authentication: bool
    testnet: bool
    categories: list[str]
    dry_run: bool
    spread_percent: float
    savings_percent: float


def load_config(use_testnet: bool | None = None) -> Config:
    """
    Load configuration from environment variables and .env file.
    If use_testnet is None, checks USE_TESTNET variable in .env.
    If use_testnet is True/False, explicitly overrides the .env setting.
    """
    load_dotenv()

    # Determine whether testnet mode is active
    if use_testnet is None:
        testnet_env = os.getenv("USE_TESTNET", os.getenv("BYBIT_TESTNET", "false")).strip().lower()
        testnet = testnet_env in ("true", "1", "yes")
    else:
        testnet = use_testnet

    categories_str = os.getenv("BYBIT_CATEGORIES", "spot,linear")
    categories = [c.strip() for c in categories_str.split(",") if c.strip()]

    # Select credentials according to testnet flag
    if testnet:
        api_key = os.getenv("BYBIT_TESTNET_API_KEY", "").strip() or os.getenv("BYBIT_API_KEY", "").strip()
        bot_name = os.getenv("BYBIT_TESTNET_BOT_NAME", "test_bot").strip()
        private_key_path = os.getenv("BYBIT_TESTNET_PRIVATE_KEY_PATH", "").strip()
        api_secret_raw = os.getenv("BYBIT_TESTNET_API_SECRET", "").strip()
        default_pem = "private_testnet.pem"
    else:
        api_key = os.getenv("BYBIT_API_KEY", "").strip()
        bot_name = os.getenv("BYBIT_BOT_NAME", "bot").strip()
        private_key_path = os.getenv("BYBIT_PRIVATE_KEY_PATH", "").strip()
        api_secret_raw = os.getenv("BYBIT_API_SECRET", "").strip()
        default_pem = "private.pem"

    api_secret = ""
    rsa_authentication = False

    # 1. Check explicit private_key_path
    if private_key_path and Path(private_key_path).is_file():
        logger.info(f"Loading RSA private key from path ({'testnet' if testnet else 'mainnet'}): {private_key_path}")
        api_secret = Path(private_key_path).read_text(encoding="utf-8")
        rsa_authentication = True
    # 2. Check if api_secret_raw is a file path
    elif api_secret_raw and Path(api_secret_raw).is_file():
        logger.info(f"Loading RSA private key from file path in secret: {api_secret_raw}")
        api_secret = Path(api_secret_raw).read_text(encoding="utf-8")
        rsa_authentication = True
    # 3. Check if api_secret_raw is an inline PEM string
    elif api_secret_raw.startswith("-----BEGIN"):
        logger.info("Using inline RSA private key")
        api_secret = api_secret_raw
        rsa_authentication = True
    # 4. Fallback: check default_pem or private.pem in working directory
    elif Path(default_pem).is_file():
        logger.info(f"Found '{default_pem}' in working directory. Using RSA private key authentication.")
        api_secret = Path(default_pem).read_text(encoding="utf-8")
        rsa_authentication = True
    elif Path("private.pem").is_file() and not api_secret_raw:
        logger.info("Found 'private.pem' in working directory. Using RSA private key authentication.")
        api_secret = Path("private.pem").read_text(encoding="utf-8")
        rsa_authentication = True
    # 5. Standard HMAC secret
    else:
        api_secret = api_secret_raw
        rsa_authentication = False

    dry_run_env = os.getenv("DRY_RUN", "true").strip().lower()
    dry_run = dry_run_env in ("true", "1", "yes")

    try:
        spread_percent = float(os.getenv("SPREAD_PERCENT", "1.25").strip())
    except ValueError:
        logger.warning("Invalid SPREAD_PERCENT in .env, falling back to 1.25")
        spread_percent = 1.25

    try:
        savings_percent = float(os.getenv("SAVINGS_PERCENT", "0.25").strip())
    except ValueError:
        logger.warning("Invalid SAVINGS_PERCENT in .env, falling back to 0.25")
        savings_percent = 0.25

    if not api_key:
        logger.warning(f"API key for {'testnet' if testnet else 'mainnet'} is missing or empty in .env file.")

    if not api_secret or api_secret == "your_api_secret_here":
        logger.warning(
            f"API secret / RSA private key for {'testnet' if testnet else 'mainnet'} is missing or default placeholder."
        )

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        bot_name=bot_name,
        rsa_authentication=rsa_authentication,
        testnet=testnet,
        categories=categories,
        dry_run=dry_run,
        spread_percent=spread_percent,
        savings_percent=savings_percent,
    )
