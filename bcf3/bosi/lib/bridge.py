class Bridge(object):
    def __init__(self, br_key, br_name, br_ip, br_vlan):
        self.br_key  = br_key
        self.br_name = br_name
        self.br_ip   = br_ip
        self.br_vlan = br_vlan

    def __str__(self):
        return (r'''{br_key : %(br_key)s, br_name : %(br_name)s, br_ip : %(br_ip)s, br_vlan : %(br_vlan)s}''' %
               {'br_key' : self.br_key, 'br_name' : self.br_name,
                'br_ip' : self.br_ip, 'br_vlan' : self.br_vlan})

    def __repr__(self):
        return self.__str__()
