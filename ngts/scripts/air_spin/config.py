import os
SETUPS_FOLDER_PATH = "/auto/sw_regression/system/SONIC/MARS/conf/setups"
TOPO_FOLDER_PATH = "/auto/sw_regression/system/SONIC/MARS/conf/topo"
SETUP_TEMPLATE_FILE = "setup_template.setup"
TEMPLATE_FOLDER_PATH = os.path.dirname(os.path.abspath(__file__)) + "/templates"
TOPO_TEMPLATE_FILE = "topology_template.xml"
NOGA_MANAGE_SCRIPT = "/.autodirect/sw_tools/Internal/Noga/RELEASE/latest/cli/noga_manage.py"
NOGA_LABELS_SCRIPT = "/.autodirect/sw_tools/Internal/Noga/RELEASE/latest/import/manage_labels.py"
RESULTS_FOLDER_PATH = "/auto/sw_regression/system/SONIC/MARS/results"

print(TEMPLATE_FOLDER_PATH)
