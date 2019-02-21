# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

"""
Copyright (C) 2019, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

"""
   Copyright 2006-2008 SpringSource (http://springsource.com), All Rights Reserved

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

# stdlib
import logging
import os
import signal
import sys
from http.client import BAD_REQUEST, FORBIDDEN, INTERNAL_SERVER_ERROR, NOT_ACCEPTABLE, OK, responses, SERVICE_UNAVAILABLE
from json import loads
from logging import DEBUG, Formatter, getLogger, StreamHandler
from logging.handlers import RotatingFileHandler
from os import getppid, path
from threading import RLock
from time import sleep
from traceback import format_exc
from wsgiref.simple_server import make_server

# Bunch
from bunch import bunchify

# Requests
from requests import post as requests_post

# YAML
import yaml

# Python 2/3 compatibility
from builtins import bytes
from six import PY2
from zato.common.py23_ import start_new_thread

# Zato
from zato.common.broker_message import code_to_name
from zato.common.util import parse_cmd_line_options
from zato.common.util.auth import parse_basic_auth
from zato.common.util.json_ import dumps
from zato.common.util.posix_ipc_ import ConnectorConfigIPC
from zato.server.connection.jms_wmq.jms import WebSphereMQException, NoMessageAvailableException
from zato.server.connection.jms_wmq.jms.connection import WebSphereMQConnection
from zato.server.connection.jms_wmq.jms.core import TextMessage

logger_zato = logging.getLogger('zato')

# ################################################################################################################################

default_logging_config = {
    'loggers': {
        'zato_ibm_mq': {
            'qualname': 'zato_ibm_mq', 'level': 'INFO', 'propagate': False, 'handlers': ['ibm_mq']}
    },
    'handlers': {
        'ibm_mq': {
            'formatter': 'default', 'backupCount': 10, 'mode': 'a', 'maxBytes': 20000000, 'filename': './logs/websphere-mq.log'
        },
    },
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)s - %(process)d:%(threadName)s - %(name)s:%(lineno)d - %(message)s'}
    }
}

# ################################################################################################################################

_http_200 = '{} {}'.format(OK, responses[OK])
_http_400 = '{} {}'.format(BAD_REQUEST, responses[BAD_REQUEST])
_http_403 = '{} {}'.format(FORBIDDEN, responses[FORBIDDEN])
_http_406 = '{} {}'.format(NOT_ACCEPTABLE, responses[NOT_ACCEPTABLE])
_http_500 = '{} {}'.format(INTERNAL_SERVER_ERROR, responses[INTERNAL_SERVER_ERROR])
_http_503 = '{} {}'.format(SERVICE_UNAVAILABLE, responses[SERVICE_UNAVAILABLE])

_path_api = '/api'
_path_ping = '/ping'
_paths = (_path_api, _path_ping)

_cc_failed         = 2    # pymqi.CMQC.MQCC_FAILED
_rc_conn_broken    = 2009 # pymqi.CMQC.MQRC_CONNECTION_BROKEN
_rc_not_authorized = 2035 # pymqi.CMQC.MQRC_NOT_AUTHORIZED

# ################################################################################################################################

class Response(object):
    def __init__(self, status=_http_200, data=b'', content_type='text/json'):
        self.status = status
        self.data = data
        self.content_type = content_type

# ################################################################################################################################

class _MessageCtx(object):
    __slots__ = ('mq_msg', 'channel_id', 'queue_name', 'service_name', 'data_format')

    def __init__(self, mq_msg, channel_id, queue_name, service_name, data_format):
        self.mq_msg = mq_msg
        self.channel_id = channel_id
        self.queue_name = queue_name
        self.service_name = service_name
        self.data_format = data_format

# ################################################################################################################################

