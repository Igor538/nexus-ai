"""Workflow graph version history.

Revision ID: 0002_workflow_versions
Revises: 0001_baseline
Create Date: 2026-11-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002_workflow_versions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    if "workflow_versions" in set(inspector.get_table_names()):
        return

    json_type = JSONB() if dialect == "postgresql" else sa.JSON()
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "workflow_id",
            sa.Integer(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("graph", json_type, nullable=False),
        sa.Column("origin", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workflow_id", "version", name="uq_workflow_versions_workflow_version"
        ),
    )
    op.create_index(
        "ix_workflow_versions_id", "workflow_versions", ["id"], unique=False
    )
    op.create_index(
        "ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"], unique=False
    )
    op.create_index(
        "ix_workflow_versions_workflow_version",
        "workflow_versions",
        ["workflow_id", "version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_versions_workflow_version", table_name="workflow_versions")
    op.drop_index("ix_workflow_versions_workflow_id", table_name="workflow_versions")
    op.drop_index("ix_workflow_versions_id", table_name="workflow_versions")
    op.drop_table("workflow_versions")
