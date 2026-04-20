class GrpcTunnelConstants:
    """NVUE keys and docker names for gRPC tunnel tests."""

    DOCKER_NV_UMF = "nv-umf"
    DOCKER_NV_GNMI = "nv-gnmi"
    # Per HLD: one ``nv-grpctunnel-<server>`` instance per configured tunnel server.
    GRPC_TUNNEL_DOCKER_PREFIX = "nv-grpctunnel-"

    STATE = "state"
    RETRY_INTERVAL = "retry-interval"
    TARGET_TYPE = "target-type"
    TARGET_NAME = "target-name"
    ADDRESS = "address"
    PORT = "port"
    CONNECTION = "connection"
    SUBSCRIPTION_THRESHOLD = 10
    STRESS_TUNNEL_SETTLE_WAIT_SEC = 40
