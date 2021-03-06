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
import time
import threading
import re
from sqlalchemy.orm import exc
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy import distinct, func
from oslo.config import cfg
from designate.openstack.common import log as logging
from designate.openstack.common.db.sqlalchemy.utils import paginate_query
from designate.openstack.common.db.sqlalchemy.utils import InvalidSortKey
from designate import exceptions
from designate.storage import base
from designate.storage.impl_sqlalchemy import models
from designate.sqlalchemy.models import SoftDeleteMixin
from designate.sqlalchemy.session import get_session
from designate.sqlalchemy.session import get_engine
from designate.sqlalchemy.session import SQLOPTS


LOG = logging.getLogger(__name__)

cfg.CONF.register_group(cfg.OptGroup(
    name='storage:sqlalchemy', title="Configuration for SQLAlchemy Storage"
))

cfg.CONF.register_opts(SQLOPTS, group='storage:sqlalchemy')


class SQLAlchemyStorage(base.Storage):
    """ SQLAlchemy connection """
    __plugin_name__ = 'sqlalchemy'

    def __init__(self):
        super(SQLAlchemyStorage, self).__init__()

        self.engine = get_engine(self.name)

        self.local_store = threading.local()

    @property
    def session(self):
        # NOTE: This uses a thread local store, allowing each greenthread to
        #       have it's own session stored correctly. Without this, each
        #       greenthread may end up using a single global session, which
        #       leads to bad things happening.

        if not hasattr(self.local_store, 'session'):
            self.local_store.session = get_session(self.name)

        return self.local_store.session

    def begin(self):
        self.session.begin(subtransactions=True)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    def setup_schema(self):
        """ Semi-Private Method to create the database schema """
        models.Base.metadata.create_all(self.session.bind)

    def teardown_schema(self):
        """ Semi-Private Method to reset the database schema """
        models.Base.metadata.drop_all(self.session.bind)

    def _apply_criterion(self, model, query, criterion):
        if criterion is not None:
            for name, value in criterion.items():
                column = getattr(model, name)

                if isinstance(value, basestring) and '%' in value:
                    query = query.filter(column.like(value))
                else:
                    query = query.filter(column == value)

        return query

    def _apply_tenant_criteria(self, context, model, query):
        if hasattr(model, 'tenant_id'):
            if context.all_tenants:
                LOG.debug('Including all tenants items in query results')
            else:
                query = query.filter(model.tenant_id == context.tenant_id)

        return query

    def _apply_deleted_criteria(self, context, model, query):
        if issubclass(model, SoftDeleteMixin):
            if context.show_deleted:
                LOG.debug('Including deleted items in query results')
            else:
                query = query.filter(model.deleted == "0")

        return query

    # modified or added by M
    # 
    def _apply_fetch_record(self, context, model, query):
        if hasattr(model, 'tenant_id'):

                # open the files
                # Modify file location if needed
                files = open("/root/flattext", "r")

                # create an empty list
                #ips = []
                tenants = []

                # read through the files
                for text in files.readlines():

                        # strip off the \n
                        text = text.rstrip()

                        # IP and Tenant Fetch
                        #regex = re.findall(r'(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})$', text)
                        regex1 = re.findall(r'[0-9A-Za-z]{32}', text)

                        #if regex is not None and regex not in ips:
                        #       ips.append(regex)

                        if regex1 is not None and regex1 not in tenants:
                                tenants.append(regex1)

                #ip_valuess = [''.join(ip) for ip in ips if ip]
                tenant_ids = [''.join(tenant) for tenant in tenants if tenant]

                # cleanup and close files
                files.close()

                query = query.filter(model.tenant_id.in_(tenant_ids))
        return query

    # For fetching the in-addr-arpa in common 
    # based on Flat file fecthing should be done
    def _apply_fetch_inaddrarpa(self, context, model, query, query1, query2, query3):
        if hasattr(model, 'tenant_id'):

		# open the files
		# Modify file location if needed
	        files = open("/root/flattext", "r")

	        # create an empty list
	        #ips = []
	        tenants = []

	        # read through the files
	        for text in files.readlines():

	                # strip off the \n
	                text = text.rstrip()

	                # IP and Tenant Fetch
	                #regex = re.findall(r'(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})$', text)
	                regex1 = re.findall(r'[0-9A-Za-z]{32}', text)

	                #if regex is not None and regex not in ips:
	                #       ips.append(regex)

	                if regex1 is not None and regex1 not in tenants:
	                        tenants.append(regex1)

		#ip_valuess = [''.join(ip) for ip in ips if ip]
		tenant_ids = [''.join(tenant) for tenant in tenants if tenant]

        	# cleanup and close files
        	files.close()

                query1 = query1.filter(model.name == "in-addr.arpa.")
		query2 = query2.filter(model.tenant_id.in_(tenant_ids))
		query3 = query3.filter(model.tenant_id == context.tenant_id)
                query = query1.union(query2,query3)
        return query

    # added or modified by M
    def _find_customr(self, model, context, criterion, one=False,
              marker=None, limit=None, sort_key=None, sort_dir=None):
        """
        Base "finder" method

        Used to abstract these details from all the _find_*() methods.
        """
        # First up, create a query and apply the various filters
        query = self.session.query(model)
        query = self._apply_criterion(model, query, criterion)
        query = self._apply_deleted_criteria(context, model, query)
        query = self._apply_fetch_record(context,model,query)
	
        if one:
            # If we're asked to return exactly one record, but multiple or
            # none match, raise a NotFound
            try:
                return query.one()
            except (exc.NoResultFound, exc.MultipleResultsFound):
                raise exceptions.NotFound()
        else:
            # If marker is not none and basestring we query it.
            # Otherwise, return all matching records
            if marker is not None:
                try:
                    marker = self._find(model, context, {'id': marker},
                                        one=True)
                except exceptions.NotFound:
                    raise exceptions.MarkerNotFound(
                        'Marker %s could not be found' % marker)
                # Malformed UUIDs return StatementError
                except sqlalchemy_exc.StatementError as statement_error:
                    raise exceptions.InvalidMarker(statement_error.message)
            sort_key = sort_key or 'created_at'
            sort_dir = sort_dir or 'asc'

            try:
                query = paginate_query(
                    query, model, limit,
                    [sort_key, 'id', 'created_at'], marker=marker,
                    sort_dir=sort_dir)

                return query.all()
            except InvalidSortKey as sort_key_error:
                raise exceptions.InvalidSortKey(sort_key_error.message)
            # Any ValueErrors are propagated back to the user as is.
            # Limits, sort_dir and sort_key are checked at the API layer.
            # If however central or storage is called directly, invalid values
            # show up as ValueError
            except ValueError as value_error:
                raise exceptions.ValueError(value_error.message)

    # added this method to avoid conflicts in other existing methods.
    # it will be used only for domain-list
    def _find_custom(self, model, context, criterion, one=False,
              marker=None, limit=None, sort_key=None, sort_dir=None):
        """
        Base "finder" method

        Used to abstract these details from all the _find_*() methods.
        """
        # First up, create a query and apply the various filters
        query = self.session.query(model)
        query1 = self.session.query(model)
        query2 = self.session.query(model)
	query3 = self.session.query(model)
        query = self._apply_criterion(model, query, criterion)
        query = self._apply_deleted_criteria(context, model, query)
        query = self._apply_fetch_inaddrarpa(context,model,query,query1,query2,query3)

        if one:
            # If we're asked to return exactly one record, but multiple or
            # none match, raise a NotFound
            try:
                return query.one()
            except (exc.NoResultFound, exc.MultipleResultsFound):
                raise exceptions.NotFound()
        else:
            # If marker is not none and basestring we query it.
            # Otherwise, return all matching records
            if marker is not None:
                try:
                    marker = self._find(model, context, {'id': marker},
                                        one=True)
                except exceptions.NotFound:
                    raise exceptions.MarkerNotFound(
                        'Marker %s could not be found' % marker)
                # Malformed UUIDs return StatementError
                except sqlalchemy_exc.StatementError as statement_error:
                    raise exceptions.InvalidMarker(statement_error.message)
            sort_key = sort_key or 'created_at'
            sort_dir = sort_dir or 'asc'

            try:
                query = paginate_query(
                    query, model, limit,
                    [sort_key, 'id', 'created_at'], marker=marker,
                    sort_dir=sort_dir)

                return query.all()
            except InvalidSortKey as sort_key_error:
                raise exceptions.InvalidSortKey(sort_key_error.message)
            # Any ValueErrors are propagated back to the user as is.
            # Limits, sort_dir and sort_key are checked at the API layer.
            # If however central or storage is called directly, invalid values
            # show up as ValueError
            except ValueError as value_error:
                raise exceptions.ValueError(value_error.message)


    def _find(self, model, context, criterion, one=False,
              marker=None, limit=None, sort_key=None, sort_dir=None):
        """
        Base "finder" method

        Used to abstract these details from all the _find_*() methods.
        """

        # First up, create a query and apply the various filters
        query = self.session.query(model)
        query = self._apply_criterion(model, query, criterion)
        query = self._apply_tenant_criteria(context, model, query)
        query = self._apply_deleted_criteria(context, model, query)

        if one:
            # If we're asked to return exactly one record, but multiple or
            # none match, raise a NotFound
            try:
                return query.one()
            except (exc.NoResultFound, exc.MultipleResultsFound):
                raise exceptions.NotFound()
        else:
            # If marker is not none and basestring we query it.
            # Otherwise, return all matching records
            if marker is not None:
                try:
                    marker = self._find(model, context, {'id': marker},
                                        one=True)
                except exceptions.NotFound:
                    raise exceptions.MarkerNotFound(
                        'Marker %s could not be found' % marker)
                # Malformed UUIDs return StatementError
                except sqlalchemy_exc.StatementError as statement_error:
                    raise exceptions.InvalidMarker(statement_error.message)
            sort_key = sort_key or 'created_at'
            sort_dir = sort_dir or 'asc'

            try:
                query = paginate_query(
                    query, model, limit,
                    [sort_key, 'id', 'created_at'], marker=marker,
                    sort_dir=sort_dir)

                return query.all()
            except InvalidSortKey as sort_key_error:
                raise exceptions.InvalidSortKey(sort_key_error.message)
            # Any ValueErrors are propagated back to the user as is.
            # Limits, sort_dir and sort_key are checked at the API layer.
            # If however central or storage is called directly, invalid values
            # show up as ValueError
            except ValueError as value_error:
                raise exceptions.ValueError(value_error.message)

    ## CRUD for our resources (quota, server, tsigkey, tenant, domain & record)
    ## R - get_*, find_*s
    ##
    ## Standard Arguments
    ## self      - python object for the class
    ## context   - a dictionary of details about the request (http etc),
    ##             provided by flask.
    ## criterion - dictionary of filters to be applied
    ##

    # Quota Methods
    def _find_quotas(self, context, criterion, one=False,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Quota, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.QuotaNotFound()

    def create_quota(self, context, values):
        quota = models.Quota()

        quota.update(values)

        try:
            quota.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateQuota()

        return dict(quota)

    def get_quota(self, context, quota_id):
        quota = self._find_quotas(context, {'id': quota_id}, one=True)

        return dict(quota)

    def find_quotas(self, context, criterion=None,
                    marker=None, limit=None, sort_key=None, sort_dir=None):
        quotas = self._find_quotas(context, criterion, marker=marker,
                                   limit=limit, sort_key=sort_key,
                                   sort_dir=sort_dir)

        return [dict(q) for q in quotas]

    def find_quota(self, context, criterion):
        quota = self._find_quotas(context, criterion, one=True)

        return dict(quota)

    def update_quota(self, context, quota_id, values):
        quota = self._find_quotas(context, {'id': quota_id}, one=True)

        quota.update(values)

        try:
            quota.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateQuota()

        return dict(quota)

    def delete_quota(self, context, quota_id):
        quota = self._find_quotas(context, {'id': quota_id}, one=True)

        quota.delete(self.session)

    # Server Methods
    def _find_servers(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Server, context, criterion, one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.ServerNotFound()

    def create_server(self, context, values):
        server = models.Server()

        server.update(values)

        try:
            server.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateServer()

        return dict(server)

    def find_servers(self, context, criterion=None,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        servers = self._find_servers(context, criterion, marker=marker,
                                     limit=limit, sort_key=sort_key,
                                     sort_dir=sort_dir)
        return [dict(s) for s in servers]

    def get_server(self, context, server_id):
        server = self._find_servers(context, {'id': server_id}, one=True)
        return dict(server)

    def update_server(self, context, server_id, values):
        server = self._find_servers(context, {'id': server_id}, one=True)

        server.update(values)

        try:
            server.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateServer()

        return dict(server)

    def delete_server(self, context, server_id):
        server = self._find_servers(context, {'id': server_id}, one=True)

        server.delete(self.session)

    # TLD Methods
    def _find_tlds(self, context, criterion, one=False,
                   marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Tld, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.TLDNotFound()

    def create_tld(self, context, values):
        tld = models.Tld()
        tld.update(values)

        try:
            tld.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateTLD()

        return dict(tld)

    def find_tlds(self, context, criterion=None,
                  marker=None, limit=None, sort_key=None, sort_dir=None):
        tlds = self._find_tlds(context, criterion, marker=marker, limit=limit,
                               sort_key=sort_key, sort_dir=sort_dir)
        return [dict(s) for s in tlds]

    def find_tld(self, context, criterion):
        tld = self._find_tlds(context, criterion, one=True)
        return dict(tld)

    def get_tld(self, context, tld_id):
        tld = self._find_tlds(context, {'id': tld_id}, one=True)
        return dict(tld)

    def update_tld(self, context, tld_id, values):
        tld = self._find_tlds(context, {'id': tld_id}, one=True)
        tld.update(values)

        try:
            tld.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateTLD()

        return dict(tld)

    def delete_tld(self, context, tld_id):
        tld = self._find_tlds(context, {'id': tld_id}, one=True)
        tld.delete(self.session)

    # TSIG Key Methods
    def _find_tsigkeys(self, context, criterion, one=False,
                       marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.TsigKey, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.TsigKeyNotFound()

    def create_tsigkey(self, context, values):
        tsigkey = models.TsigKey()

        tsigkey.update(values)

        try:
            tsigkey.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateTsigKey()

        return dict(tsigkey)

    def find_tsigkeys(self, context, criterion=None,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        tsigkeys = self._find_tsigkeys(context, criterion, marker=marker,
                                       limit=limit, sort_key=sort_key,
                                       sort_dir=sort_dir)

        return [dict(t) for t in tsigkeys]

    def get_tsigkey(self, context, tsigkey_id):
        tsigkey = self._find_tsigkeys(context, {'id': tsigkey_id}, one=True)

        return dict(tsigkey)

    def update_tsigkey(self, context, tsigkey_id, values):
        tsigkey = self._find_tsigkeys(context, {'id': tsigkey_id}, one=True)

        tsigkey.update(values)

        try:
            tsigkey.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateTsigKey()

        return dict(tsigkey)

    def delete_tsigkey(self, context, tsigkey_id):
        tsigkey = self._find_tsigkeys(context, {'id': tsigkey_id}, one=True)

        tsigkey.delete(self.session)

    ##
    ## Tenant Methods
    ##
    def find_tenants(self, context):
        # returns an array of tenant_id & count of their domains
        query = self.session.query(models.Domain.tenant_id,
                                   func.count(models.Domain.id))
        query = self._apply_tenant_criteria(context, models.Domain, query)
        query = self._apply_deleted_criteria(context, models.Domain, query)
        query = query.group_by(models.Domain.tenant_id)

        return [{'id': t[0], 'domain_count': t[1]} for t in query.all()]

    def get_tenant(self, context, tenant_id):
        # get list list & count of all domains owned by given tenant_id
        query = self.session.query(models.Domain.name)
        query = self._apply_tenant_criteria(context, models.Domain, query)
        query = self._apply_deleted_criteria(context, models.Domain, query)
        query = query.filter(models.Domain.tenant_id == tenant_id)

        result = query.all()

        return {
            'id': tenant_id,
            'domain_count': len(result),
            'domains': [r[0] for r in result]
        }

    def count_tenants(self, context):
        # tenants are the owner of domains, count the number of unique tenants
        # select count(distinct tenant_id) from domains
        query = self.session.query(distinct(models.Domain.tenant_id))
        query = self._apply_tenant_criteria(context, models.Domain, query)
        query = self._apply_deleted_criteria(context, models.Domain, query)

        return query.count()

    ##
    ## Domain Methods
    ##
    def _find_domains(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Domain, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.DomainNotFound()

    ##
    ## Domain Methods
    ## modified or added by M
    def _find_domains_for_record_custom(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find_customr(models.Domain, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.DomainNotFound()


    # added this method to avoid conflicts in other existing methods.
    # it will be used only for domain-list
    def _find_domains_custom(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find_custom(models.Domain, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.DomainNotFound()



    def create_domain(self, context, values):
        domain = models.Domain()

        domain.update(values)

        try:
            domain.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateDomain()

        return dict(domain)

    def get_domain(self, context, domain_id):
        domain = self._find_domains(context, {'id': domain_id}, one=True)

        return dict(domain)

    # modified or added by M
    def get_domain_ptr(self, context, domain_id):
        domain = self._find_domains_for_record_custom(context, {'id': domain_id}, one=True)

        return dict(domain)

    # modified or added by M
    def get_domain_facil(self, context, domain_id):
        domain = self._find_domains_for_record_custom(context, {'id': domain_id}, one=True)

        return dict(domain)


    def find_domains(self, context, criterion=None,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        domains = self._find_domains(context, criterion, marker=marker,
                                     limit=limit, sort_key=sort_key,
                                     sort_dir=sort_dir)

        return [dict(d) for d in domains]

    # new function added to avoid conflict and proper working
    def find_domains_custom(self, context, criterion=None,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        domains = self._find_domains_custom(context, criterion, marker=marker,
                                     limit=limit, sort_key=sort_key,
                                     sort_dir=sort_dir)

        return [dict(d) for d in domains]

    def find_domain(self, context, criterion):
        domain = self._find_domains(context, criterion, one=True)
        return dict(domain)

    def update_domain(self, context, domain_id, values):
        domain = self._find_domains(context, {'id': domain_id}, one=True)

        domain.update(values)

        try:
            domain.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateDomain()

        return dict(domain)

    def update_domain_ptr(self, context, domain_id, values):
        domain = self._find_domains_for_record_custom(context, {'id': domain_id}, one=True)

        domain.update(values)

        try:
            domain.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateDomain()

        return dict(domain)


    def delete_domain(self, context, domain_id):
        domain = self._find_domains(context, {'id': domain_id}, one=True)

        domain.soft_delete(self.session)

        return dict(domain)

    def count_domains(self, context, criterion=None):
        query = self.session.query(models.Domain)
        query = self._apply_criterion(models.Domain, query, criterion)
        query = self._apply_tenant_criteria(context, models.Domain, query)
        query = self._apply_deleted_criteria(context, models.Domain, query)

        return query.count()

    # Modified or added by M
    # RecordSet Methods
    def _find_recordsets(self, context, criterion, one=False,
                         marker=None, limit=None, sort_key=None,
                         sort_dir=None):
        try:
            return self._find(models.RecordSet, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.RecordSetNotFound()

    # Modified or added by M
    # RecordSet Methods
    def _find_recordsets_custom(self, context, criterion, one=False,
                         marker=None, limit=None, sort_key=None,
                         sort_dir=None):
        try:
            return self._find_customr(models.RecordSet, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.RecordSetNotFound()

    # Modified or added by M
    # RecordSet Methods
    def _find_recordsets_facil(self, context, criterion, one=False,
                         marker=None, limit=None, sort_key=None,
                         sort_dir=None):
        try:
            return self._find_customr(models.RecordSet, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.RecordSetNotFound()


    def create_recordset(self, context, domain_id, values):
        # Fetch the domain as we need the tenant_id
        domain = self._find_domains(context, {'id': domain_id}, one=True)

        recordset = models.RecordSet()

        recordset.update(values)
        recordset.tenant_id = domain['tenant_id']
        recordset.domain_id = domain_id

        try:
            recordset.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecordSet()

        return dict(recordset)

    # modified or added by M
    def create_recordset_ptr(self, context, domain_id, values):
        # Fetch the domain as we need the tenant_id
        domain = self._find_domains_for_record_custom(context, {'id': domain_id}, one=True)

        recordset = models.RecordSet()

        recordset.update(values)
        recordset.tenant_id = domain['tenant_id']
        recordset.domain_id = domain_id

        try:
            recordset.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecordSet()

        return dict(recordset)


    def get_recordset(self, context, recordset_id):
        recordset = self._find_recordsets(context, {'id': recordset_id},
                                          one=True)

        return dict(recordset)

    # modified or added by M
    def get_recordset_custom(self, context, recordset_id):
        recordset = self._find_recordsets_custom(context, {'id': recordset_id},
                                          one=True)

        return dict(recordset)


    def find_recordsets(self, context, criterion=None,
                        marker=None, limit=None, sort_key=None, sort_dir=None):
        recordsets = self._find_recordsets(
            context, criterion, marker=marker, limit=limit, sort_key=sort_key,
            sort_dir=sort_dir)

        return [dict(r) for r in recordsets]

    def find_recordsets_facil(self, context, criterion=None,
                        marker=None, limit=None, sort_key=None, sort_dir=None):
        recordsets = self._find_recordsets_facil(
            context, criterion, marker=marker, limit=limit, sort_key=sort_key,
            sort_dir=sort_dir)

        return [dict(r) for r in recordsets]


    def find_recordset(self, context, criterion):
        recordset = self._find_recordsets(context, criterion, one=True)

        return dict(recordset)

    def update_recordset(self, context, recordset_id, values):
        recordset = self._find_recordsets(context, {'id': recordset_id},
                                          one=True)

        recordset.update(values)

        try:
            recordset.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecordSet()

        return dict(recordset)

    def delete_recordset(self, context, recordset_id):
        recordset = self._find_recordsets(context, {'id': recordset_id},
                                          one=True)

        recordset.delete(self.session)

        return dict(recordset)

    def count_recordsets(self, context, criterion=None):
        query = self.session.query(models.RecordSet)
        query = self._apply_criterion(models.RecordSet, query, criterion)

        return query.count()

    # Record Methods
    def _find_records(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Record, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.RecordNotFound()

    def _find_records_facil(self, context, criterion, one=False,
                      marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find_customr(models.Record, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.RecordNotFound()


    def create_record(self, context, domain_id, recordset_id, values):
        # Fetch the domain as we need the tenant_id
        domain = self._find_domains(context, {'id': domain_id}, one=True)

        record = models.Record()

        # Create and populate the new Record model
        record = models.Record()
        record.update(values)
        record.tenant_id = domain['tenant_id']
        record.domain_id = domain_id
        record.recordset_id = recordset_id

        try:
            # Save the new Record model
            record.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecord()

        return dict(record)

    def create_record_ptr(self, context, domain_id, recordset_id, values):
        # Fetch the domain as we need the tenant_id
        domain = self._find_domains_for_record_custom(context, {'id': domain_id}, one=True)

        record = models.Record()

        # Create and populate the new Record model
        record = models.Record()
        record.update(values)
        record.tenant_id = domain['tenant_id']
        record.domain_id = domain_id
        record.recordset_id = recordset_id

        try:
            # Save the new Record model
            record.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecord()

        return dict(record)

    def find_records(self, context, criterion=None,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        records = self._find_records(
            context, criterion, marker=marker, limit=limit, sort_key=sort_key,
            sort_dir=sort_dir)

        return [dict(r) for r in records]

    def find_records_facil(self, context, criterion=None,
                     marker=None, limit=None, sort_key=None, sort_dir=None):
        records = self._find_records_facil(
            context, criterion, marker=marker, limit=limit, sort_key=sort_key,
            sort_dir=sort_dir)

        return [dict(r) for r in records]



    def get_record(self, context, record_id):
        record = self._find_records(context, {'id': record_id}, one=True)

        return dict(record)

    def find_record(self, context, criterion):
        record = self._find_records(context, criterion, one=True)

        return dict(record)

    def update_record(self, context, record_id, values):
        record = self._find_records(context, {'id': record_id}, one=True)

        record.update(values)

        try:
            record.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateRecord()

        return dict(record)

    def delete_record(self, context, record_id):
        record = self._find_records(context, {'id': record_id}, one=True)

        record.delete(self.session)

        return dict(record)

    def count_records(self, context, criterion=None):
        query = self.session.query(models.Record)
        query = self._apply_tenant_criteria(context, models.Record, query)
        query = self._apply_criterion(models.Record, query, criterion)
        return query.count()

    #
    # Blacklist Methods
    #
    def _find_blacklist(self, context, criterion, one=False,
                        marker=None, limit=None, sort_key=None, sort_dir=None):
        try:
            return self._find(models.Blacklists, context, criterion, one=one,
                              marker=marker, limit=limit, sort_key=sort_key,
                              sort_dir=sort_dir)
        except exceptions.NotFound:
            raise exceptions.BlacklistNotFound()

    def create_blacklist(self, context, values):
        blacklist = models.Blacklists()

        blacklist.update(values)

        try:
            blacklist.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateBlacklist()

        return dict(blacklist)

    def find_blacklists(self, context, criterion=None,
                        marker=None, limit=None, sort_key=None, sort_dir=None):
        blacklists = self._find_blacklist(
            context, criterion, marker=marker, limit=limit, sort_key=sort_key,
            sort_dir=sort_dir)

        return [dict(b) for b in blacklists]

    def get_blacklist(self, context, blacklist_id):
        blacklist = self._find_blacklist(context,
                                         {'id': blacklist_id}, one=True)

        return dict(blacklist)

    def find_blacklist(self, context, criterion):
        blacklist = self._find_blacklist(context, criterion, one=True)

        return dict(blacklist)

    def update_blacklist(self, context, blacklist_id, values):
        blacklist = self._find_blacklist(context, {'id': blacklist_id},
                                         one=True)

        blacklist.update(values)

        try:
            blacklist.save(self.session)
        except exceptions.Duplicate:
            raise exceptions.DuplicateBlacklist()

        return dict(blacklist)

    def delete_blacklist(self, context, blacklist_id):

        blacklist = self._find_blacklist(context, {'id': blacklist_id},
                                         one=True)

        blacklist.delete(self.session)

    # diagnostics
    def ping(self, context):
        start_time = time.time()

        try:
            result = self.engine.execute('SELECT 1').first()
        except Exception:
            status = False
        else:
            status = True if result[0] == 1 else False

        return {
            'status': status,
            'rtt': "%f" % (time.time() - start_time)
        }
