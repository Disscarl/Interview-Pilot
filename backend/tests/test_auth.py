import unittest

from services.auth import hash_password, verify_password, create_token, decode_token


class PasswordTest(unittest.TestCase):
    def test_roundtrip(self):
        h = hash_password("secret123")
        self.assertTrue(verify_password("secret123", h))

    def test_wrong_password(self):
        h = hash_password("secret123")
        self.assertFalse(verify_password("wrong", h))

    def test_salt_is_random(self):
        self.assertNotEqual(hash_password("same"), hash_password("same"))

    def test_malformed_hash(self):
        self.assertFalse(verify_password("x", "not-a-valid-hash"))


class TokenTest(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(decode_token(create_token(42)), 42)

    def test_tampered_signature(self):
        self.assertIsNone(decode_token(create_token(42) + "x"))

    def test_empty_or_malformed(self):
        self.assertIsNone(decode_token(""))
        self.assertIsNone(decode_token("a.b"))


if __name__ == "__main__":
    unittest.main()
