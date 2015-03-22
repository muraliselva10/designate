# Copyright 2012 Managed I.T.
#
# Author: Kiall Mac Innes <kiall@managedit.ie>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import abc
import copy

from oslo.config import cfg
from oslo_log import log as logging

from designate.i18n import _LI
from designate.context import DesignateContext
from designate.plugin import DriverPlugin
from designate import objects


LOG = logging.getLogger(__name__)


class Backend(DriverPlugin):
    """Base class for backend implementations"""
    __plugin_type__ = 'backend'
    __plugin_ns__ = 'designate.backend'

    def __init__(self, backend_options):
        super(Backend, self).__init__()
        self.backend_options = backend_options

        self.admin_context = DesignateContext.get_admin_context()
        self.admin_context.all_tenants = True

    def start(self):
        LOG.info(_LI('Starting %s backend'), self.get_canonical_name())

    def stop(self):
        LOG.info(_LI('Stopped %s backend'), self.get_canonical_name())

    # Config Methods
    @classmethod
    def get_cfg_opts(cls):
        group = cfg.OptGroup(
            name=cls.get_canonical_name(),
            title='Backend options for %s Backend' % cls.get_plugin_name()
        )

        opts = [
            cfg.ListOpt('server_ids', default=[]),
            cfg.ListOpt('masters', default=['127.0.0.1:5354'],
                        help='Comma-separated list of master DNS servers, in '
                             '<ip-address>:<port> format. If <port> is '
                             'omitted, the default 5354 is used. These are '
                             'mdns servers.'),
        ]

        opts.extend(cls._get_common_cfg_opts())
        opts.extend(cls._get_global_cfg_opts())

        return [(group, opts)]

    @classmethod
    def get_extra_cfg_opts(cls):
        # Common options for all backends
        opts = [
            cfg.ListOpt('masters'),
            cfg.StrOpt('host', default='127.0.0.1', help='Server Host'),
            cfg.IntOpt('port', default=53, help='Server Port'),
            cfg.StrOpt('tsig-key', help='Server TSIG Key'),
        ]

        # Backend specific common options
        common_cfg_opts = copy.deepcopy(cls._get_common_cfg_opts())

        # Ensure the default value for all common options is reset to None
        for opt in common_cfg_opts:
            opt.default = None

        opts.extend(common_cfg_opts)

        # Add any server only config options
        opts.extend(cls._get_server_cfg_opts())

        result = []
        global_group = cls.get_canonical_name()

        for server_id in cfg.CONF[global_group].server_ids:
            group = cfg.OptGroup(name='%s:%s' % (global_group, server_id))
            result.append((group, opts))

        return result

    @classmethod
    def _get_common_cfg_opts(cls):
        return []

    @classmethod
    def _get_global_cfg_opts(cls):
        return []

    @classmethod
    def _get_server_cfg_opts(cls):
        return []

    def get_backend_option(self, key):
        """
        Get the backend option value using the backend option key.
        """
        for backend_option in self.backend_options:
            if backend_option['key'] == key:
                return backend_option['value']

    # Pool Mgr Object Creation
    @classmethod
    def _create_server_object(cls, backend, server_id, backend_options,
                              server_section_name):
        """
        Create the server object.
        """
        server_values = {
            'id': server_id,
            'host': cfg.CONF[server_section_name].host,
            'port': cfg.CONF[server_section_name].port,
            'backend': backend,
            'backend_options': backend_options,
            'tsig_key': cfg.CONF[server_section_name].tsig_key
        }
        return objects.PoolServer(**server_values)

    @classmethod
    def _create_backend_option_objects(cls, global_section_name,
                                       server_section_name):
        """
        Create the backend_option object list.
        """
        backend_options = []
        for key in cfg.CONF[global_section_name].keys():
            backend_option = cls._create_backend_option_object(
                key, global_section_name, server_section_name)
            backend_options.append(backend_option)
        return backend_options

    @classmethod
    def _create_backend_option_object(cls, key, global_section_name,
                                      server_section_name):
        """
        Create the backend_option object.  If a server specific backend option
        value exists, use it.  Otherwise use the global backend option value.
        """
        value = None
        try:
            value = cfg.CONF[server_section_name].get(key)
        except cfg.NoSuchOptError:
            pass

        if value is None:
            value = cfg.CONF[global_section_name].get(key)

        backend_option_values = {
            'key': key,
            'value': value
        }
        return objects.BackendOption(**backend_option_values)

    @classmethod
    def get_server_object(cls, backend, server_id):
        """
        Get the server object from the backend driver for the server_id.
        """
        global_section_name = 'backend:%s' % (backend,)
        server_section_name = 'backend:%s:%s' % (backend, server_id)

        backend_options = cls._create_backend_option_objects(
            global_section_name, server_section_name)

        return cls._create_server_object(
            backend, server_id, backend_options, server_section_name)

    # Core Backend Interface
    @abc.abstractmethod
    def create_domain(self, context, domain):
        """
        Create a DNS domain.

        :param context: Security context information.
        :param domain: the DNS domain.
        """

    def update_domain(self, context, domain):
        pass

    @abc.abstractmethod
    def delete_domain(self, context, domain):
        """
        Delete a DNS domain.

        :param context: Security context information.
        :param domain: the DNS domain.
        """

    def ping(self, context):
        """Ping the Backend service"""

        return {
            'status': None
        }
