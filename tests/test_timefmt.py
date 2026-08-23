from src.timefmt import span_12h, to_12h


def test_afternoon():
    assert to_12h("17:00") == "5:00 PM"


def test_morning():
    assert to_12h("09:30") == "9:30 AM"


def test_noon_and_midnight():
    assert to_12h("12:00") == "12:00 PM"
    assert to_12h("00:15") == "12:15 AM"


def test_span_drops_repeated_meridiem():
    assert span_12h("17:00", "18:30") == "5:00-6:30 PM"


def test_span_keeps_both_when_they_differ():
    assert span_12h("11:20", "12:00") == "11:20 AM-12:00 PM"
