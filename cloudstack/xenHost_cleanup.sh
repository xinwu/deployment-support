#!/bin/bash

# This is the script to clean up the XenHost so that it can be added to a new CS instance.

for vm in `xe vm-list | grep name-label | grep -v Control | awk '{print $4}'`; do uuid=`xe vm-list name-label=$vm | grep uuid | awk '{print$5}'`; echo $uuid; xe vm-shutdown --force uuid=$uuid; xe vm-destroy uuid=$uuid; done

for vlan in `xe vlan-list | grep uuid | awk '{print $5}'`; do pif=`xe pif-list VLAN=$vlan | grep ^uuid | awk '{print $5}'`; xe pif-unplug uuid=$pif;  xe vlan-destroy uuid=$vlan; done

for vlan in `xe network-list | grep name-label | grep VLAN| awk '{print $4}'`; do echo $vlan; uuid=`xe network-list name-label=$vlan | grep uuid | awk '{print $5}'`; xe network-destroy uuid=$uuid; done

for sr in `xe sr-list type=nfs name-description=storage | grep uuid | awk '{print $5}'`; do pbd=`xe pbd-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; echo $pbd; xe pbd-unplug uuid=$pbd; xe pbd-destroy uuid=$pbd; xe sr-forget uuid=$sr; done

for sr in `xe sr-list type=iso name-description=iso | grep uuid | awk '{print $5}'`; do echo $sr; for vdi in `xe vdi-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $vdi; xe vdi-destroy uuid=$vdi; done; for pbd in `xe pbd-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $pbd; xe pbd-unplug uuid=$pbd; xe pbd-destroy uuid=$pbd; done; done

xentoolsiso=$(xe sr-list name-label='XenServer Tools' | grep uuid | awk '{print $5}'); for sr in `xe sr-list type=iso content-type=iso | grep uuid | awk '{print $5}' | grep -v $xentoolsiso `; do echo $sr; for vdi in `xe vdi-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $vdi; xe vdi-destroy uuid=$vdi; done; for pbd in `xe pbd-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $pbd; xe pbd-unplug uuid=$pbd; xe pbd-destroy uuid=$pbd; done;  done

for sr in `xe sr-list type=nfs | grep uuid | awk '{print $5}'`; do echo $sr;  for pbd in `xe pbd-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $pbd; xe pbd-unplug uuid=$pbd; xe pbd-destroy uuid=$pbd; done; xe sr-forget uuid=$sr; done

for sr in `xe sr-list type=lvmoiscsi | grep uuid | awk '{print $5}'`; do echo $sr; for vdi in `xe vdi-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $vdi; xe vdi-destroy uuid=$vdi; done; for pbd in `xe pbd-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $pbd; xe pbd-unplug uuid=$pbd; xe pbd-destroy uuid=$pbd; done; xe sr-forget uuid=$sr; done

for sr in `xe sr-list type=lvm | grep uuid | awk '{print $5}'`; do echo $sr; for vdi in `xe vdi-list sr-uuid=$sr | grep ^uuid | awk '{ print $5}'` ; do echo $vdi; xe vdi-destroy uuid=$vdi; done; done

for mount in `mount | grep '/var/run/sr-mount' | awk '{print $3}'`; do echo $mount; umount $mount; done
