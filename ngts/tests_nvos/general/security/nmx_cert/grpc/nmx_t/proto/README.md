# NMX-T gRPC Testing - NVOS Verification

Here we have basic NVOS -> NMX-T e2e testing - from nv CLI to manager communication (external port) with nmx-t using gRPC Hello request.

nmx-t protocol defined in .proto file at:
https://gitlab-master.nvidia.com/telemetry/nmx-telemetry-connector/blob/main/proto/nmx-telemetry.proto

Extracted definitions that are relevant to HelloRequest of TelemetryService service (removed all other non-relevant definitions).


## For update/change in the .proto :

\* preferred to save a copy of the existing files, in case of something broken after change.

1. compile the updated .proto file into python usable code - run the following (can be done in activated venv):
```
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. nmx-telemetry.proto
```
2. in the generated _pb2_grpc.py file, fix the import of the _pb2.py file to use absolute path (so it would work in tests too).

## Notes

* if something is not working, can check actual .proto used by nmx-t in the switch, at: /usr/share/cluster_pkgs/nmx-telemetry/proto/nmx-telemetry.proto
* for debug, can tail log using: tail -f /var/log/nmx-c/gwapi.log | grep -v "GFM SDK Library is not initialized. Skipping request"
* to verify that the server actually opened SSL/TLS port, try:
```
openssl s_client -connect <ip>:<port> -tls1_2
# or version 1_3
openssl s_client -connect <ip>:<port> -tls1_3

# "error:0A0000BF:SSL routines:tls_setup_handshake:no protocols available" - tried tls version is not supported for sure
# "error:0A00010B:SSL routines:ssl3_get_record:wrong version number" - suggests that the port was not opened in SSL/TLS mode
```
* 

