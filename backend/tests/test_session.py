"""Tests for SessionManager per-session locks (L10)."""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase

from services.session import SessionManager


class SessionLockTest(IsolatedAsyncioTestCase):
    async def test_get_lock_is_idempotent_per_session(self):
        m = SessionManager()
        l1 = await m.get_lock("s1")
        l2 = await m.get_lock("s1")
        self.assertIs(l1, l2)
        # Different sessions get different locks.
        l3 = await m.get_lock("s2")
        self.assertIsNot(l1, l3)

    async def test_delete_clears_lock(self):
        m = SessionManager()
        l1 = await m.get_lock("s1")
        await m.delete("s1")
        l2 = await m.get_lock("s1")
        self.assertIsNot(l1, l2)

    async def test_lock_actually_serializes(self):
        """Two concurrent critical sections on the same session never overlap."""
        m = SessionManager()
        lock = await m.get_lock("s1")
        order: list[str] = []

        async def section(name: str):
            async with lock:
                order.append(name + ":in")
                await asyncio.sleep(0.01)
                order.append(name + ":out")

        await asyncio.gather(section("a"), section("b"))
        # Serialized: each section's :in/:out pair is contiguous (no interleaving).
        names = [o.split(":")[0] for o in order]
        self.assertEqual(names[0], names[1])
        self.assertEqual(names[2], names[3])
        self.assertNotEqual(names[0], names[2])


if __name__ == "__main__":
    unittest.main()
