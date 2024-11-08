import ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_t.proto.nmx_telemetry_pb2 as pb
import ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_t.proto.nmx_telemetry_pb2_grpc as pb_grpc
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import GrpcConfig
from ngts.tests_nvos.general.security.nmx_cert.grpc.utils.logs import standalone_logger


class TelemetryServiceServicer(pb_grpc.TelemetryServiceServicer):
    def __init__(self, name: str, config: GrpcConfig, logger=standalone_logger):
        self.name = name
        self.config = config
        self.counter = 0
        self.logger = logger

    def Hello(self, request, context):
        self.counter += 1

        self._log(f'received Hello() request #{self.counter} from {context.peer()}')

        return pb.ServerHello(
            serverHeader=pb.ServerHeader(
                domain_uuid=f"Hello World! {self.counter}",
                app_uuid=f"Hello World! {self.counter}",
                app_ver=f"Hello World! {self.counter}",
                returnCode=pb.ST_ReturnCode.ST_SUCCESS
            ),
            components_ver=[],
            capabilities=[],
            host_os_details=f"Hello World! {self.counter}",
            major_version=pb.ProtoMsgMajorVersion.PROTO_MSG_MAJOR_VERSION,
            minor_version=pb.ProtoMsgMinorVersion.PROTO_MSG_MINOR_VERSION
        )

    def _log(self, msg: str):
        self.logger.info(f'[{self.name}] {msg}')
