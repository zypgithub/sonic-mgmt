# Factory to create BIOS objects
from ngts.nvos_tools.infra.BiosTools.CoffeeLakeBios import CoffeeLakeBios
from ngts.nvos_tools.infra.BiosTools.SnowyOwlBios import SnowyOwlBios


class BiosFactory:
    """
    A factory class to create BIOS objects based on the switch type.

    The `switch_type` parameter is a string that can include additional
    information such as model numbers or other identifiers. The logic
    matches specific keywords within `switch_type` to determine the BIOS type.

    Examples:
        - "Q3400-RA Black Mamba" will return a `CoffeeLakeBios` object.
        - "Juliet - N5112_LD" will return a `SnowyOwlBios` object.

    Raises:
        ValueError: If `switch_type` does not match any known types.
    """

    @staticmethod
    def create_bios(switch_type, topology_obj, dut_engine, nvue_cli_obj, dut_ip):
        coffee_lake_switches = ("Crocodile", "Black Mamba", "Gorilla")
        snowy_owl_switches = ("Juliet",)

        if any(switch in switch_type for switch in coffee_lake_switches):
            return CoffeeLakeBios(topology_obj, dut_engine, nvue_cli_obj, dut_ip)
        elif any(switch in switch_type for switch in snowy_owl_switches):
            return SnowyOwlBios(topology_obj, dut_engine, nvue_cli_obj, dut_ip)
        else:
            raise ValueError(f"Unknown switch_type: {switch_type}")
