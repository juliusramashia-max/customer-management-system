"""
Money helpers.

Every Decimal that represents money should pass through money() before
being persisted, so totals are consistently rounded to 2 decimal places
using commercial rounding (ROUND_HALF_UP), not Python's default banker's
rounding.
"""
from decimal import Decimal, ROUND_HALF_UP


TWO_PLACES = Decimal('0.01')


def money(value):
    """
    Round a Decimal to 2 decimal places using ROUND_HALF_UP.

    Accepts Decimal, int, or numeric string. Never pass float directly
    (that's the whole point of using Decimal).
    """
    if not isinstance(value, Decimal):
        # Be permissive: accept int and str; refuse float explicitly.
        if isinstance(value, float):
            raise TypeError(
                "money() refuses float input — use Decimal(str(x)) instead"
            )
        value = Decimal(str(value))
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_decimal(value):
    """
    Parse an incoming value (from JSON) into a Decimal without float drift.

    JSON turns numbers into int/float. We route through str() so the
    user's intended digits are preserved exactly.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).strip())