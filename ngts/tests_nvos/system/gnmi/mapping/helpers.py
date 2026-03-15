import os
import random
from typing import Dict, Iterable, List, Optional, Union
from ngts.tools.test_utils import allure_utils as allure
import yaml
from .constants import MappingFields
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode
from ngts.nvos_constants.constants_nvos import DatabaseConst
from typing import Any, Optional, Union

Converted = Union[int, float, str, bool]


def compare_event_db_mappings(event_db_mapping_dict: Dict[str, dict], client: Optional[GnmiClient] = None, event_ids: Optional[Iterable[Union[int, str]]] = None, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, dict]:
    """
    pick 3 random event ids, for each of them, for each EVENT_DB external path:
      - Build the external GNMI path by replacing [event-id] with the concrete id
      - Run gnmic once and parse the value
      - Fetch the EVENT_DB value for the same id and field
      - Return results grouped by event-id and externalPath
    """
    results: Dict[str, dict] = {}
    with allure.step("Get 3 random event ids"):
        ids = [str(i) for i in event_ids] if event_ids else _get_event_ids()
        if not ids:
            return results
        ids = random.sample(ids, min(3, len(ids)))

    for event_id in ids:
        results[event_id] = {}
        with allure.independent_step(f"Testing event {event_id}"):
            for external_path_pattern, mapping_item in event_db_mapping_dict.items():
                with allure.independent_step(f"Testing {external_path_pattern}"):
                    if not isinstance(mapping_item, dict):
                        continue
                    if not external_path_pattern:
                        continue
                    internal_path = mapping_item.get(MappingFields.internal_path, "")
                    parts = parse_internal_path(internal_path)
                    if not parts or parts["db"] != DatabaseConst.EVENT_DB_NAME or parts["table"] != "EVENT":
                        continue
                    field = parts["field"]
                    ext_type = mapping_item.get(MappingFields.external_data_type)
                    int_type = mapping_item.get(MappingFields.internal_data_type)
                    concrete_external_path = external_path_pattern.replace(
                        "[event-id]", f"[event-id={event_id}]"
                    )
                    with allure.step("Run gnmic once and parse the value"):
                        gnmi_out, duration_sec = run_gnmic_once_flat(concrete_external_path, client=client, username=username, password=password)
                        gnmi_value = parse_gnmic_flat_output(gnmi_out)
                    with allure.step("Fetch the EVENT_DB value for the same id and field"):
                        db_value = db_hget(DatabaseConst.EVENT_DB_NAME, f"EVENT|{event_id}", field)
                    if db_value is not None:
                        db_value = db_value.strip().strip('"')

                    result = verify_values_and_duration(concrete_external_path, event_id, field, gnmi_value, db_value, duration_sec, ext_type, int_type)
                    assert result[event_id][concrete_external_path]["result"], "Values and duration are not as expected"
                    results[event_id][external_path_pattern] = result
    return results


def verify_values_and_duration(concrete_external_path: str, event_id: str, field: str, gnmi_value: Optional[str], db_value: Optional[str], duration_sec: Optional[float], ext_type: Optional[str], int_type: Optional[str]):
    """
    Verify the values and duration are as expected
    """
    with allure.step("Verify the values and duration are as expected"):
        if gnmi_value is None or db_value is None:
            return False

        gnmi_converted = _convert_value_by_type(gnmi_value, ext_type)
        db_converted = _convert_value_by_type(db_value, int_type)
        equal = (gnmi_converted == db_converted) and (duration_sec < 9)
        returned_result: Dict[str, dict] = {}
        entry = {
            "gnmi_value": gnmi_converted,
            "db_value": db_converted,
            "equal": equal,
            "ext_type": ext_type,
            "int_type": int_type,
            "gnmi_path": concrete_external_path,
            "duration_sec": duration_sec,
            "db_key": f"EVENT|{event_id}",
            "field": field,
            "result": equal
        }
        returned_result[event_id] = {concrete_external_path: entry}
        return returned_result


