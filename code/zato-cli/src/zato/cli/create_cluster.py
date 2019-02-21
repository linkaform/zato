# -*- coding: utf-8 -*-

"""
Copyright (C) 2019, Zato Source s.r.o. https://zato.io

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from copy import deepcopy
from datetime import datetime
from traceback import format_exc
from uuid import uuid4

# SQLAlchemy
from sqlalchemy.exc import IntegrityError

# Python 2/3 compatibility
from future.utils import iteritems

# Zato
from zato.cli import common_odb_opts, get_tech_account_opts, ZatoCommand
from zato.common import CACHE, CONNECTION, DATA_FORMAT, IPC, MISC, PUBSUB, SIMPLE_IO, URL_TYPE
from zato.common.odb.model import CacheBuiltin, Cluster, HTTPBasicAuth, HTTPSOAP, PubSubEndpoint, \
     PubSubSubscription, PubSubTopic, RBACClientRole, RBACPermission, RBACRole, RBACRolePermission, Service, WSSDefinition
from zato.common.pubsub import new_sub_key
from zato.common.util import get_http_json_channel, get_http_soap_channel
from zato.common.util.json_ import dumps
from zato.common.util.time_ import utcnow_as_ms

# ################################################################################################################################

zato_services = {

    # Channels - AMQP
    'zato.channel.amqp.create':'zato.server.service.internal.channel.amqp_.Create',
    'zato.channel.amqp.delete':'zato.server.service.internal.channel.amqp_.Delete',
    'zato.channel.amqp.edit':'zato.server.service.internal.channel.amqp_.Edit',
    'zato.channel.amqp.get-list':'zato.server.service.internal.channel.amqp_.GetList',

    # Channels - IBM MQ
    'zato.channel.jms-wmq.create':'zato.server.service.internal.channel.jms_wmq.Create',
    'zato.channel.jms-wmq.delete':'zato.server.service.internal.channel.jms_wmq.Delete',
    'zato.channel.jms-wmq.edit':'zato.server.service.internal.channel.jms_wmq.Edit',
    'zato.channel.jms-wmq.get-list':'zato.server.service.internal.channel.jms_wmq.GetList',

    # Channels - WebSocket
    'zato.channel.web-socket.create':'zato.server.service.internal.channel.web_socket.Create',
    'zato.channel.web-socket.delete':'zato.server.service.internal.channel.web_socket.Delete',
    'zato.channel.web-socket.edit':'zato.server.service.internal.channel.web_socket.Edit',
    'zato.channel.web-socket.get-list':'zato.server.service.internal.channel.web_socket.GetList',
    'zato.channel.web-socket.get-token':'zato.server.service.internal.channel.web_socket.GetToken',
    'zato.channel.web-socket.invalidate-token':'zato.server.service.internal.channel.web_socket.InvalidateToken',

    # Channels - WebSocket - clients
    'zato.channel.web-socket.client.create':'zato.server.service.internal.channel.web_socket.client.Create',
    'zato.channel.web-socket.client.delete-by-pub-id':'zato.server.service.internal.channel.web_socket.client.DeleteByPubId',
    'zato.channel.web-socket.client.delete-by-server':'zato.server.service.internal.channel.web_socket.client.DeleteByServer',

    # Channels - WebSocket - subscriptions
    'zato.channel.web-socket.subscription.create':'zato.server.service.internal.channel.web_socket.subscription.Create',
    'zato.channel.web-socket.subscription.delete':'zato.server.service.internal.channel.web_socket.subscription.Delete',

    # Channels - ZeroMQ
    'zato.channel.zmq.create':'zato.server.service.internal.channel.zmq.Create',
    'zato.channel.zmq.delete':'zato.server.service.internal.channel.zmq.Delete',
    'zato.channel.zmq.edit':'zato.server.service.internal.channel.zmq.Edit',
    'zato.channel.zmq.get-list':'zato.server.service.internal.channel.zmq.GetList',

    # Outgoing connections - SAP
    'zato.outgoing.sap.change-password':'zato.server.service.internal.outgoing.sap.ChangePassword',
    'zato.outgoing.sap.create':'zato.server.service.internal.outgoing.sap.Create',
    'zato.outgoing.sap.delete':'zato.server.service.internal.outgoing.sap.Delete',
    'zato.outgoing.sap.edit':'zato.server.service.internal.outgoing.sap.Edit',
    'zato.outgoing.sap.get-list':'zato.server.service.internal.outgoing.sap.GetList',

     # Checks
    'zato.checks.sio.as-is-service': 'zato.server.service.internal.checks.sio.AsIsService',
    'zato.checks.sio.boolean-service': 'zato.server.service.internal.checks.sio.BooleanService',
    'zato.checks.sio.csv-service': 'zato.server.service.internal.checks.sio.CSVService',
    'zato.checks.sio.check-sio': 'zato.server.service.internal.checks.sio.CheckSIO',
    'zato.checks.check-service': 'zato.server.service.internal.checks.CheckService',
    'zato.checks.sio.check-target-service': 'zato.server.service.internal.checks.sio.CheckTargetService',
    'zato.checks.sio.dict-service': 'zato.server.service.internal.checks.sio.DictService',
    'zato.checks.sio.integer-service': 'zato.server.service.internal.checks.sio.IntegerService',
    'zato.checks.sio.list-of-dicts-service': 'zato.server.service.internal.checks.sio.ListOfDictsService',
    'zato.checks.sio.list-service': 'zato.server.service.internal.checks.sio.ListService',
    'zato.checks.sio.nested-service': 'zato.server.service.internal.checks.sio.NestedService',
    'zato.checks.sio.no-force-type-service': 'zato.server.service.internal.checks.sio.NoForceTypeService',
    'zato.checks.sio.utc-service': 'zato.server.service.internal.checks.sio.UTCService',
    'zato.checks.sio.unicode-service': 'zato.server.service.internal.checks.sio.UnicodeService',

    # Cloud - AWS - S3
    'zato.cloud.aws.s3.create':'zato.server.service.internal.cloud.aws.s3.Create',
    'zato.cloud.aws.s3.delete':'zato.server.service.internal.cloud.aws.s3.Delete',
    'zato.cloud.aws.s3.edit':'zato.server.service.internal.cloud.aws.s3.Edit',
    'zato.cloud.aws.s3.get-list':'zato.server.service.internal.cloud.aws.s3.GetList',

    # Cloud - OpenStack - Swift
    'zato.cloud.openstack.swift.create':'zato.server.service.internal.cloud.openstack.swift.Create',
    'zato.cloud.openstack.swift.delete':'zato.server.service.internal.cloud.openstack.swift.Delete',
    'zato.cloud.openstack.swift.edit':'zato.server.service.internal.cloud.openstack.swift.Edit',
    'zato.cloud.openstack.swift.get-list':'zato.server.service.internal.cloud.openstack.swift.GetList',

    # Connectors - AMQP
    'zato.connector.amqp.create':'zato.server.service.internal.connector.amqp_.Create',

    # Definitions - AMQP
    'zato.definition.amqp.change-password':'zato.server.service.internal.definition.amqp_.ChangePassword',
    'zato.definition.amqp.create':'zato.server.service.internal.definition.amqp_.Create',
    'zato.definition.amqp.delete':'zato.server.service.internal.definition.amqp_.Delete',
    'zato.definition.amqp.edit':'zato.server.service.internal.definition.amqp_.Edit',
    'zato.definition.amqp.get-by-id':'zato.server.service.internal.definition.amqp_.GetByID',
    'zato.definition.amqp.get-list':'zato.server.service.internal.definition.amqp_.GetList',

    # Definitions - Cassandra
    'zato.definition.cassandra.create':'zato.server.service.internal.definition.cassandra.Create',
    'zato.definition.cassandra.delete':'zato.server.service.internal.definition.cassandra.Delete',
    'zato.definition.cassandra.edit':'zato.server.service.internal.definition.cassandra.Edit',
    'zato.definition.cassandra.get-by-id':'zato.server.service.internal.definition.cassandra.GetByID',
    'zato.definition.cassandra.get-list':'zato.server.service.internal.definition.cassandra.GetList',

    # Definitions - IBM MQ
    'zato.definition.jms-wmq.create':'zato.server.service.internal.definition.jms_wmq.Create',
    'zato.definition.jms-wmq.delete':'zato.server.service.internal.definition.jms_wmq.Delete',
    'zato.definition.jms-wmq.edit':'zato.server.service.internal.definition.jms_wmq.Edit',
    'zato.definition.jms-wmq.get-by-id':'zato.server.service.internal.definition.jms_wmq.GetByID',
    'zato.definition.jms-wmq.get-list':'zato.server.service.internal.definition.jms_wmq.GetList',

    # E-mail - IMAP
    'zato.email.imap.change-password': 'zato.server.service.internal.email.imap.ChangePassword',
    'zato.email.imap.create': 'zato.server.service.internal.email.imap.Create',
    'zato.email.imap.delete': 'zato.server.service.internal.email.imap.Delete',
    'zato.email.imap.edit': 'zato.server.service.internal.email.imap.Edit',
    'zato.email.imap.get-list': 'zato.server.service.internal.email.imap.GetList',
    'zato.email.imap.ping': 'zato.server.service.internal.email.imap.Ping',

    # E-mail - SMTP
    'zato.email.smtp.change-password': 'zato.server.service.internal.email.smtp.ChangePassword',
    'zato.email.smtp.create': 'zato.server.service.internal.email.smtp.Create',
    'zato.email.smtp.delete': 'zato.server.service.internal.email.smtp.Delete',
    'zato.email.smtp.edit': 'zato.server.service.internal.email.smtp.Edit',
    'zato.email.smtp.get-list': 'zato.server.service.internal.email.smtp.GetList',
    'zato.email.smtp.ping': 'zato.server.service.internal.email.smtp.Ping',

    # Helpers
    'zato.helpers.echo': 'zato.server.service.internal.helpers.Echo',
    'zato.helpers.input-logger': 'zato.server.service.internal.helpers.InputLogger',
    'zato.helpers.sio-input-logger': 'zato.server.service.internal.helpers.SIOInputLogger',

    # Hot-deploy
    'zato.hot-deploy.create': 'zato.server.service.internal.hot_deploy.Create',
    'zato.ide-deploy.create': 'zato.server.service.internal.ide_deploy.Create',

    # HTTP/SOAP
    'zato.http-soap.create':'zato.server.service.internal.http_soap.Create',
    'zato.http-soap.delete':'zato.server.service.internal.http_soap.Delete',
    'zato.http-soap.edit':'zato.server.service.internal.http_soap.Edit',
    'zato.http-soap.get-list':'zato.server.service.internal.http_soap.GetList',
    'zato.http-soap.ping':'zato.server.service.internal.http_soap.Ping',

    # Clusters - Connections map
    'zato.info.get-info':'zato.server.service.internal.info.GetInfo',
    'zato.info.get-server-info':'zato.server.service.internal.info.GetServerInfo',

    # SQL-backed KVDB
    'zato.kv_data.auto-clean-up':'zato.server.service.internal.kv_data.AutoCleanUp',

    # Key/value DB
    'zato.kvdb.data-dict.dictionary.create':'zato.server.service.internal.kvdb.data_dict.dictionary.Create',
    'zato.kvdb.data-dict.dictionary.delete':'zato.server.service.internal.kvdb.data_dict.dictionary.Delete',
    'zato.kvdb.data-dict.dictionary.edit':'zato.server.service.internal.kvdb.data_dict.dictionary.Edit',
    'zato.kvdb.data-dict.dictionary.get-key-list':'zato.server.service.internal.kvdb.data_dict.dictionary.GetKeyList',
    'zato.kvdb.data-dict.dictionary.get-last-id':'zato.server.service.internal.kvdb.data_dict.dictionary.GetLastID',
    'zato.kvdb.data-dict.dictionary.get-list':'zato.server.service.internal.kvdb.data_dict.dictionary.GetList',
    'zato.kvdb.data-dict.dictionary.get-system-list':'zato.server.service.internal.kvdb.data_dict.dictionary.GetSystemList',
    'zato.kvdb.data-dict.dictionary.get-value-list':'zato.server.service.internal.kvdb.data_dict.dictionary.GetValueList',
    'zato.kvdb.data-dict.impexp.import':'zato.server.service.internal.kvdb.data_dict.impexp.Import',
    'zato.kvdb.data-dict.translation.create':'zato.server.service.internal.kvdb.data_dict.translation.Create',
    'zato.kvdb.data-dict.translation.delete':'zato.server.service.internal.kvdb.data_dict.translation.Delete',
    'zato.kvdb.data-dict.translation.edit':'zato.server.service.internal.kvdb.data_dict.translation.Edit',
    'zato.kvdb.data-dict.translation.get-last-id':'zato.server.service.internal.kvdb.data_dict.translation.GetLastID',
    'zato.kvdb.data-dict.translation.get-list':'zato.server.service.internal.kvdb.data_dict.translation.GetList',
    'zato.kvdb.data-dict.translation.translate':'zato.server.service.internal.kvdb.data_dict.translation.Translate',
    'zato.kvdb.remote-command.execute':'zato.server.service.internal.kvdb.ExecuteCommand',

    # Messages - Namespaces
    'zato.message.namespace.create': 'zato.server.service.internal.message.namespace.Create',
    'zato.message.namespace.edit': 'zato.server.service.internal.message.namespace.Edit',
    'zato.message.namespace.delete': 'zato.server.service.internal.message.namespace.Delete',
    'zato.message.namespace.get-list': 'zato.server.service.internal.message.namespace.GetList',

    # Messages - JSON Pointers
    'zato.message.json_pointer.create': 'zato.server.service.internal.message.json_pointer.Create',
    'zato.message.json_pointer.edit': 'zato.server.service.internal.message.json_pointer.Edit',
    'zato.message.json_pointer.delete': 'zato.server.service.internal.message.json_pointer.Delete',
    'zato.message.json_pointer.get-list': 'zato.server.service.internal.message.json_pointer.GetList',

    # Messages - XPath
    'zato.message.xpath.create': 'zato.server.service.internal.message.xpath.Create',
    'zato.message.xpath.edit': 'zato.server.service.internal.message.xpath.Edit',
    'zato.message.xpath.delete': 'zato.server.service.internal.message.xpath.Delete',
    'zato.message.xpath.get-list': 'zato.server.service.internal.message.xpath.GetList',

    # Messages - Live browser
    'zato.message.live-browser.dispatch': 'zato.server.service.internal.message.live_browser.Dispatch',
    'zato.message.live-browser.get-web-admin-connection-details': \
        'zato.server.service.internal.message.live_browser.GetWebAdminConnectionDetails',

    # Notifications - Cloud - OpenStack - Swift
    'zato.notif.cloud.openstack.swift.create': 'zato.server.service.internal.notif.cloud.openstack.swift.Create',
    'zato.notif.cloud.openstack.swift.edit': 'zato.server.service.internal.notif.cloud.openstack.swift.Edit',
    'zato.notif.cloud.openstack.swift.delete': 'zato.server.service.internal.notif.cloud.openstack.swift.Delete',
    'zato.notif.cloud.openstack.swift.get-list': 'zato.server.service.internal.notif.cloud.openstack.swift.GetList',

    # Notifications - SQL
    'zato.notif.cloud.sql.create': 'zato.server.service.internal.notif.cloud.sql.Create',
    'zato.notif.cloud.sql.edit': 'zato.server.service.internal.notif.cloud.sql.Edit',
    'zato.notif.cloud.sql.delete': 'zato.server.service.internal.notif.cloud.sql.Delete',
    'zato.notif.cloud.sql.get-list': 'zato.server.service.internal.notif.cloud.sql.GetList',

    # Outgoing connections - AMQP
    'zato.outgoing.amqp.create':'zato.server.service.internal.outgoing.amqp_.Create',
    'zato.outgoing.amqp.delete':'zato.server.service.internal.outgoing.amqp_.Delete',
    'zato.outgoing.amqp.edit':'zato.server.service.internal.outgoing.amqp_.Edit',
    'zato.outgoing.amqp.get-list':'zato.server.service.internal.outgoing.amqp_.GetList',

    # Outgoing connections - FTP
    'zato.outgoing.ftp.change-password':'zato.server.service.internal.outgoing.ftp.ChangePassword',
    'zato.outgoing.ftp.create':'zato.server.service.internal.outgoing.ftp.Create',
    'zato.outgoing.ftp.delete':'zato.server.service.internal.outgoing.ftp.Delete',
    'zato.outgoing.ftp.edit':'zato.server.service.internal.outgoing.ftp.Edit',
    'zato.outgoing.ftp.get-list':'zato.server.service.internal.outgoing.ftp.GetList',

    # Outgoing connections - IBM MQ
    'zato.outgoing.jms-wmq.create':'zato.server.service.internal.outgoing.jms_wmq.Create',
    'zato.outgoing.jms-wmq.delete':'zato.server.service.internal.outgoing.jms_wmq.Delete',
    'zato.outgoing.jms-wmq.edit':'zato.server.service.internal.outgoing.jms_wmq.Edit',
    'zato.outgoing.jms-wmq.get-list':'zato.server.service.internal.outgoing.jms_wmq.GetList',

    # Outgoing connections - Odoo
    'zato.outgoing.odoo.change-password':'zato.server.service.internal.outgoing.odoo.ChangePassword',
    'zato.outgoing.odoo.create':'zato.server.service.internal.outgoing.odoo.Create',
    'zato.outgoing.odoo.delete':'zato.server.service.internal.outgoing.odoo.Delete',
    'zato.outgoing.odoo.edit':'zato.server.service.internal.outgoing.odoo.Edit',
    'zato.outgoing.odoo.get-list':'zato.server.service.internal.outgoing.odoo.GetList',
    'zato.outgoing.odoo.ping':'zato.server.service.internal.outgoing.odoo.Ping',

    # Outgoing connections - SQL
    'zato.outgoing.sql.change-password':'zato.server.service.internal.outgoing.sql.ChangePassword',
    'zato.outgoing.sql.create':'zato.server.service.internal.outgoing.sql.Create',
    'zato.outgoing.sql.delete':'zato.server.service.internal.outgoing.sql.Delete',
    'zato.outgoing.sql.edit':'zato.server.service.internal.outgoing.sql.Edit',
    'zato.outgoing.sql.get-list':'zato.server.service.internal.outgoing.sql.GetList',
    'zato.outgoing.sql.ping':'zato.server.service.internal.outgoing.sql.Ping',

    # Outgoing connections - ZeroMQ
    'zato.outgoing.zmq.create':'zato.server.service.internal.outgoing.zmq.Create',
    'zato.outgoing.zmq.delete':'zato.server.service.internal.outgoing.zmq.Delete',
    'zato.outgoing.zmq.edit':'zato.server.service.internal.outgoing.zmq.Edit',
    'zato.outgoing.zmq.get-list':'zato.server.service.internal.outgoing.zmq.GetList',

    # Cache - Built-in
    'zato.cache.builtin.create': 'zato.server.service.internal.cache.builtin.Create',
    'zato.cache.builtin.edit': 'zato.server.service.internal.cache.builtin.Edit',
    'zato.cache.builtin.delete': 'zato.server.service.internal.cache.builtin.Delete',
    'zato.cache.builtin.get-list': 'zato.server.service.internal.cache.builtin.GetList',

    # Query - Cassandra
    'zato.query.cassandra.create':'zato.server.service.internal.query.cassandra.Create',
    'zato.query.cassandra.delete':'zato.server.service.internal.query.cassandra.Delete',
    'zato.query.cassandra.edit':'zato.server.service.internal.query.cassandra.Edit',
    'zato.query.cassandra.get-list':'zato.server.service.internal.query.cassandra.GetList',

    # Search - ElasticSearch
    'zato.search.es.create':'zato.server.service.internal.search.es.Create',
    'zato.search.es.delete':'zato.server.service.internal.search.es.Delete',
    'zato.search.es.edit':'zato.server.service.internal.search.es.Edit',
    'zato.search.es.get-list':'zato.server.service.internal.search.es.GetList',

    # Search - Solr
    'zato.search.solr.create':'zato.server.service.internal.search.solr.Create',
    'zato.search.solr.delete':'zato.server.service.internal.search.solr.Delete',
    'zato.search.solr.edit':'zato.server.service.internal.search.solr.Edit',
    'zato.search.solr.get-list':'zato.server.service.internal.search.solr.GetList',

    # Ping services are added in Create.add_ping_services

    # Scheduler
    'zato.scheduler.job.create':'zato.server.service.internal.scheduler.Create',
    'zato.scheduler.job.delete':'zato.server.service.internal.scheduler.Delete',
    'zato.scheduler.job.edit':'zato.server.service.internal.scheduler.Edit',
    'zato.scheduler.job.execute':'zato.server.service.internal.scheduler.Execute',
    'zato.scheduler.job.get-by-name':'zato.server.service.internal.scheduler.GetByName',
    'zato.scheduler.job.get-list':'zato.server.service.internal.scheduler.GetList',

    # Security
    'zato.security.get-list':'zato.server.service.internal.security.GetList',

    # Security - API keys
    'zato.security.apikey.change-password':'zato.server.service.internal.security.apikey.ChangePassword',
    'zato.security.apikey.create':'zato.server.service.internal.security.apikey.Create',
    'zato.security.apikey.delete':'zato.server.service.internal.security.apikey.Delete',
    'zato.security.apikey.edit':'zato.server.service.internal.security.apikey.Edit',
    'zato.security.apikey.get-list':'zato.server.service.internal.security.apikey.GetList',

    # Security - AWS
    'zato.security.aws.change-password':'zato.server.service.internal.security.aws.ChangePassword',
    'zato.security.aws.create':'zato.server.service.internal.security.aws.Create',
    'zato.security.aws.delete':'zato.server.service.internal.security.aws.Delete',
    'zato.security.aws.edit':'zato.server.service.internal.security.aws.Edit',
    'zato.security.aws.get-list':'zato.server.service.internal.security.aws.GetList',

    # Security - HTTP Basic Auth
    'zato.security.basic-auth.change-password':'zato.server.service.internal.security.basic_auth.ChangePassword',
    'zato.security.basic-auth.create':'zato.server.service.internal.security.basic_auth.Create',
    'zato.security.basic-auth.delete':'zato.server.service.internal.security.basic_auth.Delete',
    'zato.security.basic-auth.edit':'zato.server.service.internal.security.basic_auth.Edit',
    'zato.security.basic-auth.get-list':'zato.server.service.internal.security.basic_auth.GetList',

    # Security - JWT
    'zato.security.jwt.auto-clean-up':'zato.server.service.internal.security.jwt.AutoCleanUp',
    'zato.security.jwt.change-password':'zato.server.service.internal.security.jwt.ChangePassword',
    'zato.security.jwt.create':'zato.server.service.internal.security.jwt.Create',
    'zato.security.jwt.delete':'zato.server.service.internal.security.jwt.Delete',
    'zato.security.jwt.edit':'zato.server.service.internal.security.jwt.Edit',
    'zato.security.jwt.get-list':'zato.server.service.internal.security.jwt.GetList',
    'zato.security.jwt.log-in':'zato.server.service.internal.security.jwt.LogIn',
    'zato.security.jwt.log-out':'zato.server.service.internal.security.jwt.LogOut',

    # Security - NTLM
    'zato.security.tls.ca_cert.change-password':'zato.server.service.internal.security.tls.ca_cert.ChangePassword',
    'zato.security.tls.ca_cert.create':'zato.server.service.internal.security.tls.ca_cert.Create',
    'zato.security.tls.ca_cert.delete':'zato.server.service.internal.security.tls.ca_cert.Delete',
    'zato.security.tls.ca_cert.edit':'zato.server.service.internal.security.tls.ca_cert.Edit',
    'zato.security.tls.ca_cert.get-list':'zato.server.service.internal.security.tls.ca_cert.GetList',

    # Security - OAuth
    'zato.security.oauth.change-password':'zato.server.service.internal.security.oauth.ChangePassword',
    'zato.security.oauth.create':'zato.server.service.internal.security.oauth.Create',
    'zato.security.oauth.delete':'zato.server.service.internal.security.oauth.Delete',
    'zato.security.oauth.edit':'zato.server.service.internal.security.oauth.Edit',
    'zato.security.oauth.get-list':'zato.server.service.internal.security.oauth.GetList',

    # Security - OpenStack
    'zato.security.openstack.change-password':'zato.server.service.internal.security.openstack.ChangePassword',
    'zato.security.openstack.create':'zato.server.service.internal.security.openstack.Create',
    'zato.security.openstack.delete':'zato.server.service.internal.security.openstack.Delete',
    'zato.security.openstack.edit':'zato.server.service.zato_servicesinternal.security.openstack.Edit',
    'zato.security.openstack.get-list':'zato.server.service.internal.security.openstack.GetList',

    # Security - RBAC - Roles
    'zato.security.rbac.role.create':'zato.server.service.internal.security.rbac.role.Create',
    'zato.security.rbac.role.delete':'zato.server.service.internal.security.rbac.role.Delete',
    'zato.security.rbac.role.edit':'zato.server.service.internal.security.rbac.role.Edit',
    'zato.security.rbac.role.get-list':'zato.server.service.internal.security.rbac.role.GetList',

    # Security - RBAC - Client roles
    'zato.security.rbac.client-role.create':'zato.server.service.internal.security.rbac.client_role.Create',
    'zato.security.rbac.client-role.delete':'zato.server.service.internal.security.rbac.client_role.Delete',
    'zato.security.rbac.client-role.get-list':'zato.server.service.internal.security.rbac.client_role.GetList',
    'zato.security.rbac.client-role.get-client-def-list':'zato.server.service.internal.security.rbac.client_role.GetClientDefList',

    # Security - RBAC - Permissions
    'zato.security.rbac.permission.create':'zato.server.service.internal.security.rbac.permission.Create',
    'zato.security.rbac.permission.delete':'zato.server.service.internal.security.rbac.permission.Delete',
    'zato.security.rbac.permission.edit':'zato.server.service.internal.security.rbac.permission.Edit',
    'zato.security.rbac.permission.get-list':'zato.server.service.internal.security.rbac.permission.GetList',

    # Security - RBAC - Permissions for roles
    'zato.security.rbac.role-permission.create':'zato.server.service.internal.security.rbac.role_permission.Create',
    'zato.security.rbac.role-permission.delete':'zato.server.service.internal.security.rbac.role_permission.Delete',
    'zato.security.rbac.role-permission.get-list':'zato.server.service.internal.security.rbac.role_permission.GetList',

    # Security - TLS - CA certs
    'zato.security.tls.ca_cert.create':'zato.server.service.internal.security.tls.ca_cert.Create',
    'zato.security.tls.ca_cert.delete':'zato.server.service.internal.security.tls.ca_cert.Delete',
    'zato.security.tls.ca_cert.edit':'zato.server.service.internal.security.tls.ca_cert.Edit',
    'zato.security.tls.ca_cert.get-list':'zato.server.service.internal.security.tls.ca_cert.GetList',

    # Security - TLS - Key/cert pairs
    'zato.security.tls.key_cert.create':'zato.server.service.internal.security.tls.key_cert.Create',
    'zato.security.tls.key_cert.delete':'zato.server.service.internal.security.tls.key_cert.Delete',
    'zato.security.tls.key_cert.edit':'zato.server.service.internal.security.tls.key_cert.Edit',
    'zato.security.tls.key_cert.get-list':'zato.server.service.internal.security.tls.key_cert.GetList',

    # Security - WS-Security
    'zato.security.wss.change-password':'zato.server.service.internal.security.wss.ChangePassword',
    'zato.security.wss.create':'zato.server.service.internal.security.wss.Create',
    'zato.security.wss.delete':'zato.server.service.internal.security.wss.Delete',
    'zato.security.wss.edit':'zato.server.service.internal.security.wss.Edit',
    'zato.security.wss.get-list':'zato.server.service.internal.security.wss.GetList',

    # Security - Vault - Connections
    'zato.security.vault.connection.create':'zato.server.service.internal.security.vault.connection.Create',
    'zato.security.vault.connection.delete':'zato.server.service.internal.security.vault.connection.Delete',
    'zato.security.vault.connection.edit':'zato.server.service.internal.security.vault.connection.Edit',
    'zato.security.vault.connection.get-list':'zato.server.service.internal.security.vault.connection.GetList',

    # Security - Vault - Policies
    'zato.security.vault.policy.create':'zato.server.service.internal.security.vault.policy.Create',
    'zato.security.vault.policy.delete':'zato.server.service.internal.security.vault.policy.Delete',
    'zato.security.vault.policy.edit':'zato.server.service.internal.security.vault.policy.Edit',
    'zato.security.vault.policy.get-list':'zato.server.service.internal.security.vault.policy.GetList',

    # Security - XPath
    'zato.security.xpath.change-password':'zato.server.service.internal.security.xpath.ChangePassword',
    'zato.security.xpath.create':'zato.server.service.internal.security.xpath.Create',
    'zato.security.xpath.delete':'zato.server.service.internal.security.xpath.Delete',
    'zato.security.xpath.edit':'zato.server.service.internal.security.xpath.Edit',
    'zato.security.xpath.get-list':'zato.server.service.internal.security.xpath.GetList',

    # Servers
    'zato.server.delete':'zato.server.service.internal.server.Delete',
    'zato.server.edit':'zato.server.service.internal.server.Edit',
    'zato.server.get-by-id':'zato.server.service.internal.server.GetByID',

    # Services
    'zato.service.configure-request-response':'zato.server.service.internal.service.ConfigureRequestResponse',
    'zato.service.delete':'zato.server.service.internal.service.Delete',
    'zato.service.edit':'zato.server.service.internal.service.Edit',
    'zato.service.get-by-name':'zato.server.service.internal.service.GetByName',
    'zato.service.get-channel-list':'zato.server.service.internal.service.GetChannelList',
    'zato.service.get-deployment-info-list':'zato.server.service.internal.service.GetDeploymentInfoList',
    'zato.service.get-list':'zato.server.service.internal.service.GetList',
    'zato.service.get-request-response':'zato.server.service.internal.service.GetRequestResponse',
    'zato.service.get-source-info':'zato.server.service.internal.service.GetSourceInfo',
    'zato.service.get-wsdl':'zato.server.service.internal.service.GetWSDL',
    'zato.service.has-wsdl':'zato.server.service.internal.service.HasWSDL',
    'zato.service.invoke':'zato.server.service.internal.service.Invoke',
    'zato.service.set-wsdl':'zato.server.service.internal.service.SetWSDL',
    'zato.service.slow-response.get':'zato.server.service.internal.service.GetSlowResponse',
    'zato.service.slow-response.get-list':'zato.server.service.internal.service.GetSlowResponseList',
    'zato.service.upload-package':'zato.server.service.internal.service.UploadPackage',
    'pub.zato.service.service-invoker':'zato.server.service.internal.service.ServiceInvoker',

    # Statistics
    'zato.stats.delete':'zato.server.service.internal.stats.Delete',
    'zato.stats.get-by-service':'zato.server.service.internal.stats.GetByService',
    'zato.stats.summary.get-summary-by-day':'zato.server.service.internal.stats.summary.GetSummaryByDay',
    'zato.stats.summary.get-summary-by-month':'zato.server.service.internal.stats.summary.GetSummaryByMonth',
    'zato.stats.summary.get-summary-by-range':'zato.server.service.internal.stats.summary.GetSummaryByRange',
    'zato.stats.summary.get-summary-by-week':'zato.server.service.internal.stats.summary.GetSummaryByWeek',
    'zato.stats.summary.get-summary-by-year':'zato.server.service.internal.stats.summary.GetSummaryByYear',
    'zato.stats.trends.get-trends':'zato.server.service.internal.stats.trends.GetTrends',
}

# ################################################################################################################################

def new_password():
    return uuid4().hex

# ################################################################################################################################

class Create(ZatoCommand):
    """ Creates a new Zato cluster in the ODB
    """
    opts = deepcopy(common_odb_opts)

    opts.append({'name':'lb_host', 'help':"Load-balancer host"})
    opts.append({'name':'lb_port', 'help':'Load-balancer port'})
    opts.append({'name':'lb_agent_port', 'help':'Load-balancer agent host'})
    opts.append({'name':'broker_host', 'help':"Redis host"})
    opts.append({'name':'broker_port', 'help':'Redis port'})
    opts.append({'name':'cluster_name', 'help':'Name of the cluster to create'})

    opts += get_tech_account_opts('for web-admin instances to use')

    def execute(self, args, show_output=True):

        engine = self._get_engine(args)
        session = self._get_session(engine)

        cluster = Cluster()
        cluster.name = args.cluster_name
        cluster.description = 'Created by {} on {} (UTC)'.format(self._get_user_host(), datetime.utcnow().isoformat())

        for name in(
              'odb_type', 'odb_host', 'odb_port', 'odb_user', 'odb_db_name',
              'broker_host', 'broker_port', 'lb_host', 'lb_port', 'lb_agent_port'):
            setattr(cluster, name, getattr(args, name))
        session.add(cluster)

        # TODO: getattrs below should be squared away - one of the attrs should win
        #       and the other one should be get ridden of.
        admin_invoke_sec = HTTPBasicAuth(
            None, 'admin.invoke', True, 'admin.invoke', 'Zato admin invoke', getattr(
                args, 'admin_invoke_password', None) or getattr(args, 'tech_account_password'), cluster)
        session.add(admin_invoke_sec)

        pubapi_sec = HTTPBasicAuth(None, 'pubapi', True, 'pubapi', 'Zato public API', new_password(), cluster)
        session.add(pubapi_sec)

        internal_invoke_sec = HTTPBasicAuth(None, 'zato.internal.invoke', True, 'zato.internal.invoke.user',
            'Zato internal invoker', new_password(), cluster)
        session.add(internal_invoke_sec)

        self.add_default_rbac_permissions(session, cluster)
        root_rbac_role = self.add_default_rbac_roles(session, cluster)
        ide_pub_rbac_role = self.add_rbac_role_and_acct(
            session, cluster, root_rbac_role, 'IDE Publishers', 'ide_publisher', 'ide_publisher')

        self.add_internal_services(session, cluster, admin_invoke_sec, pubapi_sec, internal_invoke_sec, ide_pub_rbac_role)

        self.add_ping_services(session, cluster)
        self.add_default_cache(session, cluster)
        self.add_cache_endpoints(session, cluster)
        self.add_crypto_endpoints(session, cluster)
        self.add_pubsub_sec_endpoints(session, cluster)

        # For IBM MQ connections / connectors
        self.add_internal_callback_wmq(session, cluster)

        # SSO
        self.add_sso_endpoints(session, cluster)

        try:
            session.commit()
        except IntegrityError as e:
            msg = 'SQL IntegrityError caught `{}`'.format(e.message)
            if self.verbose:
                msg += '\nDetails:`{}`'.format(format_exc().decode('utf-8'))
                self.logger.error(msg)
            self.logger.error(msg)
            session.rollback()

            return self.SYS_ERROR.CLUSTER_NAME_ALREADY_EXISTS

        if show_output:
            if self.verbose:
                msg = 'Successfully created a new cluster [{}]'.format(args.cluster_name)
                self.logger.debug(msg)
            else:
                self.logger.info('OK')

# ################################################################################################################################

    def add_api_invoke(self, session, cluster, service, pubapi_sec):
        channel = HTTPSOAP(None, '/zato/api/invoke', True, True, 'channel', 'plain_http',
            None, '/zato/api/invoke/{service_name}', None, '', None, None, merge_url_params_req=True, service=service,
            cluster=cluster)
        session.add(channel)

# ################################################################################################################################

    def add_internal_services(self, session, cluster, admin_invoke_sec, pubapi_sec, internal_invoke_sec, ide_pub_rbac_role):
        """ Adds these Zato internal services that can be accessed through SOAP requests.
        """
        #
        # HTTPSOAP + services
        #

        for name, impl_name in iteritems(zato_services):

            service = Service(None, name, True, impl_name, True, cluster)
            session.add(service)

            # Add the HTTP channel for WSDLs
            if name == 'zato.service.get-wsdl':
                http_soap = HTTPSOAP(
                    None, '{}.soap'.format(name), True, True, 'channel', 'plain_http',
                    None, '/zato/wsdl', None, '', None, None, service=service, cluster=cluster)
                session.add(http_soap)

            elif name == 'pub.zato.service.service-invoker':
                self.add_api_invoke(session, cluster, service, pubapi_sec)

            elif name == 'zato.service.invoke':
                self.add_admin_invoke(session, cluster, service, admin_invoke_sec)
                self.add_internal_invoke(session, cluster, service, internal_invoke_sec)

            elif name == 'zato.security.jwt.log-in':
                self.add_jwt_log_in(session, cluster, service)

            elif name == 'zato.security.jwt.log-out':
                self.add_jwt_log_out(session, cluster, service)

            elif name == 'zato.ide-deploy.create':
                self.add_rbac_channel(session, cluster, service, ide_pub_rbac_role, '/ide-deploy', permit_write=True,
                    data_format=DATA_FORMAT.JSON)

            elif 'check' in name:
                self.add_check(session, cluster, service, pubapi_sec)

            session.add(get_http_soap_channel(name, service, cluster, pubapi_sec))
            session.add(get_http_json_channel(name, service, cluster, pubapi_sec))

# ################################################################################################################################

    def add_ping_services(self, session, cluster):
        """ Adds a ping service and channels, with and without security checks.
        """
        passwords = {
            'ping.plain_http.basic_auth': None,
            'ping.soap.basic_auth': None,
            'ping.soap.wss.clear_text': None,
        }

        for password in passwords:
            passwords[password] = new_password()

        ping_impl_name = 'zato.server.service.internal.Ping'
        ping_service_name = 'zato.ping'
        ping_service = Service(None, ping_service_name, True, ping_impl_name, True, cluster)
        session.add(ping_service)

        #
        # .. no security ..
        #
        # TODO
        # Change it to /zato/json/ping
        # and add an actual /zato/ping with no data format specified.
        ping_no_sec_channel = HTTPSOAP(
            None, 'zato.ping', True, True, 'channel',
            'plain_http', None, '/zato/ping', None, '', None, SIMPLE_IO.FORMAT.JSON, service=ping_service, cluster=cluster)
        session.add(ping_no_sec_channel)

        #
        # All the possible options
        #
        # Plain HTTP / Basic auth
        # SOAP / Basic auth
        # SOAP / WSS / Clear text
        #

        transports = ['plain_http', 'soap']
        wss_types = ['clear_text']

        for transport in transports:

            if transport == 'plain_http':
                data_format = SIMPLE_IO.FORMAT.JSON
            else:
                data_format = SIMPLE_IO.FORMAT.XML

            base_name = 'ping.{0}.basic_auth'.format(transport)
            zato_name = 'zato.{0}'.format(base_name)
            url = '/zato/{0}'.format(base_name)
            soap_action, soap_version = (zato_name, '1.1') if transport == 'soap' else ('', None)
            password = passwords[base_name]

            sec = HTTPBasicAuth(None, zato_name, True, zato_name, 'Zato ping', password, cluster)
            session.add(sec)

            channel = HTTPSOAP(
                None, zato_name, True, True, 'channel', transport, None, url, None, soap_action,
                soap_version, data_format, service=ping_service, security=sec, cluster=cluster)
            session.add(channel)

            if transport == 'soap':
                for wss_type in wss_types:
                    base_name = 'ping.{0}.wss.{1}'.format(transport, wss_type)
                    zato_name = 'zato.{0}'.format(base_name)
                    url = '/zato/{0}'.format(base_name)
                    password = passwords[base_name]

                    sec = WSSDefinition(None, zato_name, True, zato_name, password, wss_type, False, True, 3600, 3600, cluster)
                    session.add(sec)

                    channel = HTTPSOAP(
                        None, zato_name, True, True, 'channel', transport, None, url, None, soap_action,
                        soap_version, data_format, service=ping_service, security=sec, cluster=cluster)
                    session.add(channel)

# ################################################################################################################################

    def add_admin_invoke(self, session, cluster, service, admin_invoke_sec):
        """ Adds an admin channel for invoking services from web admin and CLI.
        """
        channel = HTTPSOAP(
            None, 'admin.invoke.json', True, True, 'channel', 'plain_http',
            None, '/zato/admin/invoke', None, '', None, SIMPLE_IO.FORMAT.JSON, service=service, cluster=cluster,
            security=admin_invoke_sec)
        session.add(channel)

# ################################################################################################################################

    def add_internal_invoke(self, session, cluster, service, internal_invoke_sec):
        """ Adds an internal channel for invoking services from other servers.
        """
        channel = HTTPSOAP(
            None, 'zato.internal.invoke', True, True, 'channel', 'plain_http',
            None, '/zato/internal/invoke', None, '', None, SIMPLE_IO.FORMAT.JSON, service=service, cluster=cluster,
            security=internal_invoke_sec)
        session.add(channel)

# ################################################################################################################################

    def add_default_rbac_permissions(self, session, cluster):
        """ Adds default CRUD permissions used by RBAC.
        """
        for name in('Create', 'Read', 'Update', 'Delete'):
            item = RBACPermission()
            item.name = name
            item.cluster = cluster
            session.add(item)

# ################################################################################################################################

    def add_default_rbac_roles(self, session, cluster):
        """ Adds default roles used by RBAC.
        """
        root = RBACRole(name='Root', parent=None, cluster=cluster)
        session.add(root)
        return root

# ################################################################################################################################

    def add_rbac_role_and_acct(self, session, cluster, root_rbac_role, role_name, account_name, realm):
        """ Create an RBAC role alongside a default account and random password for accessing it via Basic Auth.

        :param session: SQLAlchemy session instance
        :param cluster: Cluster model instance
        :param root_rbac_role: RBACRole model instance for the root role
        :param role_name: "My Descriptive RBAC Role Name"
        :param account_name: "my_default_rbac_user"
        :param realm: "http_auth_service_realm"
        :return: New RBACRole model instance
        """
        role = RBACRole(name=role_name, parent=root_rbac_role, cluster=cluster)
        session.add(role)

        auth = HTTPBasicAuth(None, account_name, True, account_name, realm, new_password(), cluster)
        session.add(auth)

        client_role_def = MISC.SEPARATOR.join(('sec_def', 'basic_auth', account_name))
        client_role_name = MISC.SEPARATOR.join((client_role_def, role.name))
        client_role = RBACClientRole(name=client_role_name, client_def=client_role_def, role=role, cluster=cluster)
        session.add(client_role)

        return role

# ################################################################################################################################

    def add_default_cache(self, session, cluster):
        """ Adds default cache to cluster.
        """
        item = CacheBuiltin()
        item.cluster = cluster
        item.name = 'default'
        item.is_active = True
        item.is_default = True
        item.max_size = CACHE.DEFAULT.MAX_SIZE
        item.max_item_size = CACHE.DEFAULT.MAX_ITEM_SIZE
        item.extend_expiry_on_get = True
        item.extend_expiry_on_set = True
        item.cache_type = CACHE.TYPE.BUILTIN
        item.sync_method = CACHE.SYNC_METHOD.IN_BACKGROUND.id
        item.persistent_storage = CACHE.PERSISTENT_STORAGE.SQL.id
        session.add(item)

# ################################################################################################################################

    def add_jwt_log_in(self, session, cluster, service):
        channel = HTTPSOAP(None, 'zato.security.jwt.log-in', True, True, 'channel', 'plain_http',
            None, '/zato/jwt/log-in', None, '', None, DATA_FORMAT.JSON, merge_url_params_req=True, service=service,
            cluster=cluster)
        session.add(channel)

# ################################################################################################################################

    def add_jwt_log_out(self, session, cluster, service):
        channel = HTTPSOAP(None, 'zato.security.jwt.log-out', True, True, 'channel', 'plain_http',
            None, '/zato/jwt/log-out', None, '', None, DATA_FORMAT.JSON, merge_url_params_req=True, service=service,
            cluster=cluster)
        session.add(channel)

# ################################################################################################################################

    def add_rbac_channel(self, session, cluster, service, rbac_role, url_path, permit_read=True, permit_write=False, **kwargs):
        """ Create an RBAC-authenticated plain HTTP channel associated with a service.

        :param session: SQLAlchemy session instance
        :param cluster: Cluster model instance
        :param service: Service model instance
        :param rbac_role: RBACRole model instance
        :param url_path: "/url/path" to expose service as
        """
        name = 'admin.' + service.name.replace('zato.', '')
        channel = HTTPSOAP(name=name, is_active=True, is_internal=True, connection='channel', transport='plain_http',
            url_path=url_path, soap_action='', has_rbac=True, sec_use_rbac=True, merge_url_params_req=True, service=service,
            cluster=cluster, **kwargs)
        session.add(channel)

        perms = []
        for permitted, perm_names in ((permit_read, ('Read',)), (permit_write, ('Create', 'Update'))):
            if permitted:
                perms.extend(session.query(RBACPermission).\
                    filter(RBACPermission.name.in_(perm_names)))

        for perm in perms:
            session.add(RBACRolePermission(role=rbac_role, perm=perm, service=service, cluster=cluster))

# ################################################################################################################################

    def add_check(self, session, cluster, service, pubapi_sec):

        data_formats = [DATA_FORMAT.JSON, DATA_FORMAT.XML]
        for data_format in data_formats:

            name = 'zato.checks.{}.{}'.format(data_format, service.name)
            url_path = '/zato/checks/{}/{}'.format(data_format, service.name)

            channel = HTTPSOAP(None, name, True, True, 'channel', 'plain_http', None, url_path, None, '', None, data_format,
                merge_url_params_req=True, service=service, cluster=cluster, security=pubapi_sec)
            session.add(channel)

# ################################################################################################################################

    def add_cache_endpoints(self, session, cluster):

        service_to_endpoint = {

            # For single keys
            'zato.cache.builtin.pubapi.single-key-service':  '/zato/cache/{key}',

            # Multi-key delete
            'zato.cache.builtin.pubapi.delete-by-prefix':    '/zato/cache/delete/by-prefix/{key}',
            'zato.cache.builtin.pubapi.delete-by-regex':     '/zato/cache/delete/by-regex/{key}',
            'zato.cache.builtin.pubapi.delete-by-suffix':    '/zato/cache/delete/by-suffix/{key}',
            'zato.cache.builtin.pubapi.delete-contains':     '/zato/cache/delete/contains/{key}',
            'zato.cache.builtin.pubapi.delete-not-contains': '/zato/cache/delete/not-contains/{key}',
            'zato.cache.builtin.pubapi.delete-contains-all': '/zato/cache/delete/contains-all',
            'zato.cache.builtin.pubapi.delete-contains-any': '/zato/cache/delete/contains-any',

            # Multi-key expire
            'zato.cache.builtin.pubapi.expire-by-prefix':    '/zato/cache/expire/by-prefix/{key}',
            'zato.cache.builtin.pubapi.expire-by-regex':     '/zato/cache/expire/by-prefix/{key}',
            'zato.cache.builtin.pubapi.expire-by-suffix':    '/zato/cache/expire/by-suffix/{key}',
            'zato.cache.builtin.pubapi.expire-contains':     '/zato/cache/expire/contains/{key}',
            'zato.cache.builtin.pubapi.expire-not-contains': '/zato/cache/expire/not-contains/{key}',
            'zato.cache.builtin.pubapi.expire-contains-all': '/zato/cache/expire/contains-all',
            'zato.cache.builtin.pubapi.expire-contains-any': '/zato/cache/expire/contains-any',

            # Multi-key set
            'zato.cache.builtin.pubapi.set-by-prefix':       '/zato/cache/set/by-prefix/{key}',
            'zato.cache.builtin.pubapi.set-by-regex':        '/zato/cache/set/by-regex/{key}',
            'zato.cache.builtin.pubapi.set-by-suffix':       '/zato/cache/set/by-suffix/{key}',
            'zato.cache.builtin.pubapi.set-contains':        '/zato/cache/set/contains/{key}',
            'zato.cache.builtin.pubapi.set-not-contains':    '/zato/cache/set/not-contains/{key}',
            'zato.cache.builtin.pubapi.set-contains-all':    '/zato/cache/set/contains-all',
            'zato.cache.builtin.pubapi.set-contains-any':    '/zato/cache/set/contains-any',
        }

        service_to_impl = {

            # For single keys
            'zato.cache.builtin.pubapi.single-key-service':  'zato.server.service.internal.cache.builtin.pubapi.SingleKeyService',

            # Multi-key delete
            'zato.cache.builtin.pubapi.delete-by-prefix':    'zato.server.service.internal.cache.builtin.pubapi.DeleteByPrefix',
            'zato.cache.builtin.pubapi.delete-by-regex':     'zato.server.service.internal.cache.builtin.pubapi.DeleteByRegex',
            'zato.cache.builtin.pubapi.delete-by-suffix':    'zato.server.service.internal.cache.builtin.pubapi.DeleteBySuffix',
            'zato.cache.builtin.pubapi.delete-contains':     'zato.server.service.internal.cache.builtin.pubapi.DeleteContains',
            'zato.cache.builtin.pubapi.delete-not-contains': 'zato.server.service.internal.cache.builtin.pubapi.DeleteNotContains',
            'zato.cache.builtin.pubapi.delete-contains-all': 'zato.server.service.internal.cache.builtin.pubapi.DeleteContainsAll',
            'zato.cache.builtin.pubapi.delete-contains-any': 'zato.server.service.internal.cache.builtin.pubapi.DeleteContainsAny',

            # Multi-key expire
            'zato.cache.builtin.pubapi.expire-by-prefix':    'zato.server.service.internal.cache.builtin.pubapi.ExpireByPrefix',
            'zato.cache.builtin.pubapi.expire-by-regex':     'zato.server.service.internal.cache.builtin.pubapi.ExpireByRegex',
            'zato.cache.builtin.pubapi.expire-by-suffix':    'zato.server.service.internal.cache.builtin.pubapi.ExpireBySuffix',
            'zato.cache.builtin.pubapi.expire-contains':     'zato.server.service.internal.cache.builtin.pubapi.ExpireContains',
            'zato.cache.builtin.pubapi.expire-not-contains': 'zato.server.service.internal.cache.builtin.pubapi.ExpireNotContains',
            'zato.cache.builtin.pubapi.expire-contains-all': 'zato.server.service.internal.cache.builtin.pubapi.ExpireContainsAll',
            'zato.cache.builtin.pubapi.expire-contains-any': 'zato.server.service.internal.cache.builtin.pubapi.ExpireContainsAny',

            # Multi-key set
            'zato.cache.builtin.pubapi.set-by-prefix':       'zato.server.service.internal.cache.builtin.pubapi.SetByPrefix',
            'zato.cache.builtin.pubapi.set-by-regex':        'zato.server.service.internal.cache.builtin.pubapi.SetByRegex',
            'zato.cache.builtin.pubapi.set-by-suffix':       'zato.server.service.internal.cache.builtin.pubapi.SetBySuffix',
            'zato.cache.builtin.pubapi.set-contains':        'zato.server.service.internal.cache.builtin.pubapi.SetContains',
            'zato.cache.builtin.pubapi.set-not-contains':    'zato.server.service.internal.cache.builtin.pubapi.SetNotContains',
            'zato.cache.builtin.pubapi.set-contains-all':    'zato.server.service.internal.cache.builtin.pubapi.SetContainsAll',
            'zato.cache.builtin.pubapi.set-contains-any':    'zato.server.service.internal.cache.builtin.pubapi.SetContainsAny',
        }

        sec = HTTPBasicAuth(None, 'zato.default.cache.client', True, 'zato.cache', 'Zato cache', new_password(), cluster)
        session.add(sec)

        for name, impl_name in iteritems(service_to_impl):

            service = Service(None, name, True, impl_name, True, cluster)
            session.add(service)

            url_path = service_to_endpoint[name]

            http_soap = HTTPSOAP(None, name, True, True, 'channel', 'plain_http', None, url_path, None, '',
                None, DATA_FORMAT.JSON, security=None, service=service, cluster=cluster)

            session.add(http_soap)

# ################################################################################################################################

    def add_crypto_endpoints(self, session, cluster):

        service_to_endpoint = {
            'zato.crypto.encrypt':  '/zato/crypto/encrypt',
            'zato.crypto.decrypt':  '/zato/crypto/decrypt',
            'zato.crypto.hash-secret':  '/zato/crypto/hash-secret',
            'zato.crypto.verify-hash':  '/zato/crypto/verify-hash',
            'zato.crypto.generate-secret':  '/zato/crypto/generate-secret',
            'zato.crypto.generate-password':  '/zato/crypto/generate-password',
        }

        service_to_impl = {
            'zato.crypto.encrypt':  'zato.server.service.internal.crypto.Encrypt',
            'zato.crypto.decrypt':  'zato.server.service.internal.crypto.Decrypt',
            'zato.crypto.hash-secret':  'zato.server.service.internal.crypto.HashSecret',
            'zato.crypto.verify-hash':  'zato.server.service.internal.crypto.VerifyHash',
            'zato.crypto.generate-secret':  'zato.server.service.internal.crypto.GenerateSecret',
            'zato.crypto.generate-password':  'zato.server.service.internal.crypto.GeneratePassword',
        }

        sec = HTTPBasicAuth(None, 'zato.default.crypto.client', True, 'zato.crypto', 'Zato crypto', new_password(), cluster)
        session.add(sec)

        for name, impl_name in iteritems(service_to_impl):

            service = Service(None, name, True, impl_name, True, cluster)
            session.add(service)

            url_path = service_to_endpoint[name]

            http_soap = HTTPSOAP(None, name, True, True, 'channel', 'plain_http', None, url_path, None, '',
                None, DATA_FORMAT.JSON, security=None, service=service, cluster=cluster)

            session.add(http_soap)

# ################################################################################################################################

    def add_pubsub_sec_endpoints(self, session, cluster):

        sec_demo = HTTPBasicAuth(None, 'zato.pubsub.demo.secdef', True, 'zato.pubsub.demo', 'Zato pub/sub demo', new_password(), cluster)
        session.add(sec_demo)

        sec_default_internal = HTTPBasicAuth(None, 'zato.pubsub.internal.secdef', True, 'zato.pubsub.internal',
            'Zato pub/sub internal', new_password(), cluster)
        session.add(sec_default_internal)

        impl_name1 = 'zato.server.service.internal.pubsub.pubapi.TopicService'
        impl_name2 = 'zato.server.service.internal.pubsub.pubapi.SubscribeService'
        impl_name3 = 'zato.server.service.internal.pubsub.pubapi.MessageService'
        impl_demo = 'zato.server.service.internal.helpers.JSONRawRequestLogger'

        service_topic = Service(None, 'zato.pubsub.pubapi.topic-service', True, impl_name1, True, cluster)
        service_sub = Service(None, 'zato.pubsub.pubapi.subscribe-service', True, impl_name2, True, cluster)
        service_msg = Service(None, 'zato.pubsub.pubapi.message-service', True, impl_name3, True, cluster)
        service_demo = Service(None, 'zato.pubsub.helpers.json-raw-request-logger', True, impl_demo, True, cluster)

        # Opaque data that lets clients use topic contain slash characters
        opaque = dumps({'match_slash':True})

        chan_topic = HTTPSOAP(None, 'zato.pubsub.topic.topic_name', True, True, CONNECTION.CHANNEL,
            URL_TYPE.PLAIN_HTTP, None, '/zato/pubsub/topic/{topic_name}',
            None, '', None, DATA_FORMAT.JSON, security=None, service=service_topic, opaque=opaque,
            cluster=cluster)

        chan_sub = HTTPSOAP(None, 'zato.pubsub.subscribe.topic.topic_name', True, True, CONNECTION.CHANNEL,
            URL_TYPE.PLAIN_HTTP, None, '/zato/pubsub/subscribe/topic/{topic_name}',
            None, '', None, DATA_FORMAT.JSON, security=None, service=service_sub, opaque=opaque,
            cluster=cluster)

        chan_msg = HTTPSOAP(None, 'zato.pubsub.msg.msg_id', True, True, CONNECTION.CHANNEL,
            URL_TYPE.PLAIN_HTTP, None, '/zato/pubsub/msg/{msg_id}',
            None, '', None, DATA_FORMAT.JSON, security=None, service=service_msg, opaque=opaque,
            cluster=cluster)

        chan_demo = HTTPSOAP(None, 'pubsub.demo.sample.channel', True, True, CONNECTION.CHANNEL,
            URL_TYPE.PLAIN_HTTP, None, '/zato/pubsub/zato.demo.sample',
            None, '', None, DATA_FORMAT.JSON, security=sec_demo, service=service_demo, opaque=opaque,
            cluster=cluster)

        outconn_demo = HTTPSOAP(None, 'pubsub.demo.sample.outconn', True, True, CONNECTION.OUTGOING,
            URL_TYPE.PLAIN_HTTP, 'http://localhost:11223', '/zato/pubsub/zato.demo.sample',
            None, '', None, DATA_FORMAT.JSON, security=sec_demo, opaque=opaque,
            cluster=cluster)

        endpoint_default_internal = PubSubEndpoint()
        endpoint_default_internal.name = PUBSUB.DEFAULT.INTERNAL_ENDPOINT_NAME
        endpoint_default_internal.is_internal = True
        endpoint_default_internal.role = PUBSUB.ROLE.PUBLISHER_SUBSCRIBER.id
        endpoint_default_internal.topic_patterns = 'pub=/*\nsub=/*'
        endpoint_default_internal.security = sec_default_internal
        endpoint_default_internal.cluster = cluster
        endpoint_default_internal.endpoint_type = PUBSUB.ENDPOINT_TYPE.INTERNAL.id

        endpoint_demo = PubSubEndpoint()
        endpoint_demo.name = 'zato.pubsub.demo.endpoint'
        endpoint_demo.is_internal = True
        endpoint_demo.role = PUBSUB.ROLE.PUBLISHER_SUBSCRIBER.id
        endpoint_demo.topic_patterns = 'pub=/zato/demo/*\nsub=/zato/demo/*'
        endpoint_demo.security = sec_demo
        endpoint_demo.cluster = cluster
        endpoint_demo.endpoint_type = PUBSUB.ENDPOINT_TYPE.REST.id

        topic = PubSubTopic()
        topic.name = '/zato/demo/sample'
        topic.is_active = True
        topic.is_api_sub_allowed = True
        topic.is_internal = True
        topic.max_depth = 100
        topic.has_gd = False
        topic.cluster = cluster

        sub = PubSubSubscription()
        sub.creation_time = utcnow_as_ms()
        sub.topic = topic
        sub.endpoint = endpoint_demo
        sub.sub_key = new_sub_key(endpoint_demo.endpoint_type)
        sub.has_gd = False
        sub.sub_pattern_matched = 'sub=/zato/demo/*'
        sub.active_status = PUBSUB.QUEUE_ACTIVE_STATUS.FULLY_ENABLED.id
        sub.cluster = cluster
        sub.wrap_one_msg_in_list = False
        sub.delivery_err_should_block = False
        sub.out_http_soap = outconn_demo

        session.add(endpoint_default_internal)
        session.add(endpoint_demo)
        session.add(topic)
        session.add(sub)

        session.add(service_topic)
        session.add(service_sub)
        session.add(service_msg)

        session.add(chan_topic)
        session.add(chan_sub)
        session.add(chan_msg)

        session.add(chan_demo)
        session.add(outconn_demo)

# ################################################################################################################################

    def add_internal_callback_wmq(self, session, cluster):
        impl_name = 'zato.server.service.internal.channel.jms_wmq.OnMessageReceived'
        service = Service(None, 'zato.channel.jms-wmq.on-message-received', True, impl_name, True, cluster)

        wmq_username = IPC.CONNECTOR.IBM_MQ.USERNAME
        wmq_sec = HTTPBasicAuth(None, wmq_username, True, wmq_username, 'Zato IBM MQ', new_password(), cluster)

        channel = HTTPSOAP(None, 'zato.internal.callback.wmq', True, True, 'channel', 'plain_http', None,
            '/zato/internal/callback/wmq',
            None, '', None, None, security=wmq_sec, service=service, cluster=cluster)

        session.add(wmq_sec)
        session.add(service)
        session.add(channel)

# ################################################################################################################################

    def add_sso_endpoints(self, session, cluster):

        data = [
            ['zato.sso.user.create', 'zato.server.service.internal.sso.user.Create', '/zato/sso/user/create'],
            ['zato.sso.user.signup', 'zato.server.service.internal.sso.user.Signup', '/zato/sso/user/signup'],
            ['zato.sso.user.approve', 'zato.server.service.internal.sso.user.Approve', '/zato/sso/user/approve'],
            ['zato.sso.user.reject', 'zato.server.service.internal.sso.user.Reject', '/zato/sso/user/reject'],
            ['zato.sso.user.login', 'zato.server.service.internal.sso.user.Login', '/zato/sso/user/login'],
            ['zato.sso.user.logout', 'zato.server.service.internal.sso.user.Logout', '/zato/sso/user/logout'],
            ['zato.sso.user.user', 'zato.server.service.internal.sso.user.User', '/zato/sso/user'],
            ['zato.sso.user.password', 'zato.server.service.internal.sso.user.Password', '/zato/sso/user/password'],
            ['zato.sso.user.search', 'zato.server.service.internal.sso.user.Search', '/zato/sso/user/search'],

            ['zato.sso.session.session', 'zato.server.service.internal.sso.session.Session', '/zato/sso/user/session'],

            ['zato.sso.user.password-reset.begin', 'zato.server.service.internal.sso.password_reset.Begin', '/zato/sso/user/password/reset/begin'],
            ['zato.sso.user.password-reset.complete', 'zato.server.service.internal.sso.password_reset.Complete', '/zato/sso/user/password/reset/complete'],

            ['zato.sso.user-attr.user-attr', 'zato.server.service.internal.sso.user_attr.UserAttr', '/zato/sso/user/attr'],
            ['zato.sso.user-attr.user-attr-exists', 'zato.server.service.internal.sso.user_attr.UserAttrExists', '/zato/sso/user/attr/exists'],
            ['zato.sso.user-attr.user-attr-names', 'zato.server.service.internal.sso.user_attr.UserAttrNames', '/zato/sso/user/attr/names'],

            ['zato.sso.session-attr.session-attr', 'zato.server.service.internal.sso.session_attr.SessionAttr', '/zato/sso/session/attr'],
            ['zato.sso.session-attr.session-attr-exists', 'zato.server.service.internal.sso.session_attr.SessionAttrExists', '/zato/sso/session/attr/exists'],
            ['zato.sso.session-attr.session-attr-names', 'zato.server.service.internal.sso.session_attr.SessionAttrNames', '/zato/sso/session/attr/names'],
        ]

        for name, impl_name, url_path in data:
            service = Service(None, name, True, impl_name, True, cluster)
            channel = HTTPSOAP(None, url_path, True, True, 'channel', 'plain_http', None, url_path, None, '', None,
                DATA_FORMAT.JSON, security=None, service=service, cluster=cluster)

            session.add(service)
            session.add(channel)

# ################################################################################################################################
