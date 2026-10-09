from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_limiter import FastAPILimiter

from examples.auth.database import get_db
from examples.auth.jwt_config import jwt_access
from examples.auth.redis_pool import get_redis_pool
from examples.auth.redis_pool import get_redis_pool_ws
from examples.streaming_web.backend.utils import Utils
from examples.streaming_web.backend.routers import rate_limiter_index
from examples.streaming_web.backend.routers import rate_limiter_label
from examples.streaming_web.backend.routers import router


class TestRouters(unittest.IsolatedAsyncioTestCase):
    """Test suite for FastAPI routers.

    This suite validates behaviour for the following endpoints:

    - GET /api/labels
    - POST /api/frames
    - WS  /api/ws/labels/{label}
    - WS  /api/ws/stream/{label}/{key}
    - WS  /api/ws/frames

    Attributes:
        app: The in-memory FastAPI application under test.
        fake_redis: Async mock used to stand in for the Redis pool.
        mock_db_session: Async mock simulating the database session.
        client: Test client for driving HTTP and WebSocket requests.
    """

    app: FastAPI
    fake_redis: AsyncMock
    mock_db_session: AsyncMock
    client: TestClient

    def setUp(self) -> None:
        """Initialise the app and mock dependencies.

        This method wires dependency overrides so that networked
        integrations (Redis, DB, rate limiting, and JWT credentials)
        are replaced by test doubles.
        """
        self.app = FastAPI()
        self.app.include_router(router, prefix='/api')

        # Mock Redis
        self.fake_redis = AsyncMock()
        self.fake_redis.scan_iter.return_value = []

        # Mock DB
        self.mock_db_session = AsyncMock()

        # Overrides
        self.app.dependency_overrides[get_redis_pool] = lambda: self.fake_redis
        self.app.dependency_overrides[get_redis_pool_ws] = lambda: self.fake_redis
        self.app.dependency_overrides[get_db] = lambda: self.mock_db_session

        # Mock Rate Limiters to do nothing
        self.app.dependency_overrides[rate_limiter_index] = lambda: None
        self.app.dependency_overrides[rate_limiter_label] = lambda: None

        # Mock JWT
        # We simulate a successful decode that returns a mock credentials object.
        mock_creds = SimpleNamespace()
        mock_creds.subject = {'username': 'testuser'}
        self.app.dependency_overrides[jwt_access] = lambda: mock_creds

        # Set up default mock user and result for database queries
        self.setup_default_db_mocks()

        # Init FastAPILimiter (mocked redis)
        # We need to ensure it doesn't actually try to connect.
        # However, since we override the dependency that uses it, it might be fine.
        # But routers.py uses dependencies=[Depends(rate_limiter_index)].
        # We overrode rate_limiter_index above.

        self.client = TestClient(self.app)

    async def asyncSetUp(self) -> None:
        """
        Setup async context if needed.
        FastAPILimiter needs initialization but we are mocking the dependency.
        """
        pass

    def setup_default_db_mocks(self) -> None:
        """Set up default mock user and site for database queries.

        Prepares a default user in the mocked session so tests that do not
        explicitly tailor the user can proceed without additional setup.

        Returns:
            None
        """
        # Create default mock site and user
        mock_site = MagicMock()
        mock_site.name = 'label1'
        mock_user = MagicMock()
        mock_user.role = 'admin'
        mock_user.sites = [mock_site]

        # Create mock result for database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user

        # Configure the mock session to return this result
        self.mock_db_session.execute.return_value = mock_result

    def tearDown(self) -> None:
        """Clear all dependency overrides after each test.

        Ensures state does not leak between test cases.

        Returns:
            None
        """
        self.app.dependency_overrides.clear()

    # -----------------------------
    # Test GET /api/labels
    # -----------------------------
    @patch(
        'examples.streaming_web.backend.routers.get_user_and_sites',
        new_callable=AsyncMock,
    )
    def test_get_labels_success(
        self,
        mock_get_user_and_sites: AsyncMock,
    ) -> None:
        """Test successful retrieval of labels for admin users."""
        mock_user = SimpleNamespace()
        mock_user.role = 'admin'
        mock_get_user_and_sites.return_value = (
            mock_user,
            ['label1', 'label2'],
            'admin',
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [('label2',), ('label1',)]
        self.mock_db_session.execute.return_value = mock_result

        response = self.client.get('/api/labels')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'labels': ['label1', 'label2']})

    @patch(
        'examples.streaming_web.backend.routers.get_user_and_sites',
        new_callable=AsyncMock,
    )
    def test_get_labels_with_non_admin_user(
        self,
        mock_get_user_and_sites: AsyncMock,
    ) -> None:
        """Test label retrieval for non-admin users."""
        mock_user = SimpleNamespace()
        mock_user.role = 'user'
        mock_get_user_and_sites.return_value = (
            mock_user,
            ['label2', 'label1', '', None],
            'user',
        )

        response = self.client.get('/api/labels')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'labels': ['label1', 'label2']})

    @patch(
        'examples.streaming_web.backend.routers.get_user_and_sites',
        new_callable=AsyncMock,
    )
    def test_get_labels_error(
        self,
        mock_get_user_and_sites: AsyncMock,
    ) -> None:
        """Test error handling in labels endpoint."""
        mock_get_user_and_sites.side_effect = Exception('DB error')

        response = self.client.get('/api/labels')

        self.assertEqual(response.status_code, 500)
        self.assertIn('Failed to fetch labels', response.json()['detail'])

    def test_get_labels_invalid_token(self) -> None:
        """Test labels endpoint with invalid token."""
        # Override JWT to return invalid credentials
        mock_credentials = SimpleNamespace(subject={})
        self.app.dependency_overrides[jwt_access] = lambda: mock_credentials

        response = self.client.get('/api/labels')

        self.assertEqual(response.status_code, 401)
        self.assertIn('Invalid token', response.json()['detail'])

    # -----------------------------
    # Test DELETE /api/simulator/cleanup
    # -----------------------------
    @patch(
        'examples.streaming_web.backend.routers.get_user_and_sites',
        new_callable=AsyncMock,
    )
    def test_cleanup_simulator_streams_success(
        self,
        mock_get_user_and_sites: AsyncMock,
    ) -> None:
        mock_get_user_and_sites.return_value = (
            SimpleNamespace(),
            ['label1'],
            'admin',
        )

        encoded_label = Utils.encode('label1')
        encoded_demo = Utils.encode('DEMO-CAM-05')
        encoded_real = Utils.encode('test_2')
        demo_key = f"stream_frame:{encoded_label}|{encoded_demo}".encode('utf-8')
        real_key = f"stream_frame:{encoded_label}|{encoded_real}".encode('utf-8')

        self.fake_redis.scan = AsyncMock(return_value=(0, [demo_key, real_key]))
        self.fake_redis.delete = AsyncMock(return_value=1)

        response = self.client.delete(
            '/api/simulator/cleanup',
            params={'label': 'label1'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['deleted_keys'], 1)
        self.assertEqual(body['deleted_streams'], ['DEMO-CAM-05'])

    @patch(
        'examples.streaming_web.backend.routers.get_user_and_sites',
        new_callable=AsyncMock,
    )
    def test_cleanup_simulator_streams_permission_denied(
        self,
        mock_get_user_and_sites: AsyncMock,
    ) -> None:
        mock_get_user_and_sites.return_value = (
            SimpleNamespace(),
            ['other_label'],
            'user',
        )

        response = self.client.delete(
            '/api/simulator/cleanup',
            params={'label': 'label1'},
        )
        self.assertEqual(response.status_code, 403)

    # -----------------------------
    # Test GET /api/config
    # -----------------------------
    @patch(
        'examples.streaming_web.backend.routers._try_load_file_config',
    )
    @patch(
        'examples.streaming_web.backend.routers._fetch_db_config',
        new_callable=AsyncMock,
    )
    def test_get_config_fallback_when_redis_has_empty_config(
        self,
        mock_fetch_db_config: AsyncMock,
        mock_try_load_file_config: MagicMock,
    ) -> None:
        self.fake_redis.get.return_value = b'{"config": []}'
        mock_fetch_db_config.return_value = []
        # Simulate File returning config
        mock_try_load_file_config.return_value = [
            {
                'site': 'Kaohsiung',
                'stream_name': 'Test',
                'video_url': 'https://example.invalid/stream',
                'model_key': 'yolo11n',
                'detect_with_server': True,
                'expire_date': '2024-12-31T23:59:59',
            },
        ]

        response = self.client.get('/api/config')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('config', payload)
        self.assertEqual(len(payload['config']), 1)
        self.assertEqual(payload['config'][0]['site'], 'Kaohsiung')
        # Since we mocked _try_load_file_config to return raw dict without normalization logic (which is inside the real function),
        # we expect the raw value here.
        self.assertEqual(payload['config'][0]['expire_date'], '2024-12-31T23:59:59')

    @patch('examples.streaming_web.backend.routers.get_user_and_sites')
    def test_set_config_allows_non_admin(self, mock_get_user_and_sites: AsyncMock) -> None:
        mock_user = SimpleNamespace()
        mock_user.role = 'user'
        mock_get_user_and_sites.return_value = (mock_user, [], 'user')

        payload_data = {"config": []}

        response = self.client.post('/api/config', json=payload_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    @patch('examples.streaming_web.backend.routers.get_user_and_sites')
    def test_set_config_redis_failure(self, mock_get_user_and_sites: AsyncMock) -> None:
        # Simulate user with admin role
        mock_user = SimpleNamespace()
        mock_user.role = 'admin'
        mock_get_user_and_sites.return_value = (mock_user, [], 'admin')

        # Mock Redis set to raise exception
        self.fake_redis.set.side_effect = Exception("Connection refused")

        payload_data = {"config": []}
        
        response = self.client.post('/api/config', json=payload_data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    # -----------------------------
    # Test POST /api/frames
    # -----------------------------
    @patch(
        'examples.streaming_web.backend.routers.store_to_redis',
        new_callable=AsyncMock,
    )
    def test_post_frame_success(self, mock_store_to_redis: AsyncMock) -> None:
        """Test successful frame upload."""
        mock_store_to_redis.return_value = None

        response = self.client.post(
            '/api/frames',
            data={
                'label': 'test_label',
                'key': 'test_key',
                'warnings_json': '[]',
                'cone_polygons_json': '[]',
                'pole_polygons_json': '[]',
                'detection_items_json': '[]',
                'width': '100',
                'height': '100',
            },
            files={'file': ('test.jpg', b'fake_image_data', 'image/jpeg')},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'status': 'ok', 'message': 'Frame stored successfully.'},
        )

    @patch(
        'examples.streaming_web.backend.routers.store_to_redis',
        new_callable=AsyncMock,
    )
    def test_post_frame_error(self, mock_store_to_redis: AsyncMock) -> None:
        """Test error handling in frame upload."""
        mock_store_to_redis.side_effect = Exception('Redis error')

        response = self.client.post(
            '/api/frames',
            data={
                'label': 'test_label',
                'key': 'test_key',
                'warnings_json': '[]',
                'cone_polygons_json': '[]',
                'pole_polygons_json': '[]',
                'detection_items_json': '[]',
                'width': '100',
                'height': '100',
            },
            files={'file': ('test.jpg', b'fake_image_data', 'image/jpeg')},
        )

        self.assertEqual(response.status_code, 500)
        self.assertIn('Failed to store frame', response.json()['detail'])

    # -----------------------------
    # Test WebSocket endpoints (basic endpoint existence)
    # -----------------------------
    def test_websocket_endpoints_exist(self) -> None:
        """Test that WebSocket endpoints are properly defined in the router."""
        # Check that the router has the WebSocket routes
        routes = [route for route in self.app.routes]
        websocket_paths = [
            route.path for route in routes
            if hasattr(route, 'path') and route.path.startswith('/api/ws/')
        ]

        expected_paths = [
            '/api/ws/labels/{label}',
            '/api/ws/stream/{label}/{key}',
            '/api/ws/frames',
        ]

        for expected_path in expected_paths:
            self.assertIn(expected_path, websocket_paths)

    # -----------------------------
    # Test WebSocket handler calls
    # -----------------------------
    @patch(
        'examples.streaming_web.backend.routers.handle_label_stream_ws',
        new_callable=AsyncMock,
    )
    async def test_websocket_label_stream_handler_called(
        self, mock_handle: AsyncMock,
    ) -> None:
        """Test that label stream WebSocket calls the handler."""
        from examples.streaming_web.backend.routers import (
            websocket_label_stream,
        )

        mock_websocket = AsyncMock()
        mock_handle.return_value = None

        await websocket_label_stream(
            websocket=mock_websocket,
            label='test_label',
            rds=self.fake_redis,
        )

        mock_handle.assert_called_once()

    @patch(
        'examples.streaming_web.backend.routers.handle_stream_ws',
        new_callable=AsyncMock,
    )
    async def test_websocket_stream_handler_called(
        self, mock_handle: AsyncMock,
    ) -> None:
        """Test that stream WebSocket calls the handler."""
        from examples.streaming_web.backend.routers import websocket_stream

        mock_websocket = AsyncMock()
        mock_handle.return_value = None

        await websocket_stream(
            websocket=mock_websocket,
            label='test_label',
            key='test_key',
            rds=self.fake_redis,
        )

        mock_handle.assert_called_once()

    @patch(
        'examples.streaming_web.backend.routers.handle_frames_ws',
        new_callable=AsyncMock,
    )
    async def test_websocket_frames_handler_called(
        self, mock_handle: AsyncMock,
    ) -> None:
        """Test that frames WebSocket calls the handler."""
        from examples.streaming_web.backend.routers import websocket_frames

        mock_websocket = AsyncMock()
        mock_handle.return_value = None

        await websocket_frames(
            websocket=mock_websocket,
            rds=self.fake_redis,
        )

        mock_handle.assert_called_once()


if __name__ == '__main__':
    unittest.main()


'''
pytest \
    --cov=examples.streaming_web.backend.routers \
    --cov-report=term-missing \
    tests/examples/streaming_web/backend/routers_test_new.py
'''
