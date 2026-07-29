import base64
import unittest


from app.kimi import AppError, validate_image_data_url


def data_url(mime: str, payload: bytes) -> str:
    return "data:{};base64,{}".format(
        mime,
        base64.b64encode(payload).decode("ascii"),
    )


class ImageValidationTest(unittest.TestCase):
    def test_accepts_matching_jpeg_png_and_webp_magic(self):
        samples = (
            ("image/jpeg", b"\xff\xd8\xff\xe0" + b"x" * 100),
            ("image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 100),
            ("image/webp", b"RIFF\x10\x00\x00\x00WEBP" + b"x" * 100),
        )
        for mime, payload in samples:
            with self.subTest(mime=mime):
                self.assertEqual(
                    mime,
                    validate_image_data_url(data_url(mime, payload)),
                )

    def test_rejects_spoofed_mime_before_model_call(self):
        with self.assertRaises(AppError) as raised:
            validate_image_data_url(
                data_url("image/jpeg", b"not-a-real-image" * 10)
            )
        self.assertEqual("INVALID_IMAGE", raised.exception.code)

    def test_rejects_mime_magic_mismatch_and_invalid_base64(self):
        invalid_values = (
            data_url("image/png", b"\xff\xd8\xff\xe0" + b"x" * 100),
            "data:image/jpeg;base64,***",
        )
        for value in invalid_values:
            with self.subTest(value=value[:30]):
                with self.assertRaises(AppError) as raised:
                    validate_image_data_url(value)
                self.assertEqual("INVALID_IMAGE", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
