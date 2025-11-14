import argparse
import os
import re
import signal
from ngts.scripts.air_spin.airspin import AirSpin
from ngts.scripts.air_spin.message import Message
from ngts.scripts.air_spin.config import AIR_WEBSITE_SIMULATIONS_URL
msg = Message()


def main():
    """main function for AirSpin CLI"""
    parser = argparse.ArgumentParser(
        description="Air Virtual Switch Development Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    username = os.environ.get('USER')
    if not username:
        msg.error("Error: Failed to get the current user")
        exit(1)
    subparsers = parser.add_subparsers(required=True)
    create_parser = subparsers.add_parser("create", help="Create new air simulation")
    create_parser.add_argument("--setup_name", required=True, default=f"simulation", help="Setup Simulation name")
    create_parser.add_argument("--topology_type", required=True, help="Topology type", choices=["community", "canonical"])
    create_parser.add_argument("--base_version", required=True, help="Base version")
    create_parser.add_argument("--custom_tarball_name", required=True, help="Custom tarball name")
    create_parser.add_argument("--dut_name", default=None, help="DUT name")
    create_parser.add_argument("--dut_hwsku", required=True, help="DUT hwsku")
    create_parser.add_argument("--custom_links_path", default="", help="Custom links path json file name")
    create_parser.add_argument("--organization_name", default="SONIC", help="Organization name")
    create_parser.add_argument("--dbs_to_run", default="", help="path to file containing dbs to run, for example \"communty/pretest.db,canonical/nightly.db\"")
    create_parser.set_defaults(func=handle_create)
    list_parser = subparsers.add_parser("list", help="List all air simulations of the current user")
    list_parser.set_defaults(func=handle_list)
    args = parser.parse_args()
    args.username = username

    if args.func == handle_create:
        if args.topology_type == "community":
            msg.error("The community topology is not supported yet.")
            exit(1)

        validate_setup_name(args.setup_name)
        args.setup_name = username + "_airspin_" + args.setup_name

    airspin = AirSpin(**args.__dict__)

    def _handle_sigint(signum, frame):
        airspin.force_clean_up_dockers()
        exit(1)

    signal.signal(signal.SIGINT, _handle_sigint)

    if args.func:
        args.func(args, airspin)
    else:
        parser.print_help()


def handle_create(args, airspin):
    """handle create command"""
    invalid_usernames = ['svc-nbu-sws-sonic', 'root']
    if airspin.username in invalid_usernames:
        msg.error(f"Error: User {airspin.username} is not allowed to create AirSpin simulations")
        exit(1)
    user_simulations = airspin.get_simulations()
    has_simulation_with_same_name = False
    if user_simulations:
        msg.error(f"Error: User {airspin.username} already has AirSpin simulations. Currently, only one AirSpin simulation is allowed per user.")
        msg.warning(f"Existing simulations:\n")
        for simulation in user_simulations:
            msg.warning(f"{simulation}\n")
            if re.search(r"Simulation\s+-\s+name:\s+(.*)ID", simulation).group(1).strip() == airspin.setup_name:
                has_simulation_with_same_name = True
        msg.info(f"Your simulations can be found in Air website: {AIR_WEBSITE_SIMULATIONS_URL}")
        if has_simulation_with_same_name:
            msg.warning(f"Found an existing AirSpin simulation with the same name as the new one.")
            msg.warning(f"You can override the existing simulation, proceed? (YES/NO)")
            confirmation = input()
            if confirmation != "YES":
                msg.error(f"Failed to create a new AirSpin simulation, please remove an existing simulation first.")
                exit(1)
    airspin.create_simulation()


def handle_list(args, airspin):
    """handle list command"""
    simulations = airspin.get_simulations()
    if not simulations:
        msg.warning(f"No AirSpin simulations found for user {airspin.username}")
    else:
        msg.info(f"AirSpin simulations for user {airspin.username}: \n")
        for simulation in simulations:
            msg.warning(f"{simulation}\n")
        msg.info(f"Your simulations can be found in Air website: {AIR_WEBSITE_SIMULATIONS_URL}")
    exit(0)


def validate_setup_name(setup_name):
    if not bool(re.fullmatch(r"[A-Za-z0-9-]+", setup_name)):
        msg.error(f"Error: Setup name must contain only letters, numbers, and hyphens(-): {setup_name}\
                please run the command again with a valid setup name")
        exit(1)


if __name__ == "__main__":
    main()
