"""Reviewed asset families and reconstructed original item types/slots."""

import json
from functools import lru_cache

from src.config import ROOT


@lru_cache
def classification():
    return json.loads(
        (ROOT.parent / "assets/catalogs/item-classification.json").read_text(encoding="utf-8")
    )


def group_for(item, data=None):
    data = data or classification()
    recovered = data["items"][str(item.id)]
    if (item.main_type, item.inventory_category) == (
        recovered["main_type"],
        recovered["inventory_category"],
    ):
        return recovered["category"]
    # Respect manual classification when adding an item to a default shop.
    if item.main_type == 1:
        return {
            0: "incomplete",
            3: "head",
            7: "head",
            4: "upper",
            8: "upper",
            13: "upper",
            14: "upper",
            21: "upper",
            1: "lower",
            11: "shoes",
            18: "glasses",
            19: "glasses",
        }.get(item.inventory_category, "accessories")
    return {
        2: "furniture",
        3: "beads",
        4: "beads",
        6: "pets",
        7: "pets",
        8: "food",
        9: "toys",
        10: "potions",
        11: "toys",
        12: "puzzles",
        13: "vehicles",
        14: "vehicles",
    }.get(item.main_type, recovered["category"])
