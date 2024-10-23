from dash_api.eni_pb2 import State
from dash_api.route_type_pb2 import ActionType, EncapType, RoutingType

APPLIANCE_CONFIG = {
    "DASH_APPLIANCE_TABLE:123": {
        "sip": "10.2.0.1",
        "vm_vni": "4321"
    }
}

VNET1_CONFIG = {
        "DASH_VNET_TABLE:Vnet1": {
                "vni": "1000",
                "guid": "559c6ce8-26ab-4193-b946-ccc6e8f930b2"
        }
}

VNET2_CONFIG = {
        "DASH_VNET_TABLE:Vnet2": {
                "vni": "2000",
                "guid": "659c6ce8-26ab-4193-b946-ccc6e8f930b2"
        }
}


VNET_MAPPING_CONFIG = {
    f"DASH_VNET_MAPPING_TABLE:Vnet2:20.2.2.2": {
        "mac_address": "F9:22:83:99:22:A2",
        "routing_type": RoutingType.ROUTING_TYPE_PRIVATELINK,
        "underlay_ip": "10.0.2.2",
        "overlay_sip_prefix": "fd41:108:20:abc:abc::0/ffff:ffff:ffff:ffff:ffff:ffff::",
        "overlay_dip_prefix": "2603:10e1:100:2::3401:203/ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",
    }
}

QOS_CONFIG = {
        "DASH_QOS_TABLE:qos100": {
                "qos_id": "100",
                "bw": "10000",
                "cps": "1000",
                "flows": "10"
        }
}

ENI_CONFIG = {
        "DASH_ENI_TABLE:F4939FEFC47E": {
                "eni_id": "497f23d7-f0ac-4c99-a98f-59b470e8c7bd",
                "mac_address": "F4:93:9F:EF:C4:7E",
                "underlay_ip": "10.0.0.33",
                "admin_state": State.STATE_ENABLED,
                "vnet": "Vnet1",
                "qos": "qos100"
        }
}

ROUTE_VNET2_CONFIG = {
        "DASH_ROUTE_TABLE:RouteGroup:20.2.2.0/24": {
                "action_type": RoutingType.ROUTING_TYPE_VNET,
                "vnet": "Vnet2"
        }
}

ROUTE_GROUP_CONFIG = {
        "DASH_ROUTE_GROUP_TABLE:RouteGroup": {
                "guid": "48af6ce8-26cc-4293-bfa6-0126e8fcdeb2",
                "version": "rg_version"
        }
}

ROUTE_RULE_CONFIG = {
        "DASH_ROUTE_RULE_TABLE:F4939FEFC47E:2000:10.0.2.0/24": {
                "action_type": ActionType.ACTION_TYPE_DECAP,
                "priority": "1",
                "pa_validation": True,
                "vnet": "Vnet2"
        }
}

ROUTING_TYPE_CONFIG = {
    f"DASH_ROUTING_TYPE_TABLE:privatelink": {
        "items": [
            {
                "action_name": "action1",
                "action_type": ActionType.ACTION_TYPE_MAPROUTING
            }
        ]
    }
}
