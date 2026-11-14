"""Versioned initial relational resources and immutable JSON snapshots."""
from alembic import op
from audience_simulator.repository import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=True)
