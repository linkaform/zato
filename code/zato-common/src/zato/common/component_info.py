# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import os
from anyjson import dumps as json_dumps, loads as json_loads
from cStringIO import StringIO
from datetime import datetime
from itertools import chain, groupby
from operator import attrgetter, itemgetter

# pyaml
import pyaml

# psutil
from psutil import CONN_LISTEN, Process

# PyYAML
import yaml

# pytz
from pytz import UTC

# Texttable
from texttable import Texttable

# Zato
from zato.common import INFO_FORMAT, MISC, ZATO_INFO_FILE
from zato.common.util import current_host

def format_connections(conns, format):
    """ Formats a list of connections according to the output format.
    """
    groups = (groupby(conns, key=attrgetter('status')))
    out = {}

    for status, items in groups:
        items = list(items)
        items.sort(key=attrgetter('raddr'))
        out_items = out.setdefault(status, [])

        for item in items:

            laddr_str = ':'.join(str(elem) for elem in item.laddr).ljust(21).decode('utf-8')
            raddr_str = ':'.join(str(elem) for elem in item.raddr).rjust(21).decode('utf-8')

            out_item = {
                'from': '{}:{}'.format(*item.laddr),
                'to': None,
                'formatted': None,
            }

            if item.raddr:
                out_item['to'] = '{}:{}'.format(*item.raddr)
                out_item['formatted'] = '{} -> {}'.format(laddr_str, raddr_str)
            else:
                out_item['formatted'] = '{}:{}'.format(*item.laddr)

            out_items.append(out_item)

    return out

def get_info(component_path, format):
    component_details = open(os.path.join(component_path, ZATO_INFO_FILE)).read()

    out = {
        'component_details': component_details,
        'component_full_path': component_path,
        'component_host': current_host(),
        'component_running': False,
        'current_time': datetime.now().isoformat(),
        'current_time_utc': datetime.utcnow().isoformat(),
        'master_proc_connections': None,
        'master_proc_pid': None,
        'master_proc_name': None,
        'master_proc_create_time': None,
        'master_proc_create_time_utc': None,
        'master_proc_username': None,
        'master_proc_workers_no': None,
        'master_proc_workers_pids': None,
    }

    master_proc_pid = None
    try:
        master_proc_pid = int(open(os.path.join(component_path, MISC.PIDFILE)).read())
    except(IOError, ValueError):
        # Ok, no such file or it's empty
        pass

    if master_proc_pid:
        out['component_running'] = True
        master_proc = Process(master_proc_pid)
        workers_pids = sorted(elem.pid for elem in master_proc.children())

        out['master_proc_connections'] = format_connections(master_proc.connections(), format)
        out['master_proc_pid'] = master_proc.pid
        out['master_proc_create_time'] = datetime.fromtimestamp(master_proc.create_time()).isoformat()
        out['master_proc_create_time_utc'] = datetime.fromtimestamp(master_proc.create_time(), UTC).isoformat()
        out['master_proc_username'] = master_proc.username()
        out['master_proc_name'] = master_proc.name()
        out['master_proc_workers_no'] = len(workers_pids)
        out['master_proc_workers_pids'] = workers_pids

        for pid in workers_pids:
            worker = Process(pid)
            out['worker_{}_create_time'.format(pid)] = datetime.fromtimestamp(worker.create_time()).isoformat()
            out['worker_{}_create_time_utc'.format(pid)] = datetime.fromtimestamp(worker.create_time(), UTC).isoformat()
            out['worker_{}_connections'.format(pid)] = format_connections(worker.connections(), format)

    return out

def format_info(value, format, cols_width=None, dumper=None):
    if format in(INFO_FORMAT.DICT, INFO_FORMAT.JSON, INFO_FORMAT.YAML):
        value['component_details'] = json_loads(value['component_details'])

    if format == INFO_FORMAT.JSON:
        return json_dumps(value)

    elif format == INFO_FORMAT.YAML:
        buff = StringIO()
        yaml.dump_all([value], default_flow_style=False, indent=4, Dumper=dumper, stream=buff)
        value = buff.getvalue()
        buff.close()

        return value

    elif format == INFO_FORMAT.TEXT:
        cols_width = (elem.strip() for elem in cols_width.split(','))
        cols_width = [int(elem) for elem in cols_width]

        table = Texttable()
        table.set_cols_width(cols_width)

        # Use text ('t') instead of auto so that boolean values don't get converted into ints
        table.set_cols_dtype(['t', 't'])

        rows = [['Key', 'Value']]
        rows.extend(sorted(value.items()))

        table.add_rows(rows)

        return table.draw()

    else:
        return value