"""Adaptive Inspection Loop: add severity, review queue, profile versioning, barcode, drift

Revision ID: a1b2c3d4e5f6
Revises: 4fd53c6e9ba4
Create Date: 2026-10-03 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4fd53c6e9ba4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # ── New table: product_profile_versions ────────────────────────────────
    # Must be created BEFORE inspections gets profile_version_id FK
    if 'product_profile_versions' not in existing_tables:
        op.create_table(
            'product_profile_versions',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('product_id', sa.Uuid(), nullable=False),
            sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('reference_image_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('threshold_snapshot', sa.Float(), nullable=False, server_default='0.55'),
            sa.Column('model_status_snapshot', sa.String(length=50), nullable=False, server_default='not_available'),
            sa.Column('change_reason', sa.String(length=255), nullable=True),
            sa.Column('parent_version_id', sa.Uuid(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_profile_versions_product_id_products'), ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['parent_version_id'], ['product_profile_versions.id'], name=op.f('fk_product_profile_versions_parent_version_id'), ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_product_profile_versions')),
        )
        op.create_index(op.f('ix_product_profile_versions_product_id'), 'product_profile_versions', ['product_id'])
        op.create_index(op.f('ix_product_profile_versions_is_active'), 'product_profile_versions', ['is_active'])

    # ── New table: inspection_reviews ──────────────────────────────────────
    if 'inspection_reviews' not in existing_tables:
        op.create_table(
            'inspection_reviews',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('inspection_id', sa.Uuid(), nullable=False),
            sa.Column('ai_decision', sa.Enum('PASS', 'FAIL', 'REVIEW', 'RETAKE', name='decision_enum', native_enum=False), nullable=False),
            sa.Column('human_decision', sa.Enum('PASS', 'FAIL', 'REVIEW', 'RETAKE', name='decision_enum', native_enum=False), nullable=True),
            sa.Column('review_status', sa.Enum('pending', 'accepted', 'rejected', name='review_status_enum', native_enum=False), nullable=False, server_default='pending'),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['inspection_id'], ['inspections.id'], name=op.f('fk_inspection_reviews_inspection_id_inspections'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_inspection_reviews')),
            sa.UniqueConstraint('inspection_id', name=op.f('uq_inspection_reviews_inspection_id')),
        )
        op.create_index(op.f('ix_inspection_reviews_inspection_id'), 'inspection_reviews', ['inspection_id'])
        op.create_index(op.f('ix_inspection_reviews_review_status'), 'inspection_reviews', ['review_status'])

    # ── New table: drift_snapshots ──────────────────────────────────────────
    if 'drift_snapshots' not in existing_tables:
        op.create_table(
            'drift_snapshots',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('product_id', sa.Uuid(), nullable=False),
            sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('window_days', sa.Integer(), nullable=False, server_default='7'),
            sa.Column('inspection_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('rejection_rate', sa.Float(), nullable=False, server_default='0'),
            sa.Column('average_anomaly_score', sa.Float(), nullable=False, server_default='0'),
            sa.Column('review_rate', sa.Float(), nullable=False, server_default='0'),
            sa.Column('override_rate', sa.Float(), nullable=False, server_default='0'),
            sa.Column('drift_status', sa.String(length=30), nullable=False, server_default='stable'),
            sa.Column('worsening_signals', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_drift_snapshots_product_id_products'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_drift_snapshots')),
        )
        op.create_index(op.f('ix_drift_snapshots_product_id'), 'drift_snapshots', ['product_id'])
        op.create_index(op.f('ix_drift_snapshots_drift_status'), 'drift_snapshots', ['drift_status'])

    # ── Alter existing tables ──────────────────────────────────────────────
    prod_cols = {c['name'] for c in insp.get_columns('products')}
    if 'barcode' not in prod_cols:
        op.add_column('products', sa.Column('barcode', sa.String(length=255), nullable=True))
        try:
            op.create_index(op.f('ix_products_barcode'), 'products', ['barcode'])
            op.create_unique_constraint(op.f('uq_products_barcode'), 'products', ['barcode'])
        except Exception:
            pass

    # inspections: add new columns
    insp_cols = {c['name'] for c in insp.get_columns('inspections')}
    if 'operational_severity' not in insp_cols:
        op.add_column('inspections', sa.Column('operational_severity',
            sa.Enum('NONE', 'MINOR', 'MODERATE', 'CRITICAL', 'UNKNOWN',
                    name='operational_severity_enum', native_enum=False),
            nullable=False, server_default='UNKNOWN'))
    if 'quality_check_status' not in insp_cols:
        op.add_column('inspections', sa.Column('quality_check_status',
            sa.Enum('good', 'uncertain', 'poor', 'not_run',
                    name='quality_check_status_enum', native_enum=False),
            nullable=False, server_default='not_run'))
    if 'quality_score' not in insp_cols:
        op.add_column('inspections', sa.Column('quality_score', sa.Float(), nullable=True))
    if 'quality_issues' not in insp_cols:
        op.add_column('inspections', sa.Column('quality_issues', sa.Text(), nullable=True))
    if 'conformity_summary' not in insp_cols:
        op.add_column('inspections', sa.Column('conformity_summary', sa.Text(), nullable=True))
    if 'batch_id' not in insp_cols:
        op.add_column('inspections', sa.Column('batch_id', sa.String(length=100), nullable=True))
    if 'shift' not in insp_cols:
        op.add_column('inspections', sa.Column('shift', sa.String(length=50), nullable=True))
    if 'profile_version_id' not in insp_cols:
        op.add_column('inspections', sa.Column('profile_version_id', sa.Uuid(), nullable=True))
        try:
            op.create_foreign_key(
                op.f('fk_inspections_profile_version_id_product_profile_versions'),
                'inspections', 'product_profile_versions',
                ['profile_version_id'], ['id'],
                ondelete='SET NULL'
            )
        except Exception:
            pass

    # Add RETAKE value to decision_enum (PostgreSQL ALTER TYPE)
    try:
        op.execute("ALTER TYPE decision_enum ADD VALUE IF NOT EXISTS 'RETAKE'")
    except Exception:
        pass


def downgrade() -> None:
    # Remove columns from inspections
    op.drop_column('inspections', 'profile_version_id')
    op.drop_column('inspections', 'shift')
    op.drop_column('inspections', 'batch_id')
    op.drop_column('inspections', 'conformity_summary')
    op.drop_column('inspections', 'quality_issues')
    op.drop_column('inspections', 'quality_score')
    op.drop_column('inspections', 'quality_check_status')
    op.drop_column('inspections', 'operational_severity')

    # Remove barcode from products
    try:
        op.drop_constraint(op.f('uq_products_barcode'), 'products', type_='unique')
    except Exception:
        pass
    op.drop_index(op.f('ix_products_barcode'), table_name='products')
    op.drop_column('products', 'barcode')

    # Drop new tables
    op.drop_table('drift_snapshots')
    op.drop_index(op.f('ix_inspection_reviews_review_status'), table_name='inspection_reviews')
    op.drop_index(op.f('ix_inspection_reviews_inspection_id'), table_name='inspection_reviews')
    op.drop_table('inspection_reviews')
    op.drop_index(op.f('ix_product_profile_versions_is_active'), table_name='product_profile_versions')
    op.drop_index(op.f('ix_product_profile_versions_product_id'), table_name='product_profile_versions')
    op.drop_table('product_profile_versions')
