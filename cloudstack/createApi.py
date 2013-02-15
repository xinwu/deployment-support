#!/usr/bin/env python

#
# Update the server, apiKey, and secretKey for the target CS deployment
#
# This script computes the command signature and outputs the full command
# for CS API query.
#
# Example
# > ./createApi.py 'command=listPhysicalNetworks'
# > 'http://10.192.20.210:8080/client/api?apiKey=g7tK4aIv-h7vQvgV6BPwURjlhKfKfce1_ZijQbSDvGu6i9JIkoxR6zQYsCk1sNaJotKJLe7O2eTW0DWvc8FFiw&command=listPhysicalNetworks&response=json&signature=%2BOrXpK7YozE69kFIYVXEW%2F%2FkHmk%3D'
#
# Then, user can use the output for curl query
# curl 'http://10.192.20.210:8080/client/api?apiKey=g7tK4aIv-h7vQvgV6BPwURjlhKfKfce1_ZijQbSDvGu6i9JIkoxR6zQYsCk1sNaJotKJLe7O2eTW0DWvc8FFiw&command=listPhysicalNetworks&response=json&signature=%2BOrXpK7YozE69kFIYVXEW%2F%2FkHmk%3D' | python -mjson.tool
# 
# Output:
#
# {
#    "listphysicalnetworksresponse": {
#        "count": 1, 
#        "physicalnetwork": [
#            {
#                "broadcastdomainrange": "ZONE", 
#                "id": "51f99092-520f-4256-90fd-59c748a17e25", 
#                "isolationmethods": "VNS", 
#                "name": "Physical Network 1", 
#                "state": "Enabled", 
#                "vlan": "100-150", 
#                "zoneid": "09cd24a1-9ce9-4829-9869-20d20766e0c0"
#            }
#        ]
#    }
# }

from hashlib import sha1
import hmac, base64, sys, urllib

server = '10.192.20.210:8080'
apiKey = 'g7tK4aIv-h7vQvgV6BPwURjlhKfKfce1_ZijQbSDvGu6i9JIkoxR6zQYsCk1sNaJotKJLe7O2eTW0DWvc8FFiw'
secretKey = 'ZnJ_zulSRWi3Bu-yO9jmzNfsADu3-Uvef7yRw-z18rOeb4zZ6I0EH7o_JGosQ75rzWTwSFOw0QGksN47RLsjKw'
formatType = 'json'

def parse_sort_cmd(apiCmd):
    apiCmd_low = apiCmd.lower()
    cmds = apiCmd_low.split('&')
    parsedCmds = dict()
    parsedCmds['apikey'] = apiKey.lower()
    parsedCmds['response'] = formatType.lower()
    retCmd = ""

    if not cmds or len(cmds)==0:
        return None

    for cmd in cmds:
        key, value = cmd.split('=')
        if key != None and value != None:
            parsedCmds[key] = value

    for key in sorted(parsedCmds.iterkeys()):
        if retCmd == '':
            retCmd = "%s=%s"%(key, parsedCmds[key])
        else: 
            retCmd = "%s&%s=%s"%(retCmd, key, parsedCmds[key])

    return retCmd

def sign_request(command):
    print 'un-encrypted cmd: %s' % command
    hashed = hmac.new(secretKey, msg=command, digestmod=sha1)

    # The signature
    signature = base64.b64encode(hashed.digest())
    retStr = "signature=%s" % (urllib.quote_plus(signature))
    return retStr

def main(args):
    if  len(args) != 1:
        print("command is required.")
        exit()

    command = args[0]
    sortedCmd = parse_sort_cmd(command)
    
    signedCmd = sign_request(sortedCmd).replace('+', '%20')
    if signedCmd[-1] == '=':
        signedCmd = "%s%%3D" %(signedCmd[:-1])
    signedCmd = "http://%s/client/api?apiKey=%s&%s&response=%s&%s" % \
                (server, apiKey, command, formatType, signedCmd)
    print "signed command: \'%s\'" % signedCmd
 
if  __name__ =='__main__':
    main(sys.argv[1:])
