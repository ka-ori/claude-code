import pytest

from alphagen.catalog import Catalog, Field
from alphagen.fastexpr import canonicalize, parse, to_source, validate
from alphagen.fastexpr.validator import Validator


def codes(result, severity=None):
    return {i.code for i in result.issues if severity is None or i.severity == severity}


@pytest.mark.parametrize(
    "expr",
    [
        "rank(-ts_delta(close, 5))",
        "group_rank((revenue - cogs) / assets, sector)",
        "winsorize(close / vwap, std=4)",
        "group_mean(returns, 1, sector)",
        'group_rank(returns, bucket(rank(cap), range="0,1,0.1"))',
        "a = ts_mean(returns, 20); b = ts_std_dev(returns, 60); trade_when(a > b, -rank(a), -1)",
        "if_else(ts_std_dev(returns, 20) > ts_std_dev(returns, 60), rank(returns), -rank(returns))",
        "and(close > open, not(volume < adv20))",
        "ts_decay_exp_window(returns, 10, factor=0.5)",
        "add(rank(close / vwap), rank(returns), rank(volume / adv20), filter=true)",
    ],
)
def test_valid_expressions(expr):
    result = validate(expr)
    assert result.ok, result.format()


@pytest.mark.parametrize(
    "expr, code",
    [
        ("rnak(close)", "UNKNOWN_OPERATOR"),
        ("ts_mean(close)", "MISSING_ARG"),
        ("ts_mean(close, d)", "NON_CONSTANT_LOOKBACK"),
        ("ts_mean(close, 2.5)", "BAD_LOOKBACK"),
        ("ts_mean(close, 1000)", "LOOKBACK_TOO_LONG"),
        ("rank(close, rate=2, foo=1)", "UNKNOWN_KEYWORD"),
        ("abs(close, returns)", "TOO_MANY_ARGS"),
        ("rank(sector)", "GROUP_AS_VALUE"),
        ("group_rank(close, close)", "EXPECTED_GROUP"),
        ("group_mean(returns, sector)", "MISSING_ARG"),
        ("bucket(rank(cap))", "MISSING_ARG"),
        ("close ** 2", "UNSUPPORTED_OPERATOR"),
        ("close % 2", "UNSUPPORTED_OPERATOR"),
        ("a < b < c", "CHAINED_COMPARISON"),
        ("close if returns > 0 else open", "PYTHON_SYNTAX"),
        ("close[0]", "PYTHON_SYNTAX"),
        ("x = rank(close)", "NO_OUTPUT"),
        ("rank(y); y = close", "USE_BEFORE_ASSIGN"),
        ("ts_decay_exp_window(returns, 10, factor=2)", "OUT_OF_RANGE"),
        ("rank(close, rate=true)", "NON_CONSTANT_PARAM"),
        ("ts_decay_linear(close, 5, dense=1)", "BAD_PARAM"),
    ],
)
def test_errors(expr, code):
    result = validate(expr)
    assert not result.ok
    assert code in codes(result, "error"), result.format()


def test_parse_errors_have_hints():
    for expr in ("returns > 0 ? close : open", "!close", "rank(close"):
        result = validate(expr)
        assert codes(result) == {"PARSE"}
        assert result.issues[0].hint or "unbalanced" in result.issues[0].message


@pytest.fixture
def vector_catalog():
    catalog = Catalog.load()
    catalog.add(Field(id="news_sentiment", kind="vector", category="news"))
    return catalog


def test_vector_field_must_be_collapsed(vector_catalog):
    v = Validator(catalog=vector_catalog)
    bad = v.validate("rank(news_sentiment)")
    assert "VECTOR_NOT_REDUCED" in codes(bad, "error")
    assert "vec_avg(news_sentiment)" in bad.errors[0].hint
    assert "VECTOR_NOT_REDUCED" in codes(v.validate("news_sentiment * 2"), "error")
    assert v.validate("rank(vec_avg(news_sentiment))").ok
    assert "EXPECTED_VECTOR" in codes(v.validate("vec_avg(close)"), "error")


def test_positional_optional_argument_is_flagged():
    result = validate("winsorize(close / vwap, 4)")
    assert "POSITIONAL_OPTIONAL" in codes(result, "warning")


def test_unknown_field_strictness():
    assert "UNKNOWN_FIELD" in codes(validate("rank(mystery_field)"), "warning")
    assert "UNKNOWN_FIELD" in codes(Validator(strict_fields=True).validate("rank(mystery_field)"), "error")


def test_research_warnings():
    assert "RAW_LEVEL" in codes(validate("rank(close)"))
    assert "CROSS_SECTOR_FUNDAMENTALS" in codes(validate("rank(operating_income / assets)"))
    assert "CROSS_SECTOR_FUNDAMENTALS" not in codes(
        Validator(neutralization="INDUSTRY").validate("rank(operating_income / assets)"))
    assert "HIGH_TURNOVER_RISK" in codes(validate("rank(-ts_delta(close, 3))"))
    assert "HIGH_TURNOVER_RISK" not in codes(Validator(decay=6).validate("rank(-ts_delta(close, 3))"))
    assert "RAW_LEVEL" not in codes(validate('group_rank(returns, bucket(rank(cap), range="0,1,0.1"))'))


@pytest.mark.parametrize(
    "src, expected",
    [
        ("close && open || volume", "or(and(close, open), volume)"),
        ("-(a - b) / (c * d)", "-(a - b) / (c * d)"),
        ("a - (b - c)", "a - (b - c)"),
        ("(a - b) - c", "a - b - c"),
        ("rank(x , std = 4)", "rank(x, std=4)"),
        ("ts_backfill(x, 20, ignore='NAN')", 'ts_backfill(x, 20, ignore="NAN")'),
        ("a = rank(x);\n# comment\nb = a * 2;\nb", "a = rank(x); b = a * 2; b"),
        ("filter_flag = 1; add(a, b, filter=true)", "filter_flag = 1; add(a, b, filter=true)"),
    ],
)
def test_canonical_form(src, expected):
    assert canonicalize(src) == expected


@pytest.mark.parametrize(
    "src",
    [
        "group_rank((revenue - cogs) / assets, sector) - rank(-ts_sum(returns, 5))",
        "trade_when(volume > ts_mean(volume, 20), -ts_zscore(close / vwap, 5), -1)",
        "a = ts_mean(returns, 20); if_else(a > 0 && not(volume < adv20), rank(a), -rank(a))",
        "-1 * rank(-(close - open) / (high - low + 0.001))",
    ],
)
def test_round_trip_is_stable(src):
    once = to_source(parse(src))
    assert to_source(parse(once)) == once
