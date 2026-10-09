from __future__ import annotations

import os
import unittest
from datetime import datetime
from datetime import timezone
from typing import ClassVar
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi_jwt import JwtAuthorizationCredentials

from examples.auth.database import get_db
from examples.auth.jwt_config import jwt_access
from examples.auth.models import Site
from examples.auth.models import User
from examples.auth.models import Violation
from examples.violation_records.app import app
from examples.violation_records.app import main


class TestViolationRecordsApp(unittest.IsolatedAsyncioTestCase):
    """
    Collection of test cases for the violation_records FastAPI application.
    """

    # Class variable to hold the test client.
    client: ClassVar[TestClient]

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up the test client and override the JWT dependency for testing.
        """
        super().setUpClass()

        def override_jwt() -> JwtAuthorizationCredentials:
            """
            Mock implementation of the jwt_access dependency for testing.
            """
            return JwtAuthorizationCredentials(
                subject={'username': 'test_user'},
            )

        # Override the jwt_access dependency with a mock implementation.
        app.dependency_overrides[jwt_access] = override_jwt

        # Create a test client for the application.
        cls.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_db, None)
        return super().tearDown()

    @patch('uvicorn.run')
    def test_run_uvicorn(self, mock_uvicorn_run: MagicMock) -> None:
        """
        Test the main function to ensure it runs the FastAPI application with
        Uvicorn.

        Args:
            mock_uvicorn_run (MagicMock): Mock object for the Uvicorn run
                function.
        """
        main()
        mock_uvicorn_run.assert_called_once_with(
            'examples.violation_records.app:app',
            host='0.0.0.0',
            port=8081,
            reload=True,
        )

    async def test_violations_intent_fallback_mode(self) -> None:
        user_obj = User(
            id=1,
            username='test_user',
            password_hash='x',
            role='user',
            is_active=True,
        )
        user_obj.sites = [
            Site(id=1, name='Alpha'),
            Site(id=2, name='Beta'),
        ]

        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = user_obj
        db.execute.return_value = result

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db

        with patch.dict(
            os.environ,
            {
                'VIOLATION_INTENT_LLM_MODE': 'off',
                'ALIYUN_BASE_URL': '',
                'ALIYUN_API_KEY': '',
                'ALIYUN_MODEL_NAME': '',
            },
            clear=False,
        ):
            resp = self.client.get(
                '/violations/intent',
                params={'user_query': '去 Alpha 查未戴安全帽'},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['site_ids'], [1])
        self.assertEqual(data['site_names'], ['Alpha'])
        self.assertEqual(data['query_mode'], 'search')
        self.assertIsNone(data['start_time'])
        self.assertIsNone(data['end_time'])

    async def test_violations_intent_llm_mode_openai_compatible(self) -> None:
        user_obj = User(
            id=1,
            username='test_user',
            password_hash='x',
            role='user',
            is_active=True,
        )
        user_obj.sites = [
            Site(id=1, name='Alpha'),
            Site(id=2, name='Beta'),
        ]

        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = user_obj
        db.execute.return_value = result

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db

        async def fake_openai_call(**kwargs) -> str:
            return (
                '{"site_ids":[2],"keyword":"未戴安全帽",'
                '"start_time":null,"end_time":null,"query_mode":"search","confidence":0.9}'
            )

        with (
            patch.dict(
                os.environ,
                {
                    'VIOLATION_INTENT_LLM_MODE': 'openai_compatible',
                    'ALIYUN_BASE_URL': 'https://example.com/v1',
                    'ALIYUN_API_KEY': 'sk-test',
                    'ALIYUN_MODEL_NAME': 'qwen',
                },
                clear=False,
            ),
            patch(
                'examples.violation_records.routers.call_openai_compatible',
                new=fake_openai_call,
            ),
        ):
            resp = self.client.get(
                '/violations/intent',
                params={'user_query': '帮我查 Beta 未戴安全帽'},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['site_ids'], [2])
        self.assertEqual(data['site_names'], ['Beta'])
        self.assertEqual(data['keyword'], '未戴安全帽')
        self.assertEqual(data['query_mode'], 'search')
        self.assertAlmostEqual(data['confidence'], 0.9)

    async def test_violations_summary_llm_mode_openai_compatible(self) -> None:
        db = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        now = datetime.now(timezone.utc)
        v1 = Violation(
            id=1,
            site='Alpha',
            stream_name='Cam1',
            image_path='x.png',
            detection_time=now,
        )
        v2 = Violation(
            id=2,
            site='Alpha',
            stream_name='Cam2',
            image_path='y.png',
            detection_time=now,
        )
        samples_result = MagicMock()
        samples_result.scalars.return_value.all.return_value = [v1, v2]

        db.execute.side_effect = [count_result, samples_result]

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db

        async def fake_openai_call(**kwargs) -> str:
            return 'LLM summary'

        async def fake_get_user_sites_cached(username: str, db) -> list[str]:
            return ['Alpha']

        with (
            patch.dict(
                os.environ,
                {
                    'VIOLATION_SUMMARY_LLM_MODE': 'openai_compatible',
                    'ALIYUN_BASE_URL': 'https://example.com/v1',
                    'ALIYUN_API_KEY': 'sk-test',
                    'ALIYUN_MODEL_NAME': 'qwen',
                },
                clear=False,
            ),
            patch(
                'examples.violation_records.routers.call_openai_compatible',
                new=fake_openai_call,
            ),
            patch(
                'examples.violation_records.routers.get_user_sites_cached',
                new=fake_get_user_sites_cached,
            ),
        ):
            resp = self.client.get(
                '/violations/summary',
                params={'user_query': '今天 Alpha 情况怎么样'},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['summary'], 'LLM summary')
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['sample_count'], 2)


if __name__ == '__main__':
    unittest.main()

'''
pytest \
    --cov=examples.violation_records.app \
    --cov-report=term-missing tests/examples/violation_records/app_test.py
'''
