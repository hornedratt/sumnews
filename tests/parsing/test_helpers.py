from sumnews.parsing.telegram import _title_from_text, normalize_channel


def test_normalize_channel_forms() -> None:
    assert normalize_channel("@ARPP_Russia") == "ARPP_Russia"
    assert normalize_channel("https://t.me/cipr_russia") == "cipr_russia"
    assert normalize_channel("http://t.me/s/cipr_russia") == "cipr_russia"
    assert normalize_channel("t.me/govru/123?single") == "govru"
    assert normalize_channel("  cipr_russia  ") == "cipr_russia"
    assert normalize_channel("cipr_russia") == "cipr_russia"  # idempotent


def test_title_from_text_first_line() -> None:
    assert _title_from_text("Первая строка\nвторая строка") == "Первая строка"


def test_title_from_text_skips_blank_lines() -> None:
    assert _title_from_text("\n\n  Заголовок  \nтекст") == "Заголовок"


def test_title_from_text_truncates_long() -> None:
    title = _title_from_text("слово " * 40)
    assert len(title) <= 121
    assert title.endswith("…")
