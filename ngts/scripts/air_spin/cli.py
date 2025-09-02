import argparse
import logging
import sys
from ngts.scripts.air_spin.api import AirSpinApi

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)


def main():
    """main function for air-spin"""
    parser = argparse.ArgumentParser(
        description="Air Virtual Switch Development Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(required=True)
    create_parser = subparsers.add_parser("create", help="Create new air simulation")
    create_parser.add_argument("--setup_name", required=True, help="Setup Simulation name")
    create_parser.add_argument("--topology_type", required=True, help="Topology type", choices=["community", "canonical"])
    create_parser.add_argument("--simx_version", default="", help="Simx version")
    create_parser.add_argument("--base_version", required=True, help="Base version")
    create_parser.add_argument("--topology", required=True, help="Topology")
    create_parser.add_argument("--custom_tarball_name", required=True, help="Custom tarball name")
    create_parser.add_argument("--branch", required=True, help="Branch")
    create_parser.add_argument("--dut_name", default="", help="DUT name")
    create_parser.add_argument("--dut_hwsku", required=True, help="DUT hwsku")
    create_parser.add_argument("--chip_type", default="", help="Chip type")
    create_parser.add_argument("--topology_links_path", default="", help="Topology links path")
    create_parser.add_argument("--organization_name", default="SONIC", help="Organization name")
    create_parser.set_defaults(func=handle_create)
    args = parser.parse_args()
    api = AirSpinApi()
    if args.func:
        args.func(args, api)
    else:
        parser.print_help()


def handle_create(args, api):
    """handle create command"""
    logger.info(f"Creating AIR SIMULATION {args.setup_name}")

    api.create_simulation(
        setup_name=args.setup_name,
        topology_type=args.topology_type,
        simx_version=args.simx_version,
        dut_name=args.dut_name,
        dut_hwsku=args.dut_hwsku,
        chip_type=args.chip_type,
        base_version=args.base_version,
        custom_tarball_name=args.custom_tarball_name,
        branch=args.branch,
        topology=args.topology,
        organization_name=args.organization_name,
        topology_links_path=args.topology_links_path
    )


def handle_destroy(args, api):
    """handle destroy command"""


if __name__ == "__main__":
    main()
