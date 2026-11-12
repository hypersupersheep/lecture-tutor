from tutor_any_lecture.citations import parse, resolve


def test_parse_forms():
    kinds = [
        (c.kind, c.start, c.end, c.estimated)
        for c in parse("A (slide 15). B (13:42–14:05). C （1:02:03）. D (~13:40). E (slides 14–16, 40:38)")
    ]
    assert ("slide", "15", None, False) in kinds
    assert ("time", 822.0, 845.0, False) in kinds
    assert ("time", 3723.0, None, False) in kinds
    assert ("time", 820.0, None, True) in kinds


def test_resolve_flags_out_of_range():
    assert resolve(parse("(slide 40) (99:00)"), max_slide=32, duration=5400) == [
        "slide 40 > 32",
        "99:00 > duration 1:30:00",
    ]


def test_resolve_unknown_duration_no_time_errors():
    assert resolve(parse("(99:00)"), max_slide=None, duration=None) == []


def test_parse_linked_timestamp():
    got = [(c.kind, c.start, c.end, c.estimated) for c in parse("(slide 15, [13:42](https://youtu.be/x?t=822s))")]
    assert got == [("slide", "15", None, False), ("time", 822.0, None, False)]
    got = [
        (c.kind, c.start, c.end, c.estimated)
        for c in parse("([13:42](https://v.example/w?t=822s)–14:05) (~[13:40](https://v.example/w?t=820s))")
    ]
    assert got == [("time", 822.0, 845.0, False), ("time", 820.0, None, True)]
