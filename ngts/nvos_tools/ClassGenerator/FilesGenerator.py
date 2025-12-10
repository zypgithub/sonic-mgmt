import os
from ngts.nvos_constants.constants_nvos import OpenApiReqType

SHOW_METHOD_NAME = '    def show(engine, resource_path, op_param="", output_format=OutputFormat.json):\n'
SET_METHOD_NAME = '    def set(engine, resource_path, op_param_name="", op_param_value=""):\n'
UNSET_METHOD_NAME = '    def unset(engine, resource_path, op_param=""):\n'

NVUE_WRAPPER_FILENAME = 'nvue_{}_clis'
OPENAPI_WRAPPER_FILENAME = 'openapi_{}_clis'
NVUE_WRAPPER_CLASSNAME = 'Nvue{}Cli'
OPENAPI_WRAPPER_CLASSNAME = 'OpenApi{}Cli'


# ---- Create files and directories ----

def create_init_py_file(base_directory):
    path_to_init_file = base_directory + '/__init__.py'
    if not os.path.isfile(path_to_init_file):
        init_file = open(path_to_init_file, 'w')
        init_file.close()
        print('-__init__.py was created under {}'.format(base_directory))
    else:
        print('-__init__.py already exists under {}'.format(base_directory))


def create_base_directory(root_class_name):
    base_directory = os.getcwd().replace("/ClassGenerator", "")
    path_to_class_directory = r'{base_directory}/{root_component}'.format(root_component=root_class_name,
                                                                          base_directory=base_directory)
    if not os.path.isdir(path_to_class_directory):
        os.mkdir(path_to_class_directory)
        print('-{} directory was created'.format(path_to_class_directory))
    else:
        print('-{} directory already exists'.format(path_to_class_directory))

    return path_to_class_directory


def create_class_file_in_relevant_directory(component, base_directory):
    path_to_class = base_directory + '/{class_name}.py'.format(class_name=component.name.capitalize())

    if os.path.isfile(path_to_class):
        return None
    else:
        py_class_file = open(path_to_class, 'a')
        print('-{} was created'.format(component.name.capitalize()))
        return py_class_file

# --------------------------------------------------------------------------------------------------


# ------- Add class components ---------------------------------------------------------------------

def add_imports(component, py_class_file, root_class_name):
    if component.show_method:
        py_class_file.write('import allure\n')
        py_class_file.write('from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit\n')
        py_class_file.write('from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool\n')
    py_class_file.write('from ngts.nvos_tools.infra.BaseComponent import BaseComponent\n')
    py_class_file.write('from ngts.nvos_constants.constants_nvos import ApiType\n')

    temp_file_name = NVUE_WRAPPER_FILENAME.format(root_class_name)
    temp_class_name = NVUE_WRAPPER_CLASSNAME.format(root_class_name.capitalize())
    py_class_file.write('from ngts.cli_wrappers.nvue.{file_name} import {class_name}\n'.format(file_name=temp_file_name,
                                                                                               class_name=temp_class_name))
    temp_file_name = OPENAPI_WRAPPER_FILENAME.format(root_class_name)
    temp_class_name = OPENAPI_WRAPPER_CLASSNAME.format(root_class_name.capitalize())
    py_class_file.write('from ngts.cli_wrappers.openapi.{file_name} import {class_name}\n'.format(file_name=temp_file_name,
                                                                                                  class_name=temp_class_name))

    if len(component.list_of_next_components) != 0:
        for component in component.list_of_next_components:
            py_class_file.write('from ngts.nvos_tools.{root_component}.{name} import {name}\n'.format(
                root_component=root_class_name, name=component.name.capitalize()))

    py_class_file.write('\n\n')


def add_inner_class_params(component, py_class_file):
    if len(component.list_of_next_components) != 0:
        for component in component.list_of_next_components:
            py_class_file.write('    {} = None\n'.format(component.name))


def add_method(method_name, py_class_file, resource_path):
    if method_name == 'set':
        py_class_file.write('\n    def set(self, op_param_name="", op_param_value=""): \n')
    else:
        py_class_file.write('\n    def {method_name}(self, op_param=""): \n'.format(method_name=method_name))
    py_class_file.write('        raise Exception("{method_name} is not implemented for {resource_path}")\n'.
                        format(method_name=method_name, resource_path=resource_path))

    '''py_class_file.write('    def {method_name}(self, op_param=""): \n'.format(method_name=method_name))
    py_class_file.write('        with allure.step(\'Execute {method_name} for '.format(method_name=method_name))
    py_class_file.write('{resource_path}\'.format(resource_path=self.get_resource_path())):\n')

    cmd_line = 'SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].{method_name}, ' \
               'TestToolkit.get_engine(), \n' \
               '                                                   ' \
               'self.get_resource_path(), op_param).get_returned_value()'.format(
                   method_name=method_name)
    py_class_file.write('            return {}\n\n'.format(cmd_line))'''