class IBMMQChannel(object):
    """ A process to listen for messages from IBM MQ queue managers.
    """
    def __init__(self, conn, channel_id, queue_name, service_name, data_format, on_message_callback, logger):
        self.conn = conn
        self.id = channel_id
        self.queue_name = queue_name
        self.service_name = service_name
        self.data_format = data_format
        self.on_message_callback = on_message_callback
        self.keep_running = False
        self.logger = logger
        self.has_debug = self.logger.isEnabledFor(DEBUG)

        # PyMQI is an optional dependency so let's import it here rather than on module level
        import pymqi
        self.pymqi = pymqi

# ################################################################################################################################

    def _get_destination_info(self):
        return 'destination:`%s`, %s' % (self.queue_name, self.conn.get_connection_info())

# ################################################################################################################################

    def start(self, sleep_on_error=3, _connection_closing='zato.connection.closing'):
        """ Runs a background queue listener in its own  thread.
        """
        self.keep_running = True

        def _invoke_callback(msg_ctx):
            try:
                self.on_message_callback(msg_ctx)
            except Exception:
                self.logger.warn('Could not invoke message callback %s', format_exc())

        def _impl():
            while self.keep_running:
                try:
                    msg = self.conn.receive(self.queue_name, 100)
                    if self.has_debug:
                        self.logger.debug('Message received `%s`' % str(msg).decode('utf-8'))

                    if msg == _connection_closing:
                        self.logger.info('Received request to quit, closing channel for queue `%s` (%s)',
                            self.queue_name, self.conn.get_connection_info())
                        self.keep_running = False
                        return

                    if msg:
                        start_new_thread(_invoke_callback, (
                            _MessageCtx(msg, self.id, self.queue_name, self.service_name, self.data_format),))

                except NoMessageAvailableException as e:
                    if self.has_debug:
                        self.logger.debug('Consumer for queue `%s` did not receive a message. `%s`' % (
                            self.queue_name, self._get_destination_info(self.queue_name)))

                except self.pymqi.MQMIError as e:
                    if e.reason == self.pymqi.CMQC.MQRC_UNKNOWN_OBJECT_NAME:
                        self.logger.warn('No such queue `%s` found for %s', self.queue_name, self.conn.get_connection_info())
                    else:
                        self.logger.warn('%s in run, reason_code:`%s`, comp_code:`%s`' % (
                            e.__class__.__name__, e.reason, e.comp))

                    # In case of any low-level PyMQI error, sleep for some time
                    # because there is nothing we can do at this time about it.
                    self.logger.info('Sleeping for %ss', sleep_on_error)
                    sleep(sleep_on_error)

                except WebSphereMQException as e:
                    # If current connection is broken we may try to re-estalish it.
                    sleep(sleep_on_error)

                    if e.completion_code == _cc_failed and e.reason_code == _rc_conn_broken:
                        self.logger.warn('Caught MQRC_CONNECTION_BROKEN in receive, will try to reconnect connection to %s ',
                            self.conn.get_connection_info())
                        self.conn.reconnect()
                        self.conn.ping()
                    else:
                        raise

                except Exception as e:
                    self.logger.error('Exception in the main loop %r %s %s', e.args, type(e), format_exc())
                    sleep(sleep_on_error)

        # Start listener in a thread
        start_new_thread(_impl, ())

# ################################################################################################################################

    def stop(self):
        self.keep_running = False

# ################################################################################################################################

