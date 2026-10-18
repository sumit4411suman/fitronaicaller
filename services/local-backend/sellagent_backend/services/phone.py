"""Telephone number validation/normalisation (E.164) using libphonenumber."""

from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType


class PhoneError(ValueError):
    pass


def normalize(raw: str, region: str = "IN") -> str:
    raw = (raw or "").strip()
    if not raw:
        raise PhoneError("telephone number is required")
    try:
        num = phonenumbers.parse(raw, region)
    except NumberParseException as exc:
        raise PhoneError(f"invalid telephone number: {exc}") from exc
    if not phonenumbers.is_valid_number(num):
        raise PhoneError("telephone number is not valid for its region")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def number_type(e164: str) -> str:
    try:
        t = phonenumbers.number_type(phonenumbers.parse(e164))
    except NumberParseException:
        return "unknown"
    return {
        PhoneNumberType.MOBILE: "mobile",
        PhoneNumberType.FIXED_LINE: "fixed_line",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
        PhoneNumberType.TOLL_FREE: "toll_free",
        PhoneNumberType.PREMIUM_RATE: "premium_rate",
        PhoneNumberType.VOIP: "voip",
    }.get(t, "other")


def display(e164: str) -> str:
    try:
        return phonenumbers.format_number(phonenumbers.parse(e164), phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except NumberParseException:
        return e164
