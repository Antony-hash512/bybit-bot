"""
Configuration loader for Bybit Trading Bot.
Reads API credentials, RSA PEM keys, and trading parameters from environment variables (.env).
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
    rsa_authentication: bool
    testnet: bool
    categories: list[str]


def load_config() -> Config:
    """
    Load configuration from environment variables and .env file.
    Supports both HMAC secret keys and RSA PEM private keys.
    """
    load_dotenv()

    api_key = os.getenv("BYBIT_API_KEY", "").strip()
    api_secret_raw = os.getenv("BYBIT_API_SECRET", "").strip()
    private_key_path = os.getenv("BYBIT_PRIVATE_KEY_PATH", "").strip()
    testnet_str = os.getenv("BYBIT_TESTNET", "false").lower()
    testnet = testnet_str in ("true", "1", "yes")

    categories_str = os.getenv("BYBIT_CATEGORIES", "spot,linear")
    categories = [c.strip() for c in categories_str.split(",") if c.strip()]

    api_secret = ""
    rsa_authentication = False

    # 1. Check explicit BYBIT_PRIVATE_KEY_PATH
    if private_key_path and Path(private_key_path).is_file():
        logger.info(f"Loading RSA private key from BYBIT_PRIVATE_KEY_PATH: {private_key_path}")
        api_secret = Path(private_key_path).read_text(encoding="utf-8")
        rsa_authentication = True
    # 2. Check if BYBIT_API_SECRET is a path to a PEM file
    elif api_secret_raw and Path(api_secret_raw).is_file():
        logger.info(f"Loading RSA private key from file path in BYBIT_API_SECRET: {api_secret_raw}")
        api_secret = Path(api_secret_raw).read_text(encoding="utf-8")
        rsa_authentication = True
    # 3. Check if BYBIT_API_SECRET is an inline PEM string
    elif api_secret_raw.startswith("-----BEGIN"):
        logger.info("Using inline RSA private key from BYBIT_API_SECRET")
        api_secret = api_secret_raw
        rsa_authentication = True
    # 4. Fallback: check if private.pem exists in working directory
    elif Path("private.pem").is_file() and (not api_secret_raw or api_secret_raw == "your_api_secret_here"):
        logger.info("Found 'private.pem' in working directory. Using RSA private key authentication.")
        api_secret = Path("private.pem").read_text(encoding="utf-8")
        rsa_authentication = True
    # 5. Standard HMAC secret
    else:
        api_secret = api_secret_raw
        rsa_authentication = False

    if not api_key:
        logger.warning("BYBIT_API_KEY is missing or empty in .env file.")

    if not api_secret or api_secret == "your_api_secret_here":
        logger.warning(
            "BYBIT_API_SECRET or RSA private key is missing or using default placeholders."
        )

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        rsa_authentication=rsa_authentication,
        testnet=testnet,
        categories=categories,
    )
