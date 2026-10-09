from __future__ import annotations

import os
from pathlib import Path
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_limiter import FastAPILimiter

from examples.auth.cache import _DEFAULT_SERVICE
from examples.auth.database import engine
from examples.auth.jwt_scheduler import start_jwt_scheduler
from examples.auth.models import Base
from examples.auth.redis_pool import RedisClient


async def _ensure_violations_site_fk_on_update_cascade(conn) -> None:
    try:
        fk_row = (
            await conn.exec_driver_sql(
                """
                SELECT k.CONSTRAINT_NAME
                FROM information_schema.KEY_COLUMN_USAGE k
                WHERE k.CONSTRAINT_SCHEMA = DATABASE()
                  AND k.TABLE_NAME = 'violations'
                  AND k.COLUMN_NAME = 'site'
                  AND k.REFERENCED_TABLE_NAME = 'sites'
                  AND k.REFERENCED_COLUMN_NAME = 'name'
                LIMIT 1
                """,
            )
        ).first()
        if not fk_row:
            return

        fk_name = fk_row[0]
        update_rule_row = (
            await conn.exec_driver_sql(
                """
                SELECT rc.UPDATE_RULE
                FROM information_schema.REFERENTIAL_CONSTRAINTS rc
                WHERE rc.CONSTRAINT_SCHEMA = DATABASE()
                  AND rc.CONSTRAINT_NAME = %s
                LIMIT 1
                """,
                (fk_name,),
            )
        ).first()
        if update_rule_row and update_rule_row[0] == 'CASCADE':
            return

        try:
            await conn.exec_driver_sql(
                "ALTER TABLE sites ADD UNIQUE KEY uq_sites_name (name)",
            )
        except Exception:
            pass

        await conn.exec_driver_sql(
            f"ALTER TABLE violations DROP FOREIGN KEY `{fk_name}`",
        )
        await conn.exec_driver_sql(
            (
                f"ALTER TABLE violations ADD CONSTRAINT `{fk_name}` "
                "FOREIGN KEY (`site`) REFERENCES `sites`(`name`) "
                "ON DELETE CASCADE ON UPDATE CASCADE"
            ),
        )
    except Exception:
        pass


async def _ensure_work_ticket_tables(conn) -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / 'db_management'
        / 'work_ticket_schema.sql'
    )
    script = schema_path.read_text(encoding='utf-8')
    for statement in (part.strip() for part in script.split(';')):
        if statement:
            await conn.exec_driver_sql(statement)


async def _ensure_camera_stream_fk(conn) -> None:
    existing = (
        await conn.exec_driver_sql(
            """
            SELECT 1
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = 'cameras'
              AND COLUMN_NAME = 'stream_config_id'
              AND REFERENCED_TABLE_NAME = 'stream_configs'
            LIMIT 1
            """,
        )
    ).first()
    if existing:
        return
    try:
        await conn.exec_driver_sql(
            """
            ALTER TABLE cameras
            ADD CONSTRAINT fk_camera_stream_config
            FOREIGN KEY (stream_config_id) REFERENCES stream_configs(id)
            ON DELETE SET NULL
            """,
        )
    except Exception:
        # Service-layer validation still prevents invalid mappings if a legacy
        # database contains rows that make the FK migration impossible.
        pass


@asynccontextmanager
async def global_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Provide a global lifespan manager for the FastAPI application.

    Args:
        app (FastAPI): The FastAPI application instance to
            manage resources for.

    Yields:
        None: Control is yielded back to the application
            after performing startup tasks.
    """
    # Start the scheduler (e.g., for rotating JWT secret keys).
    scheduler = start_jwt_scheduler(app)

    # Initialise Redis connection and rate limiter.
    redis_host: str = os.getenv('REDIS_HOST', '127.0.0.1')
    redis_port: str = os.getenv('REDIS_PORT', '6379')
    redis_password: str = os.getenv('REDIS_PASSWORD', '')
    redis_url: str = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"

    app.state.redis_client = RedisClient(redis_url)
    redis_conn = await app.state.redis_client.connect()
    await FastAPILimiter.init(redis_conn)

    # Preload Lua scripts into Redis (if any).
    try:
        await _DEFAULT_SERVICE.preload_script(redis_conn)
    except Exception:
        # Log the error or handle it as needed
        pass

    # Optionally create database tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_violations_site_fk_on_update_cascade(conn)
        await _ensure_work_ticket_tables(conn)
        await _ensure_camera_stream_fk(conn)
        for stmt in (
            "ALTER TABLE stream_configs ADD COLUMN active_ticket_no VARCHAR(120) NULL",
            "ALTER TABLE stream_configs ADD COLUMN active_from DATETIME NULL",
            "ALTER TABLE stream_configs ADD COLUMN active_to DATETIME NULL",
            "ALTER TABLE violations ADD COLUMN agent_report TEXT NULL",
            "ALTER TABLE cameras ADD COLUMN ip_address VARCHAR(45) NULL AFTER monitor_area",
            "ALTER TABLE cameras ADD INDEX idx_camera_ip (ip_address)",
        ):
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass

    # -- All startup logic completed --
    yield  # Provide control back to the application

    # -- Shutdown logic --
    scheduler.shutdown()
    await app.state.redis_client.close()
    # Close database engine if needed
    await engine.dispose()
