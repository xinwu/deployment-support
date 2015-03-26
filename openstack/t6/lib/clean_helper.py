import os
import constants as const
from helper import Helper
from ospurge.ospurge import Session
from ospurge.ospurge import Resources
from ospurge.ospurge import NeutronResources
from ospurge.ospurge import NeutronRouters
from ospurge.ospurge import NeutronInterfaces
from ospurge.ospurge import NeutronNetworks
from ospurge.ospurge import NeutronPorts
from ospurge.ospurge import NeutronSecgroups
from ospurge.ospurge import NeutronFloatingIps
from neutronclient.neutron import client as neutron_client
from keystoneclient.v2_0 import client as keystone_client


class CleanHelper(object):
    def __init__(self):
        self.OS_AUTH_URL    = os.environ['OS_AUTH_URL']
        self.OS_TENANT_ID   = os.environ['OS_TENANT_ID']
        self.OS_TENANT_NAME = os.environ['OS_TENANT_NAME']
        self.OS_USERNAME    = os.environ['OS_USERNAME']
        self.OS_PASSWORD    = os.environ['OS_PASSWORD']
        self.OS_REGION_NAME = os.environ['OS_REGION_NAME']
        self.neutron_client = neutron_client.Client(const.CLIENT_VERSION,
            auth_url=self.OS_AUTH_URL,
            username=self.OS_USERNAME,
            password=self.OS_PASSWORD,
            tenant_name=self.OS_TENANT_NAME)
        self.keystone_client = keystone_client.Client(auth_url=self.OS_AUTH_URL,
            username=self.OS_USERNAME,
            password=self.OS_PASSWORD,
            tenant_name=self.OS_TENANT_NAME)


    def delete_ovs_agents(self):
        if const.ADMIN != self.OS_USERNAME:
            Helper.safe_print('admin openrc file is required to delete ovs agent\n')
            return
        agents = self.neutron_client.list_agents()['agents']
        for agent in agents:
            if 'binary' not in agent:
                continue
            if const.OVS_AGENT == agent['binary']:
               ovs_agent_uuid = agent['id']
               self.neutron_client.delete_agent(ovs_agent_uuid)


    def __delete_project_neutron_resources__(self, project_uuid):
        session = Session(self.OS_USERNAME,
            self.OS_PASSWORD,
            project_uuid,
            self.OS_AUTH_URL,
            const.ENDPOINT_TYPE,
            self.OS_REGION_NAME,
            False)
        for cls in const.NEUTRON_RESOURCE_CLASSES:
            resource = globals()[cls](session)
            resource.purge()


    def delete_non_bcf_projects_neutron_resources(self):
        if const.ADMIN != self.OS_USERNAME:
            Helper.safe_print('admin openrc file is required to delete project resource\n')
            return
        project_uuids = [
            tenant.id for tenant in self.keystone_client.tenants.list()
            if const.SERVICES != tenant.name]
        for project_uuid in project_uuids:
            self.__delete_project_neutron_resources__(project_uuid)




