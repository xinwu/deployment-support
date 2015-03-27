
from lib.clean_helper import CleanHelper

if __name__=='__main__':
    cleaner = CleanHelper()
    cleaner.delete_ovs_agents()
    cleaner.delete_non_bcf_projects_neutron_resources()
