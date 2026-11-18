"""Baseline schema: brings pre-existing installs up to date without data loss.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

import app.models  # noqa: F401
from alembic import op
from app.core.database import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

EMPTY_GRAPH = '{"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}'


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "updated_at" not in columns:
            op.add_column(
                "users",
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )
        if "last_login_at" not in columns:
            op.add_column(
                "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
            )

    if "workflows" in tables:
        columns = {column["name"] for column in inspector.get_columns("workflows")}
        if "version" not in columns:
            op.add_column(
                "workflows",
                sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            )
        if "graph" not in columns:
            json_type = JSONB() if dialect == "postgresql" else sa.JSON()
            op.add_column("workflows", sa.Column("graph", json_type, nullable=True))
            if dialect == "postgresql":
                op.execute(sa.text(f"UPDATE workflows SET graph = '{EMPTY_GRAPH}'::jsonb WHERE graph IS NULL"))
            else:
                op.execute(
                    sa.text("UPDATE workflows SET graph = :graph WHERE graph IS NULL").bindparams(
                        graph=EMPTY_GRAPH
                    )
                )
            if dialect == "postgresql":
                op.alter_column(
                    "workflows",
                    "graph",
                    existing_type=json_type,
                    nullable=False,
                    server_default=sa.text(f"'{EMPTY_GRAPH}'::jsonb"),
                )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_workflows_user_updated "
            "ON workflows (user_id, updated_at DESC)"
        )

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # This baseline only adds data-preserving structures; destructive rollback is
    # intentionally omitted.
    pass
