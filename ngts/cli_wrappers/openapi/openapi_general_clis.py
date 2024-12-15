import json
import logging

from .openapi_command_builder import OpenApiCommandHelper
from ...tests_nvos.general.security.certificate.CertInfo import CertInfo

logger = logging.getLogger()


class OpenApiGeneralCli:

    """
    Open API cli wrapper
    """

    def __init__(self):
        pass

    @staticmethod
    def apply_config(engine, ask_for_confirmation=False, option='', validate_apply_message='', rev_id="",
                     skip_no_config_diff_err=True, verify_execution=False, client_certs_after_apply: CertInfo = None):
        """
        Apply configuration
        :param engine: ssh engine object
        """
        logging.info("Execute config apply using OpenApi")
        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, 'APPLY', engine.ip,
                                                   'system/config/apply', client_certs_after_apply=client_certs_after_apply)

    @staticmethod
    def save_config(engine):
        """
        Save configuration
        :param engine: ssh engine object
        """
        logging.info("Execute config save using OpenApi")
        resource_path = '/revision/applied'
        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, 'PATCH', engine.ip,
                                                   resource_path=resource_path, op_param_name="state", op_param_value="save")

    @staticmethod
    def show_config(engine, revision='applied', output_type='json', param=''):
        """
        Save configuration
        :param engine: ssh engine object
        :param revision: applied / pending / startup
        :param output_type: json / str
        :param param: --all/ ''
        """
        logging.info("Execute config show using OpenApi")
        resource_path = '/?rev={revision}&filled=False'.format(revision=revision)
        res = OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, 'GET', engine.ip,
                                                  resource_path=resource_path, op_param_name=param)

        if output_type == 'json':
            return json.dumps(res)
        else:
            return res

    @staticmethod
    def detach_config(engine, ask_for_confirmation=False):
        """
        Detach configuration
        :param engine: ssh engine object
        """
        logging.info("Execute config save using OpenApi")
        # TODO: not supported yet
        # return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, 'DETACH',
        #                                            engine.ip, 'system/config/detach')
        return ""

    @staticmethod
    def diff_config(engine, revision_1='', revision_2='', output_type='json'):
        """
        diff configuration
        :param engine: ssh engine object
        :param revision_1: config revision 1
        :param revision_2: config revision 2
        :param output_type: json / str
        """
        # TODO:
        logging.info("Execute config diff using OpenApi")
        resource_path = '/?rev={revision_2}&filled=False&diff={revision_1}'.format(revision_2=revision_2, revision_1=revision_1)
        res = OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, 'GET', engine.ip,
                                                  resource_path=resource_path)

        if output_type == 'json':
            return json.dumps(res)
        else:
            return res