def add_params(params, py_class_file):
    for param in params:
        py_class_file.write('    {param_name} = \'\'\n'.format(param_name=param))
    py_class_file.write('\n')


def add_get_resource_path(py_class_file, param_name):
    py_class_file.write('\n    def get_resource_path(self):\n')
    py_class_file.write('        self_path = self._resource_path.format({param_name}=self.{param_name}).rstrip("/")\n'.
                        format(param_name=param_name))

    py_class_file.write('        return "{parent_path}{self_path}".format('
                        '\n            parent_path=self.parent_obj.get_resource_path() if self.parent_obj else "", '
                        'self_path=self_path)\n')


def add_init(component, py_class_file, root_class_name, resource_path):
    param_list = []
    if len(component.list_of_next_components) != 0:
        for component_name in component.list_of_next_components:
            param_list.append(component_name.name)

    py_class_file.write('    def __init__(self, parent_obj):\n')
    for param in param_list:
        py_class_file.write('        self.{param} = {param_class}(self)\n'.format(param=param,
                                                                                  param_class=param.capitalize()))

    line_str = "ApiType.NVUE: Nvue{name}Cli, ApiType.OPENAPI: OpenApi{name}Cli".format(
        name=root_class_name.capitalize())
    py_class_file.write('        self.api_obj = {' + line_str + '}\n')

    py_class_file.write("        self._resource_path = '{}'\n".format(
        resource_path if root_class_name != component.name else "/" + root_class_name))
    py_class_file.write("        self.parent_obj = parent_obj\n")

# --------------------------------------------------------------------------------------------------


# ----- CLI wrapper creation -------------------------------------------------------------------

def create_nvue_clis(path_to_nvue_cli, root_class_name, isnewfie):
    print('-creating nvue clis')

    nvue_cli_file = None

    try:
        if isnewfie:
            nvue_cli_file = open(path_to_nvue_cli, 'w')
            create_nvue_cli_class(nvue_cli_file, root_class_name)
        else:
            nvue_cli_file = open(path_to_nvue_cli, 'a')
    except Exception as ex:
        print("Failed to create nvue cli: " + ex)
    finally:
        if nvue_cli_file:
            nvue_cli_file.close()


def create_nvue_cli_class(nvue_cli_file, root_class_name):
    nvue_cli_file.write("import logging\n")
    nvue_cli_file.write("from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli\n\n")
    nvue_cli_file.write("logger = logging.getLogger()\n\n\n")

    nvue_class_name = NVUE_WRAPPER_CLASSNAME.format(root_class_name.capitalize())
    nvue_cli_file.write("class {}(NvueBaseCli):\n\n".format(nvue_class_name))

    nvue_cli_file.write("    def __init__(self):\n")
    nvue_cli_file.write('        self.cli_name = "{}"\n'.format(root_class_name.capitalize()))


def add_nvue_method(nvue_cli_file, method_str, nvue_request_type):
    print('-adding show method')
    nvue_cli_file.write("    @staticmethod\n")
    nvue_cli_file.write(method_str)

    nvue_cli_file.write("        path = resource_path.replace('/', ' ')\n")
    cmd = "        cmd = \"nv {request_type} ".format(request_type=nvue_request_type)
    if nvue_request_type == "show":
        cmd += "--output {output_format} "
    cmd += '{path} {params}\".\\\n            format('
    if nvue_request_type == "show":
        cmd += 'output_format=output_format, '
    cmd += 'path=path, params={})\n'.format('op_param_value' if nvue_request_type == 'set' else 'op_param')

    nvue_cli_file.write(cmd)
    nvue_cli_file.write('        logging.info("Running \'{cmd}\' on dut using NVUE".format(cmd=cmd))\n')
    nvue_cli_file.write('        return engine.run_cmd(cmd)\n\n')


def create_nvue_cli_wrapper(root_class_name):
    print('\n>Creating nvue cli wrapper')

    base_directory = os.getcwd().replace("nvos_tools/ClassGenerator", "cli_wrappers")
    path_to_nvue_cli = r'{root_path}/nvue/nvue_{name}_clis.py'.format(root_path=base_directory, name=root_class_name)

    if not os.path.isfile(path_to_nvue_cli):
        create_nvue_clis(path_to_nvue_cli, root_class_name, True)
    else:
        create_nvue_clis(path_to_nvue_cli, root_class_name, False)


