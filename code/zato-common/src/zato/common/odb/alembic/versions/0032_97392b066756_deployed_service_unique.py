"""deployed service unique

Revision ID: 97392b066756
Revises: 0031_00ad4c118b99
Create Date: 2017-12-19 16:27:53.399697

"""

# Revision identifiers, used by Alembic.
revision = '0032_97392b066756'
down_revision = '0031_00ad4c118b99'

from alembic import context, op
import sqlalchemy as sa


# Zato
from zato.common.odb import alembic_utils

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('deployed_service', schema=None, naming_convention=alembic_utils.naming_convention) as batch_op:
        batch_op.create_unique_constraint(None, ['server_id', 'service_id'])

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('deployed_service', schema=None, naming_convention=alembic_utils.naming_convention) as batch_op:
        batch_op.drop_constraint(None, type_='unique')

    # ### end Alembic commands ###