class ConnectionContainer(object):
    def __init__(self):

        # PyMQI is an optional dependency so let's import it here rather than on module level
        try:
            import pymqi
        except ImportError:
            self.pymqi = None
        else:
            self.pymqi = pymqi

        zato_options = sys.argv[1]
        zato_options = parse_cmd_line_options(zato_options)

        self.deployment_key = zato_options['deployment_key']
        self.shmem_size = int(zato_options['shmem_size'])

        self.host = '127.0.0.1'
        self.port = None
        self.username = None
        self.password = None
        self.server_auth = None
        self.basic_auth_expected = None
        self.server_port = None
        self.server_path = None
        self.server_address = 'http://127.0.0.1:{}{}'

        self.lock = RLock()
        self.logger = None
        self.parent_pid = getppid()

        self.config_ipc = ConnectorConfigIPC()
        self.config_ipc.create(self.deployment_key, self.shmem_size, False)

        self.connections = {}
        self.outconns = {}
        self.channels = {}

        self.outconn_id_to_def_id = {} # Maps outgoing connection IDs to their underlying definition IDs
        self.channel_id_to_def_id = {} # Ditto but for channels
        self.outconn_name_to_id = {}   # Maps outgoing connection names to their IDs

        self.set_config()

    def set_config(self):
        """ Sets self attributes, as configured in shmem by our parent process.
        """
        config = self.config_ipc.get_config('zato-ibm-mq')

        config = loads(config)
        config = bunchify(config)

        self.username = config.username
        self.password = config.password
        self.server_auth = (self.username, self.password)

        self.base_dir = config.base_dir
        self.port = config.port
        self.server_port = config.server_port
        self.server_path = config.server_path
        self.server_address = self.server_address.format(self.server_port, self.server_path)

        with open(config.logging_conf_path) as f:
            logging_config = yaml.load(f)

        # IBM MQ logging configuration is new in Zato 3.0, so it's optional.
        if not 'zato_ibm_mq' in logging_config['loggers']:
            logging_config = default_logging_config

        self.set_up_logging(logging_config)

# ################################################################################################################################

    def set_up_logging(self, config):

        logger_conf = config['loggers']['zato_ibm_mq']
        wmq_handler_conf = config['handlers']['ibm_mq']
        del wmq_handler_conf['formatter']
        wmq_handler_conf.pop('class', False)
        formatter_conf = config['formatters']['default']['format']

        self.logger = getLogger(logger_conf['qualname'])
        self.logger.setLevel(getattr(logging, logger_conf['level']))

        formatter = Formatter(formatter_conf)

        wmq_handler_conf['filename'] = path.abspath(path.join(self.base_dir, wmq_handler_conf['filename']))
        wmq_handler = RotatingFileHandler(**wmq_handler_conf)
        wmq_handler.setFormatter(formatter)

        stdout_handler = StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)

        self.logger.addHandler(wmq_handler)
        self.logger.addHandler(stdout_handler)

# ################################################################################################################################

    def _post(self, msg, _post=requests_post):
        self.logger.info('POST to `%s` (%s), msg:`%s`', self.server_address, self.username, msg)
        _post(self.server_address, data=dumps(msg), auth=self.server_auth)

# ################################################################################################################################

    def on_mq_message_received(self, msg_ctx):
        return self._post({
            'msg': msg_ctx.mq_msg.to_dict(),
            'channel_id': msg_ctx.channel_id,
            'queue_name': msg_ctx.queue_name,
            'service_name': msg_ctx.service_name,
            'data_format': msg_ctx.data_format,
            })

# ################################################################################################################################

    def _create_definition(self, msg, needs_connect=True):
        """ A low-level method to create connection definitions. Must be called with self.lock held.
        """
        msg.pop('name')
        msg.pop('cluster_id', None)
        msg.pop('old_name', None)
        id = msg.pop('id')
        msg['needs_jms'] = msg.pop('use_jms', False)
        msg.pop('_encryption_needed', False)
        msg.pop('_encrypted_in_odb', False)

        # We always create and add a connetion ..
        conn = WebSphereMQConnection(**msg)
        self.connections[id] = conn

        # .. because even if it fails here, it will be eventually established during one of .send or .receive,
        # however, it is possible that our caller already knows that the connection will fail so we need
        # to take it into account too.
        if needs_connect:
            conn.connect()

        return conn

