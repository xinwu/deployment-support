import constants as const

class MembershipRule(object):
    def __init__(self, br_key, br_vlan, tenant):
        # br_key will be used as segment name and ivs internal port name
        prefixes = br_key.split('/')
        self.br_key    = prefixes[len(prefixes)-1]
        self.br_vlan   = br_vlan
        self.tenant    = tenant

    def __str__(self): 
        return (r'''{br_key : %(br_key)s, br_vlan : %(br_vlan)s}''' %
               {'br_key' : self.br_key, 'br_vlan' : self.br_vlan})

    def __repr__(self):
        return self.__str__()