def _convert_value_by_type(
    value: Any,
    data_type: Optional[str],
    *,
    strict: bool = True,
) -> Optional[Converted]:
    """
    Convert a single value according to data_type.

    - strict=True  -> raise on conversion errors (recommended for tests)
    - strict=False -> fallback to string on conversion errors
    """

    if value is None:
        return None

    dt = (data_type or "").strip().lower()
    s = str(value).strip()
    # string (default)
    if dt in ("", "string"):
        return str(value)
    # boolean
    if dt in ("bool", "boolean"):
        if isinstance(value, bool):
            return value
        lv = s.lower()
        if lv in ("true", "1", "yes", "on", "enabled"):
            return True
        if lv in ("false", "0", "no", "off", "disabled"):
            return False
        if strict:
            raise ValueError(f"Cannot parse boolean from {value!r}")
        return s
    # signed integers
    if dt in ("int", "int64"):
        if isinstance(value, bool):
            if strict:
                raise ValueError(f"Refusing bool -> int conversion: {value!r}")
            return s
        try:
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                if value.is_integer():
                    return int(value)
                raise ValueError
            return int(s, 0)  # supports decimal & hex
        except Exception:
            if strict:
                raise ValueError(f"Cannot parse int from {value!r}")
            return s
    # unsigned integers
    if dt in ("uint16", "uint32", "uint64"):
        try:
            num = value if isinstance(value, int) else int(s, 0)
            if num < 0:
                raise ValueError
            return int(num)
        except Exception:
            if strict:
                raise ValueError(f"Cannot parse {dt} from {value!r}")
            return s
    # floats
    if dt in ("float", "float64", "ieeefloat32"):
        if isinstance(value, bool):
            if strict:
                raise ValueError(f"Refusing bool -> float conversion: {value!r}")
            return s
        try:
            return float(value) if isinstance(value, (int, float)) else float(s)
        except Exception:
            if strict:
                raise ValueError(f"Cannot parse float from {value!r}")
            return s
    # custom float64 / 1e8
    if dt == "float64dividedby1e8":
        try:
            base = float(s) if (("." in s) or ("e" in s.lower())) else float(int(s, 0))
            return base / 1e8
        except Exception:
            if strict:
                raise ValueError(f"Cannot parse {dt} from {value!r}")
            return s
    # enums / domain textual types
    # (LeakSensors, IBSpeed, FormFactorType, TransPresent, ...)
    return s


def _load_yaml_from_input(yaml_content_or_path: str) -> Union[List, Dict, None]:
    """
    Try to parse the given string as YAML content; if that fails, treat it as a file path and load.
    Returns a Python object (list/dict) or None if parsing fails.
    """
    if not yaml_content_or_path:
        return None
    try:
        data = yaml.safe_load(yaml_content_or_path)
        if data is not None:
            return data
    except Exception:
        pass
    possible_path = yaml_content_or_path.strip()
    if os.path.exists(possible_path) and os.path.isfile(possible_path):
        with open(possible_path, "r") as f:
            return yaml.safe_load(f)
    return None


def build_external_map_from_yaml(yaml_content_or_path: str, internal_prefixes: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """
    Build a dictionary keyed by externalPath from the mappings YAML (content or path).
    internal_prefixes: filter items whose internalPath starts with ANY of the given prefixes
                         (e.g., ["STATE_DB/", "COUNTERS_DB/"]). If None, include all items.
    """
    data = _load_yaml_from_input(yaml_content_or_path)
    if data is None:
        return {}

    items: List[dict]
    if isinstance(data, list):
        items = [i for i in data if isinstance(i, dict)]
    elif isinstance(data, dict) and isinstance(data.get("mappings"), list):
        items = [i for i in data["mappings"] if isinstance(i, dict)]
    else:
        return {}

    prefixes: List[str] = []
    if internal_prefixes:
        for p in internal_prefixes:
            if not isinstance(p, str) or not p:
                continue
            base = p.strip()
            with_slash = base if base.endswith("/") else f"{base}/"
            without_slash = base[:-1] if base.endswith("/") else base
            for variant in (with_slash, without_slash):
                if variant not in prefixes:
                    prefixes.append(variant)

    def _match_prefix(internal_path: str) -> bool:
        if not prefixes:
            return True
        ip = internal_path.strip()
        return any(ip.startswith(pref) for pref in prefixes)

    result: Dict[str, dict] = {}
    for item in items:
        external_path = item.get(MappingFields.external_path)
        internal_path = item.get(MappingFields.internal_path, "")
        if not external_path:
            continue
        if not isinstance(internal_path, str):
            continue
        if not _match_prefix(internal_path):
            continue
        result[external_path] = item
    return result


def build_external_maps_by_db(yaml_content_or_path: str, db_names: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, dict]]:
    """
    Build a dictionary grouped by DB prefix (e.g., STATE_DB, COUNTERS_DB, CONFIG_DB, EVENT_DB).
    Each value is a dict keyed by externalPath for that DB group.
    If db_names is provided, only include those DB names.
    """
    data = _load_yaml_from_input(yaml_content_or_path)
    if data is None:
        return {}

    items: List[dict]
    if isinstance(data, list):
        items = [i for i in data if isinstance(i, dict)]
    elif isinstance(data, dict) and isinstance(data.get("mappings"), list):
        items = [i for i in data["mappings"] if isinstance(i, dict)]
    else:
        return {}

    allowed: Optional[set] = set(db_names) if db_names else None
    grouped: Dict[str, Dict[str, dict]] = {}

    for item in items:
        external_path = item.get(MappingFields.external_path)
        internal_path = item.get(MappingFields.internal_path, "")
        if not external_path or not isinstance(internal_path, str):
            continue
        db_prefix = internal_path.split('/', 1)[0].strip()
        if not db_prefix:
            continue
        if allowed is not None and db_prefix not in allowed:
            continue
        grouped.setdefault(db_prefix, {})[external_path] = item

    return grouped