# ################################################################################################################################

    def _on_DEFINITION_WMQ_CREATE(self, msg):
        """ Creates a new connection to IBM MQ.
        """
        if not self.pymqi:
            return Response(_http_503, 'Could not find pymqi module, IBM MQ connections will not start')

        with self.lock:
            try:
                self._create_definition(msg)
            except Exception as e:
                self.logger.warn(format_exc())
                return Response(_http_503, str(e.message))
            else:
                return Response()

# ################################################################################################################################

    def _on_DEFINITION_WMQ_EDIT(self, msg):
        """ Updates an existing definition - close the current one, including channels and outconns,
        and creates a new one in its place.
        """
        with self.lock:
            def_id = msg.id
            old_conn = self.connections[def_id]

            # Edit messages don't carry passwords
            msg.password = old_conn.password

            # It's possible that we are editing a connection that has no connected yet,
            # e.g. if password was invalid, so this needs to be guarded by an if.
            if old_conn.is_connected:
                self.connections[def_id].close()

            # Overwrites the previous connection object
            new_conn = self._create_definition(msg, old_conn.is_connected)

            # Stop and start all channels using this definition.
            for channel_id, _def_id in self.channel_id_to_def_id.items():
                if def_id == _def_id:
                    channel = self.channels[channel_id]
                    channel.stop()
                    channel.conn = new_conn
                    channel.start()

            return Response()

# ################################################################################################################################

    def _on_DEFINITION_WMQ_DELETE(self, msg):
        """ Deletes an IBM MQ MQ definition along with its associated outconns and channels.
        """
        with self.lock:
            def_id = msg.id

            # Stop all connections ..
            try:
                self.connections[def_id].close()
            except Exception:
                self.logger.warn(format_exc())
            finally:
                try:
                    del self.connections[def_id]
                except Exception:
                    self.logger.warn(format_exc())

                # .. continue to delete outconns regardless of errors above ..
                for outconn_id, outconn_def_id in self.outconn_id_to_def_id.items():
                    if outconn_def_id == def_id:
                        del self.outconn_id_to_def_id[outconn_id]
                        del self.outconns[outconn_id]

                # .. delete channels too.
                for channel_id, channel_def_id in self.channel_id_to_def_id.items():
                    if channel_def_id == def_id:
                        del self.channel_id_to_def_id[channel_id]
                        del self.channels[channel_id]

            return Response()

# ################################################################################################################################

    def _on_DEFINITION_WMQ_CHANGE_PASSWORD(self, msg):
        with self.lock:
            try:
                conn = self.connections[msg.id]
                conn.close()
                conn.password = str(msg.password)
                conn.connect()
            except Exception as e:
                self.logger.warn(format_exc())
                return Response(_http_503, str(e.message), 'text/plain')
            else:
                return Response()

# ################################################################################################################################

    def _on_DEFINITION_WMQ_PING(self, msg):
        """ Pings a remote IBM MQ manager.
        """
        try:
            self.connections[msg.id].ping()
        except WebSphereMQException as e:
            return Response(_http_503, str(e.message), 'text/plain')
        else:
            return Response()

# ################################################################################################################################

    def _create_outconn(self, msg):
        """ A low-level method to create an outgoing connection. Must be called with self.lock held.
        """
        # Just to be on the safe side, make sure that our connection exists
        if not msg.def_id in self.connections:
            return Response(_http_503, 'Could not find def_id among {}'.format(self.connections.keys()), 'text/plain')

        # Map outconn to its definition
        self.outconn_id_to_def_id[msg.id] = msg.def_id

        # Create the outconn now
        self.outconns[msg.id] = msg

        # Maps outconn name to its ID
        self.outconn_name_to_id[msg.name] = msg.id

        # Everything OK
        return Response()

# ################################################################################################################################

    def _delete_outconn(self, msg, outconn_name=None):
        """ A low-level implementation of outconn deletion. Must be called with self.lock held.
        """
        outconn_name = outconn_name if outconn_name else self.outconns[msg.id].name
        del self.outconns[msg.id]
        del self.outconn_id_to_def_id[msg.id]
        del self.outconn_name_to_id[outconn_name]

