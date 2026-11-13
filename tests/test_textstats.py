import re
from pathlib import Path

import pytest

from tutor_any_lecture.textstats import char_jaccard, containment, ngrams, units


def test_units_cjk_vs_en():
    assert units("离散复利 compound", "zh") == 4 and units("compound interest grows", "en") == 3


def test_units_excludes_latex_code_urls():
    # counted words: The, rate, is, 5, at, b
    assert units("The rate $r$ is 5% at https://example.org/a b `x = 1`", "en") == 6


def test_ngrams_and_containment():
    assert ngrams("Compound interest grows fast.", "en") == {"compound interest", "interest grows", "grows fast"}
    assert ngrams("离散复利", "zh") == {"离散复", "散复利"}
    assert containment("Interest grows", "Compound interest grows fast.", "en") == 1.0
    # A = {离散复, 散复利, 复利很, 利很快}; two of the four are in B
    assert containment("离散复利很快", "离散复利", "zh") == 0.5


def test_char_jaccard_keeps_punctuation():
    # 19 and 20 distinct 3-grams, 18 shared, 21 in the union
    assert char_jaccard("What is a martingale?", "What is a martingale ?") == pytest.approx(18 / 21)



def test_word_jaccard_is_gone():
    from tutor_any_lecture import textstats

    assert not hasattr(textstats, "jaccard")


def test_no_cross_module_private_imports():
    package = Path(__file__).resolve().parents[1] / "src" / "tutor_any_lecture"
    files = sorted(package.rglob("*.py"))
    assert files
    pattern = re.compile(r"from \.[\w.]* import .*\b_[a-z]")
    offenders = [
        f"{f.name}:{n}"
        for f in files
        for n, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1)
        if pattern.search(line)
    ]
    assert offenders == []
