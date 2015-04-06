import constants as const

class MembershipRule(object):
    def __init__(self, br_key, br_vlan, interface=const.ANY, tenant=const.OS_MGMT_TENANT):
        # br_key will be used as segment name
        self.br_key    = br_key
        self.interface = interface
        self.br_vlan   = br_vlan
        self.tenant    = tenant

    def __str__(self): 
        return (r'''{br_key : %(br_key)s, interface : %(interface)s, br_vlan : %(br_vlan)s}''' %
               {'br_key' : self.br_key, 'interface' : self.interface,
                'br_vlan' : self.br_vlan})

    def __repr__(self):
        return self.__str__()


