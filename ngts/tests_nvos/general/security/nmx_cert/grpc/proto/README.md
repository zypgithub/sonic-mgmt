# NMX-C gRPC Testing - NVOS Verification

Here we have NVOS -> NMX e2e testing - from nv CLI to manager communication (external port) with nmx-c using gRPC HelloRequest.

nmx-c protocol defined in .proto file at:
https://gitlab-master.nvidia.com/nmx-c-common/nmx-c-proto

Extracted definitions that are relevant to HelloRequest of NMX_Controller service (removed all other non-relevant definitions).


## For update/change in the .proto :

\* preferred to save a copy of the existing files, in case of something broken after change.

1. compile the updated .proto file into python usable code - run the following (can be done in activated venv):
```
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. nmx-m-nmx-c.proto
```
2. in the generated _pb2_grpc.py file, fix the import of the _pb2.py file to use absolute path (so it would work in tests too).

## Notes

* if something is not working, can check actual .proto used by nmx-c in the switch, at: /usr/share/cluster_pkgs/nmx-controller/nmx-m-nmx-c.proto
* for debug, can tail log using: tail -f /var/log/nmx-c/gwapi.log | grep -v "GFM SDK Library is not initialized. Skipping request"

