from decimal import Decimal

from src.ingestion.normalize import format_count, format_pct, format_usd


def test_format_usd_billions():
    assert format_usd(Decimal("1523000000")) == "$1.52B"


def test_format_usd_millions():
    assert format_usd(Decimal("245000000")) == "$245.00M"


def test_format_usd_thousands():
    assert format_usd(Decimal("42500")) == "$42.50K"


def test_format_usd_small():
    assert format_usd(Decimal("99.50")) == "$99.50"


def test_format_count_thousands():
    assert format_count(Decimal("142000")) == "142.0K"


def test_format_count_millions():
    assert format_count(Decimal("5000000")) == "5.00M"


def test_format_count_small():
    assert format_count(Decimal("42")) == "42"


def test_format_pct():
    assert format_pct(Decimal("0.1534")) == "15.3%"


def test_format_pct_small():
    assert format_pct(Decimal("0.05")) == "5.0%"
