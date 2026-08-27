import os
import shutil
import tempfile
from unittest import IsolatedAsyncioTestCase

from services.history import (
    init_db, create_user, get_user_by_username, get_user_by_id,
    save_interview, list_interviews, get_interview, delete_interview, list_progress,
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

    async def test_save_interview_with_none_report(self):
        # Evaluation failure must not lose the transcript row.
        a = await create_user("noreport", "h")
        messages = [{"role": "interviewer", "content": "你好"}]
        await save_interview("sess_none", "岗位", "公司", messages, None, a)
        rec = await get_interview("sess_none", a)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["report"], {})

    async def test_jd_roundtrip_for_reinterview(self):
        a = await create_user("jduser", "h")
        messages = [{"role": "interviewer", "content": "你好"}]
        jd = {
            "profile": {"role_title": "UE开发", "company_name": "某公司", "tech_stack": ["C++", "UE"]},
            "plan": {"summary": "深度考察", "stages": []},
            "candidate": {"skills": ["C++"], "years_of_experience": "3年"},
        }
        await save_interview("sess_jd", "UE开发", "某公司", messages, {"overall_score": 4.0}, a, jd=jd)
        rec = await get_interview("sess_jd", a)
        self.assertEqual(rec["jd"], jd)
        self.assertEqual(rec["jd"]["profile"]["role_title"], "UE开发")

    async def test_legacy_row_without_jd_returns_none(self):
        a = await create_user("legacy", "h")
        await save_interview("sess_legacy", "岗位", "公司", [], {"overall_score": 3.0}, a)
        rec = await get_interview("sess_legacy", a)
        self.assertIsNone(rec["jd"])

    async def test_list_progress_groups(self):
        a = await create_user("prog", "h")
        msg = [{"role": "interviewer", "content": "你好", "phase": "intro"}]
        r1 = {"overall_score": 3.0, "summary": "s",
              "dimension_scores": {"沟通": {"score": 3, "comment": "c"}}}
        r2 = {"overall_score": 4.0, "summary": "s2",
              "dimension_scores": {"沟通": {"score": 4, "comment": "c"}}}
        await save_interview("p1", "UE开发", "某公司", msg, r1, a)
        await save_interview("p2", "UE开发", "某公司", msg, r2, a)
        await save_interview("p3", "后端", "", msg, r1, a)

        groups = await list_progress(a)
        by_role = {g["role_title"]: g for g in groups}
        self.assertEqual(len(by_role), 2)

        ue = by_role["UE开发"]
        self.assertEqual(ue["company_name"], "某公司")
        self.assertEqual(len(ue["attempts"]), 2)
        # oldest first, with parsed dimension scores
        self.assertEqual([t["overall_score"] for t in ue["attempts"]], [3.0, 4.0])
        self.assertEqual(ue["attempts"][0]["dimension_scores"]["沟通"]["score"], 3)

        self.assertEqual(len(by_role["后端"]["attempts"]), 1)

        # other users see nothing
        b = await create_user("prog2", "h")
        self.assertEqual(await list_progress(b), [])


if __name__ == "__main__":
    unittest.main()
