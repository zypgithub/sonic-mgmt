#!/usr/bin/bash

for i in {0..504..8};do config int start Ethernet$i;done
#interface mac
for i in {0..504..8}; do 
    redis-cli -n 4 hmset "INTERFACE|Ethernet$i" "mac_addr" "00:00:00:00:00:01"
done

######FORWARD###############
# IP addr
for i in {256..504..8};do
    config interface ip add Ethernet$i $(($i/8 + 1)).0.0.1/24
done

#static-arp
for i in {256..504..8}; do
    arp -s $(($i/8 + 1)).0.0.2 00:00:00:00:00:02
done

#static-route
for i in {256..504..8}; do    
    config route add prefix 100.100.100.101/32 nexthop $(($i/8 + 1)).0.0.2
done

##########BACKWARD#################
# IP addr
for i in {0..248..8};do
    config interface ip add Ethernet$i $(($i/8 + 1)).0.0.1/24
done

#static-arp
for i in {0..248..8}; do 
    arp -s $(($i/8 + 1)).0.0.2 00:00:00:00:00:03
done

#route
for i in {0..248..8}; do 
    config route add prefix 100.100.100.102/32 nexthop $(($i/8 + 1)).0.0.2
done