def run_gnmic_once_flat(external_path: str, client: Optional[GnmiClient] = None, username: Optional[str] = None, password: Optional[str] = None) -> str:
    """
    Execute gnmic subscribe ONCE for the given external path and return flat output.
    Preferred: use provided GnmiClient (consistent with existing GNMI tests).
    Fallback: shell out via player engine if client is not provided.
    """
    path_no_slash = external_path.lstrip('/')
    if client is not None:
        out, _err, duration_sec, _ = client.gnmic_subscribe(
            prefix='',
            path=path_no_slash,
            mode=GnmiMode.ONCE,
            flat=True,
            username=username or '',
            password=password or '',
            skip_cert_verify=True,
            wait_till_done=True
        )
        return out, duration_sec
    player = TestToolkit.engines.get('sonic_mgmt') or TestToolkit.engines.dut
    engine = TestToolkit.engines.dut
    cmd = (
        f'gnmic -a {engine.ip} --port 9339 --skip-verify subscribe '
        f'--path "{path_no_slash}" --target nvos -u {username or "admin"} -p {password or "admin"} --mode ONCE --format flat'
    )
    return player.run_cmd(cmd, validate=False, timeout=60)


def parse_gnmic_flat_output(output: str) -> Optional[str]:
    """
    Parse gnmic --format flat output and return the last line's value.
    Supports separators '=' and ':' (e.g., 'path=value' or 'path: value').
    """
    if not output:
        return None
    candidates = []
    for ln in output.splitlines():
        if not ln:
            continue
        if "=" in ln or ":" in ln:
            candidates.append(ln)
    lines = candidates
    if not lines:
        return None
    last = lines[-1]
    # Choose the separator that appears last in the line (handles '=' inside bracketed keys)
    idx_eq = last.rfind("=")
    idx_colon = last.rfind(":")
    sep_idx = max(idx_eq, idx_colon)
    if sep_idx == -1:
        return None
    val = last[sep_idx + 1:]
    return val.strip().strip('"').strip("'")


def parse_internal_path(internal_path: str) -> Optional[Dict[str, str]]:
    """
    Parse 'DB/TABLE/FIELD[...][...]' into components.
    Returns dict with keys: db, table, field, raw
    """
    if not isinstance(internal_path, str) or "/" not in internal_path:
        return None
    head, rest = internal_path.split("/", 1)
    if "/" not in rest:
        return None
    table, field_and_keys = rest.split("/", 1)
    field = field_and_keys.split("[", 1)[0]
    return {"db": head.strip(), "table": table.strip(), "field": field.strip(), "raw": internal_path}


def db_hget(db_name: str, key: str, field: str) -> Optional[str]:
    """
    Run 'sonic-db-cli <DB> HGET "<KEY>" "<FIELD>"' and return value (stripped), or None.
    """
    engine = TestToolkit.engines.dut
    out = engine.run_cmd(f'sonic-db-cli {db_name} HGET "{key}" "{field}"', validate=False)
    val = out.strip()
    return val if val else None


def _type_check_and_cast(value: Optional[str], data_type: Optional[str]) -> Dict[str, Union[bool, Optional[Union[int, str]], str]]:
    """
    Coerce a string value to the expected data type and validate.
    Supported data types: 'uint64', 'string' (extend as needed).
    Returns dict: {'ok': bool, 'value': coerced_value_or_None, 'error': reason_if_any}
    """
    if value is None:
        return {"ok": False, "value": None, "error": "no_value"}
    dt = (data_type or "").strip().lower()
    if dt in ("string", ""):
        return {"ok": True, "value": str(value), "error": ""}
    if dt == "uint64":
        try:
            s = str(value).strip()
            if s.startswith(("0x", "0X")):
                num = int(s, 16)
            else:

                num = int(s)
            if num < 0:
                return {"ok": False, "value": None, "error": "negative_uint64"}
            return {"ok": True, "value": num, "error": ""}
        except Exception as e:
            return {"ok": False, "value": None, "error": f"uint64_parse_error:{e}"}

    return {"ok": True, "value": str(value), "error": ""}


def _get_event_ids() -> List[str]:
    """
    Read EVENT_DB keys and extract event ids from keys like 'EVENT|<id>'
    """
    engine = TestToolkit.engines.dut
    out = engine.run_cmd('sonic-db-cli EVENT_DB KEYS "EVENT|*"', validate=False)
    ids: List[str] = []
    for ln in (out or "").splitlines():
        ln = ln.strip().strip('"').strip("'")
        if not ln:
            continue
        # Expect 'EVENT|<id>'
        if "|" in ln:
            ids.append(ln.split("|", 1)[1])
    return ids
