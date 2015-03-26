import os
import constants as const
from helper import Helper
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
        pass

    def delete_project_resource(self, project_uuid):
        pass