# ################################################################################################################################

    def _on_OUTGOING_WMQ_DELETE(self, msg):
        """ Deletes an existing IBM MQ outconn.
        """
        with self.lock:
            self._delete_outconn(msg)
            return Response()

# ################################################################################################################################

    def _on_OUTGOING_WMQ_CREATE(self, msg):
        """ Creates a new IBM MQ outgoin connections using an already existing definition.
        """
        with self.lock:
            return self._create_outconn(msg)

# ################################################################################################################################

    def _on_OUTGOING_WMQ_EDIT(self, msg):
        """ Updates and existing outconn by deleting and creating it again with latest configuration.
        """
        with self.lock:
            self._delete_outconn(msg, msg.old_name)
            return self._create_outconn(msg)

# ################################################################################################################################

    def _on_OUTGOING_WMQ_SEND(self, msg, is_reconnect=False):
        """ Sends a message to a remote IBM MQ queue.
        """
        with self.lock:
            outconn_id = msg.get('id') or self.outconn_name_to_id[msg.outconn_name]
            outconn = self.outconns[outconn_id]

        if not outconn.is_active:
            return Response(_http_406, 'Cannot send messages through an inactive connection', 'text/plain')
        else:
            def_id = self.outconn_id_to_def_id[outconn_id]
            conn = self.connections[def_id]
            conn.ping()

            try:

                delivery_mode = msg.delivery_mode or outconn.delivery_mode
                priority = msg.priority or outconn.priority
                expiration = msg.expiration or outconn.expiration

                text_msg = TextMessage(
                    text = msg.data,
                    jms_delivery_mode = delivery_mode,
                    jms_priority = priority,
                    jms_expiration = expiration,
                    jms_correlation_id = msg.get('correlation_id', '').encode('utf8'),
                    jms_message_id = msg.get('msg_id', '').encode('utf8'),
                    jms_reply_to = msg.get('reply_to', '').encode('utf8'),
                )

                conn.send(text_msg, msg.queue_name.encode('utf8'))
                return Response(data=dumps(text_msg.to_dict(False)))

            except(self.pymqi.MQMIError, WebSphereMQException) as e:

                if isinstance(e, self.pymqi.MQMIError):
                    cc_code = e.comp
                    reason_code = e.reason
                else:
                    cc_code = e.completion_code
                    reason_code = e.reason_code

                # Try to reconnect if the connection is broken but only if we have not tried to already
                if (not is_reconnect) and cc_code == _cc_failed and reason_code == _rc_conn_broken:
                    self.logger.warn('Caught MQRC_CONNECTION_BROKEN in send, will try to reconnect connection to %s ',
                        conn.get_connection_info())

                    # Sleep for a while before reconnecting
                    sleep(1)

                    # Try to reconnect
                    conn.reconnect()

                    # Confirm it by pinging the queue manager
                    conn.ping()

                    # Resubmit the request
                    return self._on_OUTGOING_WMQ_SEND(msg, is_reconnect=True)
                else:
                    return self._on_send_exception()

            except Exception as e:
                return self._on_send_exception()


# ################################################################################################################################

    def _on_CHANNEL_WMQ_CREATE(self, msg):
        """ Creates a new background channel listening for messages from a given queue.
        """
        with self.lock:
            conn = self.connections[msg.def_id]
            channel = IBMMQChannel(conn, msg.id, msg.queue.encode('utf8'), msg.service_name, msg.data_format,
                self.on_mq_message_received, self.logger)
            channel.start()
            self.channels[channel.id] = channel
            self.channel_id_to_def_id[channel.id] = msg.def_id
            return Response()

