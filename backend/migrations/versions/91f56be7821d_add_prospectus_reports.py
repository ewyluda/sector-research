"""add prospectus_reports

Revision ID: 91f56be7821d
Revises: 69d806901850
Create Date: 2026-05-20 17:44:36.151131
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '91f56be7821d'
down_revision: Union[str, None] = '69d806901850'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prospectus_reports',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('accession_number', sa.String(length=32), nullable=False),
        sa.Column('issuer_cik', sa.String(length=16), nullable=False),
        sa.Column('issuer_name', sa.String(length=256), nullable=False),
        sa.Column('proposed_ticker', sa.String(length=16), nullable=True),
        sa.Column('theme_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('step_outputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_prospectus_reports_accession_number'),
        'prospectus_reports',
        ['accession_number'],
        unique=False,
    )
    op.create_index(
        op.f('ix_prospectus_reports_issuer_cik'),
        'prospectus_reports',
        ['issuer_cik'],
        unique=False,
    )
    op.create_index(
        op.f('ix_prospectus_reports_theme_id'),
        'prospectus_reports',
        ['theme_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_prospectus_reports_theme_id'), table_name='prospectus_reports')
    op.drop_index(op.f('ix_prospectus_reports_issuer_cik'), table_name='prospectus_reports')
    op.drop_index(op.f('ix_prospectus_reports_accession_number'), table_name='prospectus_reports')
    op.drop_table('prospectus_reports')
