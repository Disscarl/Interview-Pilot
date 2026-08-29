import hashlib
import json
import unittest

from services.auth import (
    hash_password, verify_password, create_token, decode_token, _b64url_decode,
    _PBKDF2_ITERATIONS, _LEGACY_PBKDF2_ITERATIONS,
)


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

    def test_new_hash_embeds_iterations(self):
        # R13: the hash carries its iteration count so it can be raised later
        # without breaking already-stored hashes.
        h = hash_password("secret123")
        parts = h.split("$")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], str(_PBKDF2_ITERATIONS))
        self.assertTrue(verify_password("secret123", h))

    def test_legacy_format_still_verifies(self):
        # Pre-R13 hashes were '<salt_hex>$<hash_hex>' at a fixed 100k rounds —
        # they must keep verifying after the upgrade.
        salt = hashlib.sha256(b"legacy-salt").digest()[:16]
        dk = hashlib.pbkdf2_hmac("sha256", b"secret123", salt, _LEGACY_PBKDF2_ITERATIONS)
        stored = f"{salt.hex()}${dk.hex()}"
        self.assertTrue(verify_password("secret123", stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_three_part_hash_with_bad_iterations(self):
        self.assertFalse(verify_password("x", "abc$deadbeef$cafe"))


class TokenTest(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(decode_token(create_token(42)), 42)

    def test_tampered_signature(self):
        self.assertIsNone(decode_token(create_token(42) + "x"))

    def test_empty_or_malformed(self):
        self.assertIsNone(decode_token(""))
        self.assertIsNone(decode_token("a.b"))

    def test_token_has_iat_and_jti(self):
        # R13: issued-at and token-id claims aid auditing/revocation later.
        token = create_token(7)
        payload = json.loads(_b64url_decode(token.split(".")[1]))
        self.assertEqual(payload["sub"], "7")
        self.assertIn("iat", payload)
        self.assertIn("jti", payload)
        self.assertGreater(payload["exp"], payload["iat"])


if __name__ == "__main__":
    unittest.main()
