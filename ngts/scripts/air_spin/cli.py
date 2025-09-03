import argparse
from ngts.scripts.air_spin.api import AirSpinApi


def main():
    """main function for air-spin"""
    parser = argparse.ArgumentParser(
        description="Air Virtual Switch Development Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(required=True)
    create_parser = subparsers.add_parser("create", help="Create new air simulation")
    create_parser.add_argument("--setup_name", default="", help="Setup Simulation name")
    create_parser.add_argument("--topology_type", required=True, help="Topology type", choices=["community", "canonical"])
    create_parser.add_argument("--simx_version", default="", help="Simx version")
    create_parser.add_argument("--base_version", required=True, help="Base version")
    create_parser.add_argument("--topology", required=True, help="Topology")
    create_parser.add_argument("--custom_tarball_name", required=True, help="Custom tarball name")
    create_parser.add_argument("--branch", required=True, help="Branch")
    create_parser.add_argument("--dut_name", default="", help="DUT name")
    create_parser.add_argument("--dut_hwsku", required=True, help="DUT hwsku")
    create_parser.add_argument("--chip_type", default="", help="Chip type")
    create_parser.add_argument("--custom_links_path", default="", help="Custom links path json file name")
    create_parser.add_argument("--organization_name", default="SONIC", help="Organization name")
    create_parser.add_argument("--dbs_to_run_path", default="", help="path to file containing dbs to run, for example \"communty/pretest.db,canonical/nightly.db\"")
    create_parser.set_defaults(func=handle_create)
    args = parser.parse_args()
    api = AirSpinApi()
    if args.func:
        args.func(args, api)
    else:
        parser.print_help()


def handle_create(args, api):
    """handle create command"""
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
        custom_links_path=args.custom_links_path,
        dbs_to_run_path=args.dbs_to_run_path
    )


def handle_destroy(args, api):
    """handle destroy command"""


if __name__ == "__main__":
    main()
