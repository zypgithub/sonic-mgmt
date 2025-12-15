class MappingFields:
    external_path = "externalPath"
    internal_path = "internalPath"
    external_data_model = "externalDataModel"
    external_data_type = "externalDataType"
    internal_data_type = "internalDataType"
    key_mappings = "keyMappings"
    key_mapping_internal = "internal"
    key_mapping_default = "default"
    key_mapping_key_is_value = "keyIsValue"
    key_mapping_external_match = "externalMatch"
    key_mapping_external = "external"
    key_mapping_value = "value"


# Paths and credentials used for GNMI vs STATE_DB mapping validation
MAPPINGS_FILE_PATH = "/etc/nv-gnmi/mapping/nvos-mappings-common.yaml"
GNMI_PORT = 9339
GNMI_USERNAME = "admin"
GNMI_PASSWORD = "admin"
