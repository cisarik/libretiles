from __future__ import annotations

import random
from dataclasses import dataclass, field

from .types import TilePoints
from .variant_store import VariantDefinition, get_default_variant, load_variant


def _resolve_variant(variant: VariantDefinition | str | None) -> VariantDefinition:
    if isinstance(variant, VariantDefinition):
        return variant
    if isinstance(variant, str) and variant:
        return load_variant(variant)
    return get_default_variant()


def get_tile_points(variant: VariantDefinition | str | None = None) -> TilePoints:
    resolved = _resolve_variant(variant)
    return dict(resolved.tile_points)


def get_tile_distribution(variant: VariantDefinition | str | None = None) -> dict[str, int]:
    resolved = _resolve_variant(variant)
    return dict(resolved.distribution)


@dataclass
class TileBag:
    seed: int | None = None
    tiles: list[str] = field(default_factory=list)
    variant: VariantDefinition | str | None = None

    def __post_init__(self) -> None:
        self._variant = _resolve_variant(self.variant)
        self.variant = self._variant
        self.variant_slug = self._variant.slug
        if not self.tiles:
            for ch, count in self._variant.distribution.items():
                self.tiles.extend([ch] * count)
            self._rng = random.Random(self.seed)
            self._rng.shuffle(self.tiles)
        else:
            self._rng = random.Random(self.seed)

    def draw(self, n: int) -> list[str]:
        out, self.tiles = self.tiles[:n], self.tiles[n:]
        return out

    def put_back(self, letters: list[str]) -> None:
        self.tiles.extend(letters)
        self._rng.shuffle(self.tiles)

    def exchange(self, letters: list[str]) -> list[str]:
        count = len(letters)
        self.put_back(letters)
        return self.draw(count)

    def remaining(self) -> int:
        return len(self.tiles)
