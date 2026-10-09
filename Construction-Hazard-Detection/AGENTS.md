# AGENTS.md

Guidelines for AI coding agents working on the Construction-Hazard-Detection codebase.

## Build / Run / Test Commands

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Main Application
```bash
# Database mode (polls DB for stream configs)
python main.py

# JSON config mode
python main.py --config config/configuration.json

# Custom polling interval
python main.py --poll 5
```

### Run Tests
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run a single test file
pytest tests/src/danger_detector_test.py -v

# Run a single test class
pytest tests/src/danger_detector_test.py::TestDangerDetector -v

# Run a single test method
pytest tests/src/danger_detector_test.py::TestDangerDetector::test_detect_danger -v

# Run tests in parallel
pytest -n auto tests/
```

### Run Individual Services
```bash
# Detection API (port 8000)
uvicorn examples.YOLO_server_api.backend.app:app --host 127.0.0.1 --port 8000

# Violation Records API (port 8002)
uvicorn examples.violation_records.app:app --host 127.0.0.1 --port 8002

# Notification Server (port 8003)
uvicorn examples.local_notification_server.app:app --host 127.0.0.1 --port 8003

# DB Management API (port 8005)
uvicorn examples.db_management.app:app --host 127.0.0.1 --port 8005

# Streaming Web (port 8800)
uvicorn examples.streaming_web.backend.app:app --host 127.0.0.1 --port 8800

# MCP Server
python -m examples.mcp_server.main
```

### Docker
```bash
docker-compose up -d
```

## Code Style Guidelines

### Imports
```python
# 1. Future annotations (always first)
from __future__ import annotations

# 2. Standard library imports (alphabetical)
import asyncio
import json
import os

# 3. Third-party imports (alphabetical, one per line)
from fastapi import FastAPI
from pydantic import BaseModel

# 4. Local imports (alphabetical)
from src.danger_detector import DangerDetector
from src.utils import Utils
```

### Type Hints
- Use Python 3.10+ syntax: `list[dict]`, `str | None`, not `List[Dict]`, `Optional[str]`
- Use `TypedDict` for structured dictionaries
- Always annotate function parameters and return types
- Use `-> None` for functions that don't return a value

```python
from typing import TypedDict

class StreamConfig(TypedDict, total=False):
    video_url: str
    model_key: str
    site: str

def process_data(items: list[dict[str, any]]) -> dict[str, int]:
    ...

async def fetch_config(url: str) -> StreamConfig | None:
    ...
```

### Naming Conventions
- **Functions/Variables**: `snake_case` (e.g., `detect_danger`, `video_url`)
- **Classes**: `PascalCase` (e.g., `DangerDetector`, `StreamCapture`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Private methods**: Prefix with `_` (e.g., `_filter_static_machinery`)
- **Async functions**: No special prefix, use `async def`

### Docstrings
Use Google-style docstrings:

```python
def detect_danger(
    self,
    datas: list[list[float]],
) -> tuple[dict[str, dict[str, int]], list[Polygon], list[Polygon]]:
    """
    Detects potential safety violations in a construction site.

    Args:
        datas: List of detection data with bounding boxes and class IDs.

    Returns:
        A tuple containing:
            - warnings: Dictionary of warning types and counts
            - cone_polygons: List of safety cone polygons
            - pole_polygons: List of utility pole polygons
    """
```

### Error Handling
- Use try-except blocks for expected exceptions
- Log errors before raising or handling
- Use specific exception types, not bare `except:`

```python
try:
    result = await api_client.fetch()
except httpx.HTTPError as e:
    logger.error(f"API request failed: {e}")
    raise RuntimeError(f"Failed to fetch data: {e}") from e
```

### Async Patterns
- Use `asyncio.run()` for async entry points
- Use `async with` for async context managers
- Use `await` for async function calls

```python
async def main() -> None:
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)

if __name__ == '__main__':
    asyncio.run(main())
```

### Class Structure
```python
class ExampleClass:
    """
    Brief description of the class.
    """

    def __init__(self, param: str) -> None:
        """
        Initialize the class.

        Args:
            param: Description of parameter.
        """
        self.param = param
        self.logger = logging.getLogger(__name__)

    def public_method(self) -> dict:
        """Public method description."""
        return self._private_helper()

    def _private_helper(self) -> dict:
        """Private helper method."""
        return {}
```

### Testing Conventions
- Test files: `*_test.py` (e.g., `danger_detector_test.py`)
- Test classes: `Test{ClassName}` (e.g., `TestDangerDetector`)
- Test methods: `test_{description}` (e.g., `test_detect_danger`)
- Use `unittest.TestCase` for test classes
- Use `setUp()` for test fixtures

```python
import unittest
from unittest.mock import patch, MagicMock

class TestDangerDetector(unittest.TestCase):
    """Unit tests for DangerDetector class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.detector = DangerDetector()

    def test_detect_danger_returns_warnings(self) -> None:
        """Test that detect_danger returns expected warnings."""
        data = [[100, 100, 200, 200, 0.95, 5, -1, 0]]
        warnings, _, _ = self.detector.detect_danger(data)
        self.assertIsInstance(warnings, dict)
```

### Environment Variables
- Load with `python-dotenv`: `load_dotenv()`
- Access with `os.getenv()` and provide defaults
- Required variables should raise clear errors if missing

```python
from dotenv import load_dotenv
import os

load_dotenv()

api_url = os.getenv('API_URL') or 'http://127.0.0.1:8000'
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise RuntimeError('DATABASE_URL environment variable is required')
```

### FastAPI Patterns
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(lifespan=global_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(some_router)
```

### MCP Server Tools
```python
from fastmcp import FastMCP

mcp = FastMCP('service-name')

@mcp.tool(
    name='tool_name',
    description='Tool description for AI agents',
)
async def tool_function(param: str) -> dict:
    """
    Extended description.

    Args:
        param: Parameter description.

    Returns:
        Result dictionary.
    """
    return {'result': 'value'}
```

## Project Structure

```
src/                    # Core library modules
  danger_detector.py    # Hazard detection logic
  live_stream_detection.py  # YOLO detection
  utils.py              # Utilities (Redis, geometry)
  notifiers/            # Notification integrations

examples/               # Microservices
  YOLO_server_api/      # Detection API (port 8000)
  streaming_web/        # Streaming server (port 8800)
  mcp_server/           # MCP server for AI agents
  db_management/        # DB management API (port 8005)

tests/                  # Test files mirror src/ structure
  src/
    danger_detector_test.py
  examples/
    mcp_server/
```

## Key Dependencies
- **YOLO**: `ultralytics` for object detection
- **Web**: `fastapi`, `uvicorn`, `httpx`
- **Database**: `asyncmy` (MySQL), `redis`
- **MCP**: `fastmcp` for AI agent tools
- **Testing**: `pytest`, `pytest-cov`, `pytest-xdist`

## Detection Classes (YOLO)
| ID | Label | Description |
|----|-------|-------------|
| 0 | Hardhat | Worker with helmet |
| 2 | NO-Hardhat | Worker without helmet |
| 4 | NO-Safety Vest | Worker without vest |
| 5 | Person | Human detection |
| 6 | Safety Cone | Safety markers |
| 8 | Machinery | Construction equipment |
| 9 | Utility Pole | Power/utility poles |
| 10 | Vehicle | Construction vehicles |