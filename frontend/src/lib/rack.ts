const UNICODE_TILE = /^[\p{L}?]$/u;

export function isPlausibleRack(
  rack: unknown,
  alphabet?: readonly string[],
): rack is string[] {
  if (!Array.isArray(rack) || rack.length === 0 || rack.length > 7) {
    return false;
  }

  const alphabetSet = alphabet !== undefined ? new Set(alphabet) : null;

  const normalized = rack.every((letter) => {
    if (typeof letter !== "string") {
      return false;
    }
    if (letter === "?") {
      return true;
    }
    if (alphabetSet) {
      return alphabetSet.has(letter);
    }
    return UNICODE_TILE.test(letter);
  });

  if (!normalized) {
    return false;
  }

  return rack.filter((letter) => letter === "?").length <= 2;
}
