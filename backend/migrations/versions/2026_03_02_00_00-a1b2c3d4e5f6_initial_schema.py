"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-02 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'failed', name='jobstatus'), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('file_name', sa.String(length=128), nullable=False),
        sa.Column('secret_ref', sa.String(length=64), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result_error', sa.Text(), nullable=True),
        sa.Column('result_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_token', sa.String(length=64), nullable=True),
        sa.Column('public', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index('ix_jobs_status_created_at_id', 'jobs', ['status', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_jobs_status_created_at_id', table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_table('jobs')
