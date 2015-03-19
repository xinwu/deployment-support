class Node(object): 
    def __init__(self, node_config):
        self.hostname = get_raw_value(node_config, 'hostname')
        self.user     = get_raw_value(node_config, 'user')
        self.passwd   = get_raw_value(node_config, 'passwd')
        self.log      = 'var/log/bcf-deployment.log'
