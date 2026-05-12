import allure
import logging

FIXTURE_NAME_FORMAT = "<----- :FIXTURE: {} {} scope ----->"
FIXTURE_END = "<=================== :FIXTURE: CONFIG END ===================>"
FIXTURE_IDENTIFIER = ":FIXTURE:"
PACKAGE_SCOPE = "package scope"
MODULE_SCOPE = "module scope"
CLASS_SCOPE = "class scope"
FUNCTION_SCOPE = "function scope"
FIXTURE_NAME_SCOPE_FORMAT = "{} {} scope"
LINE_BREAK = '\n'

logger = logging.getLogger(__name__)

# TODO: temporary workaround. Replace with a proper mixin that adds the
# allure command-tracking interface to every engine type (PexpectSerialEngine,
# AirWebSocketSerialEngine, ...) instead of guarding at every call site.
_ALLURE_TRACKING_PROBE_ATTR = 'get_allure_attached_cmds'


def _supports_allure_tracking(player_info):
    """
    Return True if the player's engine implements the allure command-tracking
    interface (currently provided by ProxySshEngine). Engines like
    PexpectSerialEngine do not yet implement it and must be skipped to avoid
    AttributeError during pytest teardown hooks.
    """
    cli = player_info.get('cli') if hasattr(player_info, 'get') else player_info['cli']
    engine = getattr(cli, 'engine', None)
    return engine is not None and hasattr(engine, _ALLURE_TRACKING_PROBE_ATTR)


def allure_attach(player_alias, cmds):
    """
    Attach commands to allure report
    :param player_alias: player alias, such as 'dut'
    :param cmds: commands
    """
    allure.attach(bytes(cmds, 'utf-8'), player_alias, allure.attachment_type.TEXT)


def collect_stored_cmds_then_attach_to_allure_report(topology_obj):
    """
    Collect stored commands from topology_obj then attach them to allure report
    :param topology_obj: topology_obj fixture
    """
    for player, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        player_info['cli'].engine.remove_null_cmd_fixtures(FIXTURE_IDENTIFIER)
        if player_info['cli'].engine.get_allure_attached_cmds():
            allure_attach(player, LINE_BREAK.join(player_info['cli'].engine.get_allure_attached_cmds()))


def enable_record_cmds(topology_obj):
    """
    Enable record commands of engines in topology_obj
    :param topology_obj: topology_obj fixture
    """
    for _, player_info in topology_obj.players.items():
        if 'cli' in player_info.keys() and _supports_allure_tracking(player_info):
            player_info['cli'].engine.record_cmd = True


def add_fixture_name(topology_obj, fixture_name, fixture_scope):
    """
    Add command title for fixtures, the format is like below
    <----- :FIXTURE: basic_l3_connectivity_configuration module scope ----->
    :param topology_obj: topology_obj fixture
    :param fixture_name: fixture name
    :param fixture_scope: fixture scope
    """
    fixture_name_format = FIXTURE_NAME_FORMAT.format(fixture_name, fixture_scope)
    for _, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        player_info['cli'].engine.update_allure_commands(fixture_name_format)


def add_fixture_end_tag(topology_obj):
    """
    Add a tag into the allure command list, which indicates the fixture log ends
    :param topology_obj: topology_obj fixture
    """
    for _, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        if FIXTURE_IDENTIFIER in LINE_BREAK.join(player_info['cli'].engine.get_allure_attached_cmds()):
            player_info['cli'].engine.update_allure_commands(FIXTURE_END)


def clean_stored_cmds_with_fixture_scope(topology_obj, fixture_name, fixture_scope):
    """
    Clean stored commands
    :param topology_obj: topology_obj fixture
    :param fixture_name: fixture name
    :param fixture_scope: fixture scope value, such as 'function'
    """
    for player, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        if FIXTURE_NAME_SCOPE_FORMAT.format(fixture_name, fixture_scope) in LINE_BREAK.join(player_info['cli'].engine.get_allure_attached_cmds()):
            player_info['cli'].engine.clean_allure_attached_cmds(FIXTURE_IDENTIFIER, FIXTURE_NAME_SCOPE_FORMAT.format(fixture_name, fixture_scope), FIXTURE_END)


def clean_stored_cmds_with_fixture_scope_list(topology_obj):
    """
    Clean stored commands based on the fixture scope list in each engine
    :param topology_obj: topology_obj fixture
    """
    for _, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        fixture_name_scope_list = player_info['cli'].engine.get_allure_fixture_name_scope_list()
        if fixture_name_scope_list:
            for fixture_name_scope in fixture_name_scope_list:
                if fixture_name_scope in LINE_BREAK.join(player_info['cli'].engine.get_allure_attached_cmds()):
                    player_info['cli'].engine.clean_allure_attached_cmds(FIXTURE_IDENTIFIER, fixture_name_scope, FIXTURE_END)
                else:
                    player_info['cli'].engine.remove_unnecessary_fixure_scope_cmds(FIXTURE_IDENTIFIER, FIXTURE_END)
            player_info['cli'].engine.set_allure_fixture_name_scope_list([])


def update_fixture_scope_list(topology_obj, fixture_name, fixture_scope):
    """
    Update fixture scope when fixture ends with test run failed
    At that time, in order to let sysdump stage collect all the command list, pytest_fixture_post_finalizer would not clean
    the stored collected commands
    :param topology_obj: topology_obj fixture
    :param fixture_name: fixture name
    :param fixture_scope: fixture scope value
    """
    for _, player_info in topology_obj.players.items():
        if not _supports_allure_tracking(player_info):
            continue
        if fixture_scope not in player_info['cli'].engine.get_allure_fixture_name_scope_list():
            player_info['cli'].engine.update_allure_fixture_name_scope_list(FIXTURE_NAME_SCOPE_FORMAT.format(fixture_name, fixture_scope))
