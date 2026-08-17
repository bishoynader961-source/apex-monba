"""
rx_init.py — Initialize Rx Workflow tables.

Usage:
    python archive/rx_init.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rx_database import init_rx_tables
from rx_config import ConfigManager
from rx_db import set_region_config


def main():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config.json")
    if not os.path.exists(config_path):
        config_path = "config.json"

    cm = ConfigManager()
    cm.set_path(os.path.abspath(config_path))

    init_rx_tables()

    region = cm.get("rx_region", "US")
    set_region_config(region)

    print(f"Rx tables initialized. Region set to: {region}")


if __name__ == "__main__":
    main()
