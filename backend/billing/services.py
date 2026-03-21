from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.conf import settings
from django.db import transaction

from billing.models import CreditBalance, Transaction
from catalog.models import AIModel
from game.models import GameSession

_ZERO = Decimal("0")
_CENT = Decimal("0.01")
_USD_PRECISION = Decimal("0.000001")


def ensure_credit_balance(user) -> CreditBalance:  # type: ignore[no-untyped-def]
    starting_balance = Decimal(str(settings.DEFAULT_STARTING_CREDITS))

    with transaction.atomic():
        balance = CreditBalance.objects.select_for_update().filter(user=user).first()
        if balance is None:
            balance = CreditBalance.objects.create(user=user, balance=starting_balance)
        return balance


def build_balance_summary(user) -> dict[str, str | None]:  # type: ignore[no-untyped-def]
    balance = ensure_credit_balance(user)
    return {
        "credit_balance": _format_decimal(balance.balance),
        "credit_updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
    }


def charge_ai_move(
    *,
    user,
    game: GameSession,
    ai_model: AIModel | None,
    ai_metadata: dict[str, Any] | None,
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    balance = ensure_credit_balance(user)
    usd_charge, usage_summary, charge_source = _calculate_ai_charge(ai_model, ai_metadata)
    credits_charge = _to_credits(usd_charge)

    if credits_charge <= _ZERO:
        return {
            "charged_credits": "0.00",
            "remaining_credits": _format_decimal(balance.balance),
            "charged_usd": _format_decimal(usd_charge, precision=_USD_PRECISION),
            "charge_source": charge_source,
            "model_id": ai_model.model_id if ai_model else None,
            **usage_summary,
        }

    with transaction.atomic():
        locked_balance = CreditBalance.objects.select_for_update().get(pk=balance.pk)
        locked_balance.balance = _quantize_credits(locked_balance.balance - credits_charge)
        locked_balance.save(update_fields=["balance"])

        Transaction.objects.create(
            user=user,
            type="game_charge",
            amount=-credits_charge,
            description=_build_charge_description(ai_model, usage_summary, charge_source),
            game=game,
        )

    locked_balance.refresh_from_db()
    return {
        "charged_credits": _format_decimal(credits_charge),
        "remaining_credits": _format_decimal(locked_balance.balance),
        "charged_usd": _format_decimal(usd_charge, precision=_USD_PRECISION),
        "charge_source": charge_source,
        "model_id": ai_model.model_id if ai_model else None,
        **usage_summary,
    }


def _calculate_ai_charge(
    ai_model: AIModel | None,
    ai_metadata: dict[str, Any] | None,
) -> tuple[Decimal, dict[str, int], str]:
    usage = ai_metadata.get("usage") if isinstance(ai_metadata, dict) else None
    usage_summary = _extract_usage_summary(usage)
    if ai_model is None:
        return (_ZERO, usage_summary, "none")

    usd_charge = _usage_charge_usd(ai_model, usage, usage_summary)
    if usd_charge > _ZERO:
        return (usd_charge, usage_summary, "token_usage")

    fallback_credits = _as_decimal(ai_model.cost_per_game)
    if fallback_credits > _ZERO:
        usd_equivalent = fallback_credits / Decimal(str(settings.CREDITS_PER_USD))
        return (usd_equivalent, usage_summary, "legacy_cost_per_game")

    return (_ZERO, usage_summary, "none")


def _usage_charge_usd(
    ai_model: AIModel,
    usage: Any,
    usage_summary: dict[str, int],
) -> Decimal:
    if not isinstance(usage, dict):
        return _ZERO

    input_cost = _pricing_decimal(ai_model, "input")
    output_cost = _pricing_decimal(ai_model, "output")
    cache_read_cost = _pricing_decimal(ai_model, "input_cache_read")
    cache_write_cost = _pricing_decimal(ai_model, "input_cache_write")

    no_cache_tokens = usage_summary["input_tokens"]
    cache_read_tokens = 0
    cache_write_tokens = 0

    nested_input = usage.get("inputTokens")
    if isinstance(nested_input, dict):
        nested_total = int(nested_input.get("total") or 0)
        cache_read_tokens = int(
            nested_input.get("cacheRead")
            or nested_input.get("cacheReadTokens")
            or 0
        )
        cache_write_tokens = int(
            nested_input.get("cacheWrite")
            or nested_input.get("cacheWriteTokens")
            or 0
        )
        no_cache_tokens = int(
            nested_input.get("noCache")
            or nested_input.get("noCacheTokens")
            or max(nested_total - cache_read_tokens - cache_write_tokens, 0)
        )

    details = usage.get("inputTokenDetails")
    if isinstance(details, dict) and any(
        details.get(key) is not None
        for key in ("noCacheTokens", "cacheReadTokens", "cacheWriteTokens")
    ):
        no_cache_tokens = int(details.get("noCacheTokens") or no_cache_tokens or 0)
        cache_read_tokens = int(details.get("cacheReadTokens") or cache_read_tokens or 0)
        cache_write_tokens = int(details.get("cacheWriteTokens") or cache_write_tokens or 0)

    usd_total = (
        Decimal(no_cache_tokens) * input_cost
        + Decimal(cache_read_tokens) * cache_read_cost
        + Decimal(cache_write_tokens) * cache_write_cost
        + Decimal(usage_summary["output_tokens"]) * output_cost
    )
    return usd_total.quantize(_USD_PRECISION, rounding=ROUND_HALF_UP)


def _extract_usage_summary(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    nested_input = usage.get("inputTokens")
    nested_output = usage.get("outputTokens")
    input_total = (
        int(nested_input.get("total") or 0)
        if isinstance(nested_input, dict)
        else int(usage.get("inputTokens") or 0)
    )
    output_total = (
        int(nested_output.get("total") or 0)
        if isinstance(nested_output, dict)
        else int(usage.get("outputTokens") or 0)
    )
    total_tokens = int(usage.get("totalTokens") or (input_total + output_total))

    return {
        "input_tokens": input_total,
        "output_tokens": output_total,
        "total_tokens": total_tokens,
    }


def _pricing_decimal(ai_model: AIModel, key: str) -> Decimal:
    pricing = ai_model.pricing if isinstance(ai_model.pricing, dict) else {}
    return _as_decimal(pricing.get(key))


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO


def _to_credits(usd_amount: Decimal) -> Decimal:
    return _quantize_credits(usd_amount * Decimal(str(settings.CREDITS_PER_USD)))


def _quantize_credits(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _format_decimal(value: Decimal, *, precision: Decimal = _CENT) -> str:
    return format(value.quantize(precision, rounding=ROUND_HALF_UP), "f")


def _build_charge_description(
    ai_model: AIModel | None,
    usage_summary: dict[str, int],
    charge_source: str,
) -> str:
    model_id = ai_model.model_id if ai_model else "unknown-model"
    return (
        f"AI move charge via {model_id} "
        f"({usage_summary['input_tokens']} in / {usage_summary['output_tokens']} out, {charge_source})"
    )
