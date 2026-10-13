"""Our arithmetic, not a quoted bookmaker probability or a performance model."""
import math

def american_to_decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or abs(value) < 100:
        raise ValueError('American odds must be finite and at least 100 in magnitude')
    return 1 + (value/100 if value > 0 else 100/-value)

def fair_line(a, b):
    da, db = american_to_decimal(a), american_to_decimal(b)
    qa, qb = 1/da, 1/db
    total = qa + qb
    return dict(decimal_a=da, decimal_b=db, probability_a=qa/total, probability_b=qb/total,
                fair_a=total/qa, fair_b=total/qb, overround=total-1)
