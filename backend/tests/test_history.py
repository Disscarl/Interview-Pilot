import os
import shutil
import tempfile
from unittest import IsolatedAsyncioTestCase

from services.history import (
    init_db, create_user, get_user_by_username, get_user_by_id,
    save_interview, list_interviews, get_interview, delete_interview,
)
from services.auth import hash_password

REPORT = {"overall_score": 3.5, "summary": "测试报告"}


class HistoryTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp()
        await init_db(os.path.join(self.tmp, "test.db"))

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_user_crud(self):
        uid = await create_user("alice", hash_password("pw1234"))
        self.assertIsNotNone(uid)
        # duplicate username
        self.assertIsNone(await create_user("alice", hash_password("pw1234")))
        u = await get_user_by_username("alice")
        self.assertEqual(u["id"], uid)
        self.assertEqual((await get_user_by_id(uid))["username"], "alice")

    async def test_history_is_scoped_by_user(self):
        a = await create_user("a", "h")
        b = await create_user("b", "h")
        messages = [{"role": "interviewer", "content": "你好", "phase": "intro"}]
        await save_interview("sess_a", "岗位", "公司", messages, REPORT, a)

        # A sees it, B does not
        self.assertEqual(len(await list_interviews(a)), 1)
        self.assertEqual(len(await list_interviews(b)), 0)

        # ownership checks
        self.assertIsNotNone(await get_interview("sess_a", a))
        self.assertIsNone(await get_interview("sess_a", b))

        # B cannot delete A's record, A can
        self.assertFalse(await delete_interview("sess_a", b))
        self.assertTrue(await delete_interview("sess_a", a))
        self.assertEqual(len(await list_interviews(a)), 0)


if __name__ == "__main__":
    unittest.main()
