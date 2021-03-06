# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Author: Endre Karlson <endre.karlson@hp.com>
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

import datetime

from oslo_log import log as logging
from oslo_utils import timeutils

from designate.zone_manager import tasks
from designate.tests import TestCase
from designate.storage.impl_sqlalchemy import tables
from designate.tests import fixtures

LOG = logging.getLogger(__name__)


class TaskTest(TestCase):
    def setUp(self):
        super(TaskTest, self).setUp()

    def _enable_tasks(self, tasks):
        self.config(
            enabled_tasks=tasks,
            group="service:zone_manager")


class DeletedDomainPurgeTest(TaskTest):
    def setUp(self):
        super(DeletedDomainPurgeTest, self).setUp()

        self.config(
            interval=3600,
            time_threshold=604800,
            batch_size=100,
            group="zone_manager_task:domain_purge"
        )

        self.purge_task_fixture = self.useFixture(
            fixtures.ZoneManagerTaskFixture(tasks.DeletedDomainPurgeTask)
        )

    def _create_deleted_zone(self, name, mock_deletion_time):
        # Create a domain and set it as deleted
        domain = self.create_domain(name=name)
        self._delete_domain(domain, mock_deletion_time)
        return domain

    def _fetch_all_domains(self):
        """Fetch all domains including deleted ones
        """
        query = tables.domains.select()
        return self.central_service.storage.session.execute(query).fetchall()

    def _delete_domain(self, domain, mock_deletion_time):
        # Set a domain as deleted
        zid = domain.id.replace('-', '')
        query = tables.domains.update().\
            where(tables.domains.c.id == zid).\
            values(
                action='NONE',
                deleted=zid,
                deleted_at=mock_deletion_time,
                status='DELETED',
        )

        pxy = self.central_service.storage.session.execute(query)
        self.assertEqual(pxy.rowcount, 1)
        return domain

    def _create_deleted_zones(self):
        # Create a number of deleted zones in the past days
        zones = []
        now = timeutils.utcnow()
        for age in range(18):
            age *= (24 * 60 * 60)  # seconds
            delta = datetime.timedelta(seconds=age)
            deletion_time = now - delta
            name = "example%d.org." % len(zones)
            z = self._create_deleted_zone(name, deletion_time)
            zones.append(z)

        return zones

    def test_purge_zones(self):
        """Create 18 zones, run zone_manager, check if 7 zones are remaining
        """
        self.config(quota_domains=1000)
        self._create_deleted_zones()

        self.purge_task_fixture.task()

        zones = self._fetch_all_domains()
        LOG.info("Number of zones: %d", len(zones))
        self.assertEqual(len(zones), 7)
