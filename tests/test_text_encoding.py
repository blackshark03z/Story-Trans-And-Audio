from __future__ import annotations

import unittest

from story_audio.text_encoding import (
    CanonicalTextValidationError,
    TEXT_ENCODING_INVALID,
    validate_canonical_text,
)


def legacy_decode_utf8(text: str) -> str:
    decoded: list[str] = []
    for byte in text.encode("utf-8"):
        try:
            decoded.append(bytes([byte]).decode("cp1252"))
        except UnicodeDecodeError:
            decoded.append(chr(byte))
    return "".join(decoded)


class CanonicalTextEncodingTests(unittest.TestCase):
    def test_valid_vietnamese_is_round_trip_safe(self) -> None:
        validate_canonical_text(
            'Trời vừa sáng. "Chào anh, tôi đã đợi từ sớm."',
            field="chapter",
        )

    def test_legacy_decoded_utf8_is_rejected(self) -> None:
        malformed = legacy_decode_utf8("Trời vừa sáng.")
        with self.assertRaises(CanonicalTextValidationError) as caught:
            validate_canonical_text(malformed, field="chapter")
        self.assertEqual(caught.exception.code, TEXT_ENCODING_INVALID)

    def test_disallowed_controls_and_surrogates_are_rejected(self) -> None:
        for malformed in ("Câu có \u0081 điều khiển.", "Câu có \x00 NUL.", "Câu có \ud800 surrogate."):
            with self.subTest(repr=repr(malformed)), self.assertRaises(
                CanonicalTextValidationError
            ):
                validate_canonical_text(malformed)

    def test_normal_whitespace_controls_remain_allowed(self) -> None:
        validate_canonical_text("Dòng một.\nDòng hai.\r\n\tThụt dòng.")


if __name__ == "__main__":
    unittest.main()
