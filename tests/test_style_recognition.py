# Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_style_recognition.py -q
import collections

import pytest

from experiments import run_style_recognition as sr


@pytest.fixture(scope="module")
def drafts():
    return sr.load_drafts()


@pytest.fixture(scope="module")
def template():
    return sr.TEMPLATE_PATH.read_text()


def test_all_180_drafts_balanced(drafts):
    assert len(drafts) == 180
    assert collections.Counter(d["writer"] for d in drafts) == {"claude": 60, "gpt55": 60, "gemini": 60}


def test_no_fences_or_tags_in_shown_code(drafts):
    for d in drafts:
        for cond in ("raw", "nocomments"):
            assert "```" not in d[cond]
            assert "<solution>" not in d[cond] and "</solution>" not in d[cond]


def test_prompt_has_no_writer_name_or_label_line(drafts, template):
    for d in drafts:
        for reviewer in sr.REVIEWERS:
            opts = sr.option_order(reviewer, d, "raw", 1)
            p = sr.build_prompt(template, opts, d["raw"])
            assert "written by" not in p.lower().replace("it was written by exactly one", "")
            assert "{" + "code}" not in p and "{option_1}" not in p
            assert p.endswith(d["raw"] + "\n")


def test_option_order_is_permutation_varies_and_reproducible(drafts):
    orders = []
    for d in drafts[:60]:
        o = sr.option_order("claude", d, "raw", 1)
        assert sorted(o) == sorted(sr.OPTIONS)
        assert o == sr.option_order("claude", d, "raw", 1)
        orders.append(tuple(o))
    assert len(set(orders)) >= 4
    firsts = collections.Counter(o[0] for o in orders)
    assert len(firsts) == 3


@pytest.mark.parametrize("text,expected", [
    ("Claude", "Claude"), ("gpt", "GPT"), (" Gemini.\n", "Gemini"), ("**GPT**", "GPT"), ("`Claude`", "Claude"),
    ("Claude or GPT", None), ("I think Gemini", None), ("Gemini wrote it", None), ("", None), ("ChatGPT", None),
])
def test_parser(text, expected):
    assert sr.parse_answer(text) == expected


def test_same_draft_text_for_every_reviewer(drafts, template):
    for d in drafts:
        hashes = {sr.sha256(d["raw"]) for _ in sr.REVIEWERS}
        assert len(hashes) == 1


def test_strip_comments_removes_only_comments_and_docstrings():
    code = 'def f(x):\n    """Doc."""\n    # note\n    y = x + 1  # inline\n    s = "# not a comment"\n\n    return y\n'
    out = sr.strip_comments(code)
    assert "Doc." not in out and "note" not in out and "inline" not in out
    assert 's = "# not a comment"' in out
    assert "    y = x + 1\n" in out + "\n"
    assert "\n\n    return y" in out


def test_nocomments_keeps_code_tokens(drafts):
    import io
    import tokenize
    def code_tokens(src):
        return [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.STRING)]
    for d in drafts:
        assert code_tokens(d["raw"]) == code_tokens(d["nocomments"])


def test_cells_cover_every_draft_reviewer_condition(drafts):
    cells = sr.build_cells(drafts, ["raw", "nocomments"], list(sr.REVIEWERS), sr.repeat_problems(10))
    assert len(cells) == 180 * 3 * 2 + 10 * 3 * 3
    assert len({str(sr.cell_path(c)) for c in cells}) == len(cells)
