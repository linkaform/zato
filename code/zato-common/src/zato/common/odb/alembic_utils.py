# -*- coding: utf-8 -*-

"""
Functions used to support Alembic integration, and helper functions for use within Alembic migrations.

Copyright (C) 2018, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import

# Stdlib
import contextlib
import logging
import os
import sys
import alembic.config

# SQLAlchemy
import sqlalchemy

# Zato
import zato.common.odb.alembic
from zato.common.util import get_crypto_manager_from_server_config
from zato.common.util import get_engine_url
from zato.common.util import get_config as get_zato_config
from zato.common.util import get_odb_session_from_server_config


# Pass this as a naming_convention= kwarg to batch_alter_table() in order to
# resolve unnamed constraint exceptions with SQLite. This is the default
# format used by PostgreSQL, it is likely if there are other databases to
# be supported, we will need to mimic their default naming behaviour by
# dynamically switching this at runtime, according to the driver in use.
naming_convention = {
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
}


# ################################################################################################################################

def db_type():
    """Return one of "sqlite", "mysql", or "postgresql" depending on Alembic's active database connection."""
    config = alembic.context.config.get_section('alembic')
    url = config.get('sqlalchemy.url')
    url, _, _ = url.partition(':')
    url, _, _ = url.partition('+')
    return url

# ################################################################################################################################

def never_if_mysql():
    """For batch_alter_table(recreate=...), return "never" if the active database connection is MySQL, otherwise return "auto".
    This is to work around a bug in the SQL Alembic emits against MySQL for certain operations."""
    if db_type() == 'mysql':
        return 'never'
    else:
        return 'auto'

# ################################################################################################################################

def always_if_sqlite():
    """For batch_alter_table(recreate=...), return "always" if the active database connection is SQLite, otherwise return "auto".
    This works around errors where Alembic thinks it can skip the recreate-table method when actually SQLite will still produce
    an error."""
    if db_type() == 'sqlite':
        return 'always'
    else:
        return 'auto'

# ################################################################################################################################

def drop_fk_by_shape(src_table, src_col, target_table, target_col):
    """
    Drop a ForeignKeyConstraint without knowing its name. This is used to work unnamed ForeignKeys on PG and MySQL having
    differing behaviour, and in the case of MySQL, having behaviour that varies according to the order FKs were created
    on the table.

    ::

        drop_fk_by_shape('web_socket_sub', 'client_id',
                         'web_socket_client', 'id')

    Above will result:
        MySQL: ALTER TABLE web_socket_sub DROP CONSTRAINT web_socket_sub_ibfk_1;
        PostgreSQL: ALTER TABLE web_socket_sub DROP CONSTRAINT web_socket_sub_client_id_fkey;
        SQLite: do nothing.
    """
    engine = alembic.op.get_bind()
    meta = sqlalchemy.MetaData()
    tbl = sqlalchemy.Table(src_table, meta, autoload=True, autoload_with=engine)

    for fk in tbl.foreign_keys:
        if   (fk.parent.name == src_col and
              fk.column.table.name == target_table and
              fk.column.name == target_col and
              fk.name and
              db_type() != 'sqlite'):
            alembic.op.drop_constraint(fk.name, src_table, 'foreignkey')

# ################################################################################################################################

def get_alembic_dir():
    """Return the location of the alembic directory in the source tree."""
    return os.path.dirname(zato.common.odb.alembic.__file__)

# ################################################################################################################################

def get_config(engine):
    """
    Instantiate Alembic with a configuration equivalent to:

    [alembic]
    script_location = <zato_basedir>/alembic
    sqlalchemy.url = <configured engine url>
    """
    config = alembic.config.Config()
    config.set_main_option('script_location', get_alembic_dir())
    config.set_main_option('sqlalchemy.url', str(engine.url))
    return config

# ################################################################################################################################

@contextlib.contextmanager
def share_connection(engine):
    """Yield an alembic Config instance that reuses ODB's existing SQLAlchemy connection. This is necessary to avoid having to duplicate the large amount of
    logic involved in setting up an mxODBC connection, etc."""
    config = get_config(engine)
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        yield config

# ################################################################################################################################

def main():
    """
    Command line wrapper that connects Alembic to the database specified in a Zato server config.
    """
    if len(sys.argv) < 2:
        sys.stderr.write('Usage: _zato-alembic <server_path> ...\n')
        sys.exit(1)

    repo_dir = os.path.join(sys.argv[1], 'config', 'repo')
    if not os.path.isdir(repo_dir):
        sys.stderr.write('Error: {} is not a server directory.\n'.format(repo_dir))
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

    zconfig = get_zato_config(repo_dir, 'server.conf')
    cm = get_crypto_manager_from_server_config(zconfig, repo_dir)
    session = get_odb_session_from_server_config(zconfig, cm)

    command_line = alembic.config.CommandLine(prog='_zato-alembic')
    options = command_line.parser.parse_args(sys.argv[2:])
    if not hasattr(options, 'cmd'):
        command_line.parser.error("too few arguments")
        sys.exit(1)

    engine = session.connection().engine
    config = get_config(engine)
    command_line.run_cmd(config, options)
