export function isPlausibleRack(rack: unknown): rack is string[] {
  if (!Array.isArray(rack) || rack.length === 0 || rack.length > 7) {
    return false;
  }

  const normalized = rack.every(
    (letter) => typeof letter === "string" && /^[A-Za-z?]$/.test(letter),
  );

  if (!normalized) {
    return false;
  }

  return rack.filter((letter) => letter === "?").length <= 2;
}
