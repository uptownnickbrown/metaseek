"""empty message

Revision ID: 9b059ec9b083
Revises: 3042244d8e87
Create Date: 2017-06-28 22:43:31.437205

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '9b059ec9b083'
down_revision = '3042244d8e87'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('dataset_to_nuccore')
    op.drop_table('nuccore')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('nuccore',
    sa.Column('id', mysql.INTEGER(display_width=11), nullable=False),
    sa.Column('nuccore_uid', mysql.VARCHAR(length=50), nullable=True),
    sa.Column('nuccore_link', mysql.TEXT(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    mysql_default_charset=u'utf8',
    mysql_engine=u'InnoDB'
    )
    op.create_table('dataset_to_nuccore',
    sa.Column('dataset_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=True),
    sa.Column('nuccore_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], [u'dataset.id'], name=u'dataset_to_nuccore_ibfk_1'),
    sa.ForeignKeyConstraint(['nuccore_id'], [u'nuccore.id'], name=u'dataset_to_nuccore_ibfk_2'),
    mysql_default_charset=u'utf8',
    mysql_engine=u'InnoDB'
    )
    # ### end Alembic commands ###
