#!/usr/bin/bash


######FORWARD###############
#interface mac
for i in {256..504..8}; do 
    redis-cli -n 4 hmset "INTERFACE|Ethernet$i" "mac_addr" "00:00:00:00:00:01"
done

# IP addr
for i in {256..504..8};do
    config interface ip add Ethernet$i $(($i/8 + 1)).0.0.1/24
done

#static-arp
for i in {256..508..8}; do 
    # echo "arp -s $(($i/8 + 1)).0.0.2 00:00:00:00:00:03" 
    arp -s $(($i/8 + 1)).0.0.2 00:00:00:00:00:02
done

#static-route
for i in {256..508..8}; do 
    # echo "config route add prefix 200.0.0.1/32 nexthop $(($i/8 + 1)).0.0.2"
    # config route add prefix 202.0.0.0/8 nexthop $(($i/8 + 1)).0.0.2
    config route add prefix 100.100.100.101/32 nexthop $(($i/8 + 1)).0.0.2
done

##########BACKWARD#################

#interface mac
for i in {0..252..4}; do 
    redis-cli -n 4 hmset "INTERFACE|Ethernet$i" "mac_addr" "00:00:00:00:00:01"
done

# IP addr
for i in {0..252..4};do
    # config interface ip remove Ethernet$i $(($i/4 + 100)).0.0.1/24
    config interface ip add Ethernet$i $(($i/4 + 128)).0.0.1/24
done

#static-arp
for i in {0..252..4}; do 
    # echo "arp -s $(($i/4 + 100)).0.0.2 00:00:00:00:00:03"
    arp -s $(($i/4 + 128)).0.0.2 00:00:00:00:00:03
done

#route
for i in {0..252..4}; do 
    # echo "config route add prefix 100.0.0.1/32 nexthop $(($i/8 + 1)).0.0.2"
    # config route add prefix 201.0.0.0/8 nexthop $(($i/8 + 1)).0.0.2
    config route add prefix 100.100.100.102/32 nexthop $(($i/4 + 128)).0.0.2
done

