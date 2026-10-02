import math

import pytest

from alphagen import metrics
from alphagen.cli import main, parse_pasted
from alphagen.fastexpr.mutate import crossover_valid, mutate
from alphagen.fastexpr.validator import validate
from alphagen.journal import Journal
from alphagen.settings import SimulationSettings, next_decay
from alphagen.themes import load_themes


def test_fitness_formula():
    assert metrics.fitness(1.5, 0.10, 0.40) == pytest.approx(1.5 * math.sqrt(0.10 / 0.40))
    # turnover below 12.5% is floored
    assert metrics.fitness(1.5, 0.10, 0.02) == pytest.approx(1.5 * math.sqrt(0.10 / 0.125))
    # sign follows Sharpe, magnitude uses |returns|
    assert metrics.fitness(-0.79, -0.0509, 0.0397) == pytest.approx(-0.79 * math.sqrt(0.0509 / 0.125))


def test_turnover_needed_for_fitness():
    ceiling = metrics.max_turnover_for_fitness(1.0, 1.5, 0.08)
    assert metrics.fitness(1.5, 0.08, ceiling) == pytest.approx(1.0)
    assert metrics.max_turnover_for_fitness(1.0, 0.8, 0.04) is None


def test_multiple_testing_hurdle():
    assert metrics.required_t(1) == 3.0
    assert metrics.required_t(1000) > 4.0
    assert metrics.haircut_sharpe(1.5, 1) == pytest.approx(1.5, rel=1e-6)
    assert metrics.haircut_sharpe(1.5, 200) < 1.5


@pytest.mark.parametrize("raw, expected", [("32.1%", 0.321), ("0.321", 0.321), (32.1, 0.321), ("-5.09%", -0.0509)])
def test_parse_rate(raw, expected):
    assert metrics.parse_rate(raw) == pytest.approx(expected)


def test_parse_pasted_brain_panel():
    text = "Sharpe\n-0.79\nTurnover\n3.97%\nFitness\n-0.50\nReturns\n-5.09%\nDrawdown\n24.68%\nMargin\n-25.66 bps"
    parsed = parse_pasted(text)
    assert parsed == {"sharpe": "-0.79", "turnover": "3.97%", "fitness": "-0.50", "returns": "-5.09%",
                      "drawdown": "24.68%", "margin": "-25.66"}


def test_settings():
    assert next_decay(0) == 2 and next_decay(10) == 15 and next_decay(30) is None
    assert any("truncation" in p for p in SimulationSettings(truncation=0.5).problems())
    assert SimulationSettings().with_(neutralization="industry").neutralization == "INDUSTRY"


def test_theme_seeds_validate():
    for theme in load_themes().values():
        for seed in theme.seeds:
            neut = theme.settings.get("neutralization")
            result = validate(seed, strict_fields=True, neutralization=neut)
            assert result.ok, f"{theme.id}: {seed}\n{result.format()}"


def test_mutations_are_valid_and_distinct():
    source = "group_rank(-ts_sum(returns, 5), subindustry)"
    variants = mutate(source)
    kinds = {v.kind for v in variants}
    assert {"lookback", "normalizer_swap", "group_change", "volume_event_gate", "sign_flip"} <= kinds
    expressions = [v.expression for v in variants]
    assert len(expressions) == len(set(expressions))
    assert source not in expressions
    assert all(validate(e).ok for e in expressions)


def test_crossover_renames_colliding_variables():
    variants = crossover_valid("a = rank(returns); a", "a = ts_mean(returns, 20); -rank(a)")
    assert variants
    for v in variants:
        assert "a_b = ts_mean(returns, 20)" in v.expression
        assert validate(v.expression).ok


def test_journal_workflow(tmp_path, monkeypatch, capsys):
    path = tmp_path / "alphas.jsonl"
    monkeypatch.setattr("alphagen.journal.JOURNAL_PATH", path)
    monkeypatch.setattr(Journal.__init__, "__defaults__", (path,))

    assert main(["propose", "group_rank(-ts_sum(returns, 5), subindustry)", "--theme", "short_term_reversal"]) == 0
    assert main(["propose", "group_rank(-ts_sum(returns, 5), subindustry)", "--theme", "short_term_reversal"]) == 1
    assert main(["propose", "rank(close", "--theme", "x"]) == 1

    assert main(["log", "A0001", "--sharpe", "1.9", "--turnover", "85%", "--returns", "14%"]) == 0
    out = capsys.readouterr().out
    assert "HIGH_TURNOVER" in out and "Decay" in out

    assert main(["rerun", "A0001", "--decay", "6"]) == 0
    journal = Journal(path)
    child = journal.get("A0002")
    assert child.parents == ["A0001"] and child.settings["decay"] == 6

    assert main(["log", "A0002", "--text", "Sharpe -1.4 Turnover 30% Fitness -0.9 Returns -8%"]) == 0
    assert "INVERTED" in capsys.readouterr().out

    assert main(["log", "A0002", "--sharpe", "1.6", "--turnover", "20%", "--returns", "9%", "--self-corr", "0.85"]) == 0
    assert "SELF_CORRELATED" in capsys.readouterr().out

    assert main(["status", "A0001", "submitted"]) == 0
    assert main(["stats"]) == 0
    assert main(["similar", "group_rank(-ts_sum(returns, 10), subindustry)", "--submitted"]) == 0
    assert "A0001" in capsys.readouterr().out
