import pytest
from sellagent_ai.language import detect, resolve
from sellagent_backend.services.phone import PhoneError, normalize, number_type

pytestmark = pytest.mark.automated


@pytest.mark.parametrize("raw,expected", [("98765 43210", "+919876543210"), ("+91-98765-43210", "+919876543210"), ("09876543210", "+919876543210"), ("0091 9876543210", "+919876543210")])
def test_normalize_indian_numbers(raw, expected):
    assert normalize(raw, "IN") == expected


@pytest.mark.parametrize("raw", ["", "12345", "abcd", "+91 12345"])
def test_invalid_numbers(raw):
    with pytest.raises(PhoneError):
        normalize(raw, "IN")


def test_number_type():
    assert number_type("+919876543210") in ("mobile", "fixed_line_or_mobile")


@pytest.mark.parametrize("text,lang", [("कितना दाम है?", "hi"), ("haan ji bataiye kitna paisa", "hi"), ("How much does it cost?", "en"), ("", "en"), ("price kitna hai", "mixed")])
def test_detect(text, lang):
    assert detect(text) == lang


def test_resolve():
    assert resolve("hi", "en") == "hi" and resolve("auto", "mixed") == "hi" and resolve("auto", "en") == "en"