# ################################################################################################################################

    def _on_CHANNEL_WMQ_EDIT(self, msg):
        """ Updates an IBM MQ MQ channel by stopping it and starting again with a new configuration.
        """
        with self.lock:
            channel = self.channels[msg.id]
            channel.stop()
            channel.queue_name = msg.queue.encode('utf8')
            channel.service_name = msg.service_name
            channel.data_format = msg.data_format
            channel.keep_running = True
            channel.start()

            return Response()

# ################################################################################################################################

    def _on_CHANNEL_WMQ_DELETE(self, msg):
        """ Stops and deletes a background channel.
        """
        with self.lock:
            channel = self.channels[msg.id]
            channel.keep_running = False

            del self.channels[channel.id]
            del self.channel_id_to_def_id[channel.id]

            return Response()

# ################################################################################################################################

    def _on_send_exception(self):
        msg = 'Exception in _on_OUTGOING_WMQ_SEND (2) `{}`'.format(format_exc())
        self.logger.warn(msg)
        return Response(_http_503, msg)

# ################################################################################################################################

    def handle_http_request(self, path, msg, ok=b'OK'):
        """ Dispatches incoming HTTP requests - either reconfigures the connector or puts messages to queues.
        """
        self.logger.info('MSG received %s %s', path, msg)

        if path == _path_ping:
            return Response()
        else:
            msg = msg.decode('utf8')
            msg = loads(msg)
            msg = bunchify(msg)

            # Delete what handlers don't need
            msg.pop('msg_type', None) # Optional if message was sent by a server that is starting up vs. API call
            action = msg.pop('action')

            handler = getattr(self, '_on_{}'.format(code_to_name[action]))
            return handler(msg)

# ################################################################################################################################

    def check_credentials(self, auth):
        """ Checks incoming username/password and returns True only if they were valid and as expected.
        """
        username, password = parse_basic_auth(auth)

        if username != self.username:
            self.logger.warn('Invalid username or password')
            return

        elif password != self.password:
            self.logger.warn('Invalid username or password')
            return
        else:
            # All good, we let the request in
            return True

# ################################################################################################################################

    def on_wsgi_request(self, environ, start_response):

        # Default values to use in case of any internal errors
        status = _http_503
        content_type = 'text/plain'

        try:
            content_length = environ['CONTENT_LENGTH']
            if not content_length:
                status = _http_400
                data = 'Missing content'
                content_type = 'text/plain'
            else:
                data = environ['wsgi.input'].read(int(content_length))
                if self.check_credentials(environ.get('HTTP_AUTHORIZATION')):
                    response = self.handle_http_request(environ['PATH_INFO'], data)
                    status = response.status
                    data = response.data
                    content_type = response.content_type
                else:
                    status = _http_403
                    data = 'You are not allowed to access this resource'
                    content_type = 'text/plain'

        except Exception as e:
            self.logger.warn(format_exc())
            content_type = 'text/plain'
            status = _http_503
            data = repr(e.args)
        finally:

            try:
                if PY2:
                    status = status.encode('utf8')
                    headers = [(b'Content-type', content_type.encode('utf8'))]
                else:
                    headers = [('Content-type', content_type)]

                if not isinstance(data, bytes):
                    data = data.encode('utf8')

                start_response(status, headers)
                return [data]

            except Exception:
                exc_formatted = format_exc()
                self.logger.warn('Exception in finally block `%s`', exc_formatted)

# ################################################################################################################################

    def run(self):
        server = make_server(self.host, self.port, self.on_wsgi_request)
        try:
            server.serve_forever()
        except KeyboardInterrupt:

            try:
                # Attempt to clean up, if possible
                server.shutdown()
                for conn in self.connections.values():
                    conn.close()
            except Exception:
                # Log exception if cleanup was not possible
                self.logger.warn('Exception in shutdown procedure `%s`', format_exc())
            finally:
                # Anything happens, we need to shut down the process
                os.kill(os.getpid(), signal.SIGTERM)

# ################################################################################################################################

if __name__ == '__main__':

    container = ConnectionContainer()
    container.run()

# ################################################################################################################################
