import constants as const

class MembershipRule(object):
    def __init__(self, br_key, br_name, br_vlan, tenant=const.OS_MGMT_TENANT):
        self.br_key  = br_key
        self.br_name = br_name
        self.br_vlan = br_vlan
        self.tenant  = tenant

    def __str__(self): 
        return (r'''{br_key : %(br_key)s, br_name : %(br_name)s, br_vlan : %(br_vlan)s}''' %
               {'br_key' : self.br_key, 'br_name' : self.br_name,
                'br_vlan' : self.br_vlan})

    def __repr__(self):
        return self.__str__()


