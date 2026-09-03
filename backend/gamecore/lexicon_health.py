"""Content-aware health checks for a language asset. Pure engine module: no Django import.

Two tiers, deliberately separated, because readiness is computed PER REQUEST while the
largest shipped lexicon is 54 105 021 B:

``check_lexicon``  CHEAP. Reads at most ``MAX_PREFIX_BYTES`` and is cached on
    ``(resolved path, st_size, st_mtime_ns)``. This is the tier ``GET /api/game/variants/``
    consults. It must never read a whole lexicon.
``audit_lexicon``  EXPENSIVE. Streams the whole file: NFC of every surviving line, the
    duplicate policy, a word-count floor and an optional membership probe. It belongs to
    ``manage.py validate_lexicons`` and to the test harness, never to a request path.

ONE FILTER, NOT A SECOND ONE. ``surviving_word`` mirrors the loader that actually builds
the index — ``gamecore/fastdict.py:_read_words``: skip a raw line starting with ``'#'``,
``strip``, NFC-casefold, then ``str.isalpha`` — and adds the two-code-point floor the
product applies to every word at ``game/services.py:216``. A "surviving" line is therefore
exactly a line that can ever become a playable word.

⛔ Four measured properties of the SHIPPED assets that no rule here may trip on:

* ``collins2019.txt`` line 1 is prose, ``"Collins Scrabble Words (2019). 279,496 words.
  Words only."``, followed by an empty line. It is not a ``'#'`` comment, so it is
  discarded by ``str.isalpha`` rather than by a comment rule. The only correct requirement
  is "at least one line SURVIVING the filter" — never "every non-comment line is a word".
* Casing is not uniform: ``collins2019.txt`` is UPPERCASE while ``czech.txt``,
  ``polish.txt`` and ``slovak.txt`` are lowercase. Normalize first, compare second. That
  file also uses CRLF, which ``str.strip`` removes.
* The three expanded lexicons carry two ``'#'`` header lines each and
  ``slovak_two_tile_words.txt`` carries three, one of them a URL. A 65 536-byte prefix
  clears all of them with room to spare.
* ``czech.txt`` deliberately contains non-Czech code points (the Greek mu in ``μa μg μm
  μv``). Lexicon characters are NEVER validated against the variant alphabet: that
  invariant is about TILES, and such a rule would make Czech ``unavailable``.

Cheap-tier reason codes: ``ok`` ``missing`` ``empty`` ``bom`` ``invalid_utf8``
``no_surviving_word`` ``unreadable``. The audit adds ``non_nfc_line`` ``duplicate_word``
``too_few_words`` ``probe_absent`` ``probe_present``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_PREFIX_BYTES = 65_536
MIN_WORD_CODEPOINTS = 2
DEFAULT_MIN_SURVIVING_WORDS = 100
COMMENT_PREFIX = "#"
_UTF8_BOM = b"\xef\xbb\xbf"
# UTF-8 encodes a code point in at most four bytes, so a prefix cut can leave at most
# three bytes of an incomplete sequence behind.
_MAX_UTF8_SEQUENCE = 4


@dataclass(frozen=True)
class LexiconHealth:
    """Cheap-tier verdict. ``reason`` is the stable machine-readable key."""

    ok: bool
    reason: str
    surviving_words_in_prefix: int = 0
    bytes_read: int = 0


@dataclass(frozen=True)
class LexiconAudit:
    """Whole-file verdict. ``reason`` is the stable machine-readable key."""

    ok: bool
    reason: str
    surviving_words: int = 0
    duplicate_words: int = 0
    non_nfc_lines: int = 0
    missing_probes: tuple[str, ...] = ()
    unexpected_probes: tuple[str, ...] = ()


def _nfc_casefold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def surviving_word(line: str) -> str | None:
    """The token this line contributes to the index, or ``None`` when it is discarded.

    Mirrors ``gamecore/fastdict.py:_read_words`` — including the comment test against the
    RAW line, before stripping — plus the two-code-point floor from
    ``game/services.py:216``.
    """
    if line.startswith(COMMENT_PREFIX):
        return None
    token = _nfc_casefold(line.strip())
    if len(token) < MIN_WORD_CODEPOINTS:
        return None
    if not token.isalpha():
        return None
    return token


def _decode_bounded(raw: bytes, *, truncated: bool) -> str | None:
    """Strict UTF-8 over a bounded prefix, tolerating a character cut by the bound.

    A prefix read can slice a multi-byte character in half, so when — and only when — the
    read stopped short of end of file, the incomplete tail is dropped: at the last newline
    if there is one, otherwise by discarding the trailing incomplete sequence. A false
    ``invalid_utf8`` here would report a GOOD lexicon as ``unavailable``, which is worse
    than the defect this module exists to fix.
    """
    candidate = raw
    if truncated:
        newline = raw.rfind(b"\n")
        if newline != -1:
            candidate = raw[: newline + 1]
    try:
        return candidate.decode("utf-8")
    except UnicodeDecodeError as exc:
        if truncated and exc.start >= len(candidate) - (_MAX_UTF8_SEQUENCE - 1):
            try:
                return candidate[: exc.start].decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None


_HEALTH_CACHE: dict[tuple[str, int, int], LexiconHealth] = {}


def _check_uncached(path: Path, *, size: int) -> LexiconHealth:
    if size == 0:
        return LexiconHealth(ok=False, reason="empty")
    try:
        with path.open("rb") as handle:
            head = handle.read(MAX_PREFIX_BYTES)
    except OSError:
        return LexiconHealth(ok=False, reason="unreadable")
    if head.startswith(_UTF8_BOM):
        return LexiconHealth(ok=False, reason="bom", bytes_read=len(head))
    text = _decode_bounded(head, truncated=len(head) < size)
    if text is None:
        return LexiconHealth(ok=False, reason="invalid_utf8", bytes_read=len(head))
    survivors = sum(1 for line in text.splitlines() if surviving_word(line) is not None)
    if survivors == 0:
        return LexiconHealth(ok=False, reason="no_surviving_word", bytes_read=len(head))
    return LexiconHealth(
        ok=True,
        reason="ok",
        surviving_words_in_prefix=survivors,
        bytes_read=len(head),
    )


def check_lexicon(path: Path) -> LexiconHealth:
    """Cheap, bounded and cached: safe to call on every request.

    ⛔ The cache key includes ``st_size`` and ``st_mtime_ns`` and never the path alone, so
    a lexicon rebuilt in place is re-checked instead of being trusted forever. A file that
    cannot be stat-ed is not cached at all, so an asset that appears later is picked up
    without a process restart.
    """
    if not path.is_file():
        return LexiconHealth(ok=False, reason="missing")
    try:
        info = path.stat()
    except OSError:
        return LexiconHealth(ok=False, reason="missing")
    key = (str(path.resolve()), info.st_size, info.st_mtime_ns)
    cached = _HEALTH_CACHE.get(key)
    if cached is not None:
        return cached
    result = _check_uncached(path, size=info.st_size)
    _HEALTH_CACHE[key] = result
    return result


def audit_lexicon(
    path: Path,
    *,
    min_words: int = DEFAULT_MIN_SURVIVING_WORDS,
    expect_present: frozenset[str] = frozenset(),
    expect_absent: frozenset[str] = frozenset(),
) -> LexiconAudit:
    """Whole-file audit. ⛔ Never call this from a request path.

    Duplicate policy, stated explicitly: a surviving token must appear exactly once. The
    index de-duplicates into a ``frozenset`` (``gamecore/fastdict.py:37``), so a duplicate
    is silent waste that only a whole-file pass can see. Measured over the shipped assets:
    english 279 496, slovak 3 005 250, czech 3 930 497 and polish 3 721 704 surviving
    tokens, with zero duplicates and zero non-NFC lines, so the policy costs the shipped
    set nothing.

    ``min_words`` is a floor, not a target: the smallest shipped dictionary has 279 496
    surviving tokens, while an auxiliary list such as ``slovak_two_tile_words.txt`` is
    intentionally tiny (103 entries) and is audited with its own lower floor.
    """
    cheap = check_lexicon(path)
    if not cheap.ok:
        return LexiconAudit(ok=False, reason=cheap.reason)

    wanted = {_nfc_casefold(word) for word in expect_present}
    forbidden = {_nfc_casefold(word) for word in expect_absent}
    found_forbidden: set[str] = set()
    seen: set[str] = set()
    survivors = 0
    duplicates = 0
    non_nfc = 0
    try:
        with path.open("r", encoding="utf-8", errors="strict") as handle:
            for line in handle:
                token = surviving_word(line)
                if token is None:
                    continue
                stripped = line.strip()
                if unicodedata.normalize("NFC", stripped) != stripped:
                    non_nfc += 1
                survivors += 1
                if token in seen:
                    duplicates += 1
                else:
                    seen.add(token)
                wanted.discard(token)
                if token in forbidden:
                    found_forbidden.add(token)
    except UnicodeDecodeError:
        return LexiconAudit(ok=False, reason="invalid_utf8")
    except OSError:
        return LexiconAudit(ok=False, reason="unreadable")

    missing = tuple(sorted(wanted))
    unexpected = tuple(sorted(found_forbidden))
    if non_nfc:
        reason = "non_nfc_line"
    elif duplicates:
        reason = "duplicate_word"
    elif survivors < min_words:
        reason = "too_few_words"
    elif missing:
        reason = "probe_absent"
    elif unexpected:
        reason = "probe_present"
    else:
        reason = "ok"
    return LexiconAudit(
        ok=reason == "ok",
        reason=reason,
        surviving_words=survivors,
        duplicate_words=duplicates,
        non_nfc_lines=non_nfc,
        missing_probes=missing,
        unexpected_probes=unexpected,
    )
