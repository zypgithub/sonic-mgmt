import json


def test_psu_sensor_key_prefix(engines, show_platform_summary):
    """
    Test that the PSU sensor output has the expected prefix.
    """
    dut_engine = engines.dut
    output = dut_engine.run_cmd("sensors -j dps460-i2c-*-*")
    output_json = json.loads(output)
    for chip_value in output_json.values():
        for sensor_key in chip_value.keys():
            if sensor_key == "Adapter":
                continue
            # panther platform has a key "temp3", this is a won't fix issue
            if sensor_key == "temp3" and 'SN2700-A1' in show_platform_summary['hwsku']:
                continue
            assert sensor_key.startswith("PSU-"), f"Sensor {sensor_key} has unexpected prefix"
