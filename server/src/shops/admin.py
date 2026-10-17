"""Compatibility entry point; use python -m src.admin grant USERNAME."""

from src.admin.__main__ import change, main  # noqa: F401

if __name__ == "__main__":
    main()