def create_openapi_cli_class(openapi_cli_file, root_class_name):
    openapi_cli_file.write("import logging\n")
    openapi_cli_file.write("from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli\n")
    openapi_cli_file.write("logger = logging.getLogger()\n\n\n")

    nvue_class_name = OPENAPI_WRAPPER_CLASSNAME.format(root_class_name.capitalize())
    openapi_cli_file.write("class {}(OpenApiBaseCli):\n\n".format(nvue_class_name))
    openapi_cli_file.write("    def __init__(self):\n")
    openapi_cli_file.write('        self.cli_name = "{}"\n'.format(root_class_name.capitalize()))


def _get_openapi_request(method):
    if method == OpenApiReqType.GET:
        return "OpenApiReqType.GET"
    elif method == OpenApiReqType.DELETE:
        return "OpenApiReqType.DELETE"
    elif method == OpenApiReqType.PATCH:
        return "OpenApiReqType.PATCH"
    else:
        assert "Unexpected openApi type"


def add_openapi_method(openapi_cli_file, method_str, method):
    print('-adding show method')
    openapi_cli_file.write("    @staticmethod\n")
    openapi_cli_file.write(method_str)

    openapi_type = _get_openapi_request(method)
    openapi_cli_file.write('        logging.info("Running {} method on dut using openApi")\n'.format(method))

    run_cmd = "        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, " \
              "\n                                                   " \
              "{method}, engine.ip, engine.open_api_port, resource_path, {str_param})".format(method=openapi_type,
                                                                                              str_param='op_param_name, op_param_value' if method == OpenApiReqType.PATCH else 'op_param')
    openapi_cli_file.write('{}\n\n'.format(run_cmd))


def create_openapi_clis(path_to_openapi_cli, root_class_name, isnewfie, addshow=True, addset=True, addunset=True):
    print('-creating openApi clis')

    openapi_cli_file = None

    try:
        if isnewfie:
            openapi_cli_file = open(path_to_openapi_cli, 'w')
            create_openapi_cli_class(openapi_cli_file, root_class_name)
        else:
            openapi_cli_file = open(path_to_openapi_cli, 'r')

    except Exception as ex:
        print("Failed to create nvue cli: " + str(ex))
    finally:
        if openapi_cli_file:
            openapi_cli_file.close()


def create_openapi_cli_wrapper(root_class_name):
    print('>Creating openApi cli wrapper')

    base_directory = os.getcwd().replace("nvos_tools/ClassGenerator", "cli_wrappers")
    path_to_openapi_cli = r'{root_path}/openapi/openapi_{name}_clis.py'.format(root_path=base_directory, name=root_class_name)

    if not os.path.isfile(path_to_openapi_cli):
        create_openapi_clis(path_to_openapi_cli, root_class_name, True)
    else:
        create_openapi_clis(path_to_openapi_cli, root_class_name, False)


def create_cli_wrappers(root_class_name):
    create_nvue_cli_wrapper(root_class_name)
    create_openapi_cli_wrapper(root_class_name)

# -----------------------------------------------------------------------------------------------


# ---- Class definitions ------------------------------------------------------------------------

def define_classes(component, root_class_name, base_directory):

    py_class_file = create_class_file_in_relevant_directory(component, base_directory)

    if not py_class_file:
        print("! WARNING: Seems that {class_name} class already defined. Please make sure that all required components"
              " exist and all methods are implemented")
    else:
        print('> Creating {class_name} - {path_to_class}'.format(class_name=component.name.capitalize(),
                                                                 path_to_class=py_class_file.name))
        try:
            print('-add imports')
            add_imports(component, py_class_file, root_class_name)
            py_class_file.write('class {class_name}(BaseComponent):\n'.format(class_name=component.name.capitalize()))

            print('-add parameters')
            add_inner_class_params(component, py_class_file)
            add_params(component.param_list, py_class_file)

            print('-add init method')
            add_init(component, py_class_file, root_class_name, component.resource_path)

            if component.param_list and len(component.param_list) > 0:
                add_get_resource_path(py_class_file, component.param_list[0])

            if not component.set_method:
                print('-add set method')
                add_method('set', py_class_file, component.resource_path)

            if not component.unset_method:
                print('-add unset method')
                add_method('unset', py_class_file, component.resource_path)

            py_class_file.close()
            print('*** {class_name} class was successfully created ({path_to_class})'.format(
                class_name=component.name.capitalize(),
                path_to_class=py_class_file.name))

        except BaseException as ex:
            py_class_file.close()
            print('*** exception: ' + str(ex))

    for next_component in component.list_of_next_components:
        define_classes(next_component, root_class_name, base_directory)


# ---------------------------------------------------------------------------------------------------
