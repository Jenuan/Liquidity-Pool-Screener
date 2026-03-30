"""
Entrypoint script to run one cycle of the LP bot.

Usage (from project root, with venv ativo):

    python scripts/run_bot.py
"""

from lpbot.executor import run_once


def main() -> None:
    """Run a single execution cycle of the bot."""
    run_once()


if __name__ == "__main__":
    main()

