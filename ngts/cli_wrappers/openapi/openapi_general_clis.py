import json
import logging

from .openapi_command_builder import OpenApiCommandHelper, OpenApiRequest, RequestData
from ...nvos_tools.infra.ResultObj import ResultObj
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

    @staticmethod
    def config_patch(engine, filepath, apply=True, detach_first=True):
        """
        Patch configuration from file with optional apply.

        Args:
            engine: SSH engine
            filepath: Path to config file
            apply: If True, applies config and validates. If False, only creates revision
            detach_first: If True, detaches any pending config before patching (default: True)
                         Note: OpenAPI detach may not be fully supported yet

        Returns:
            ResultObj with success/failure status
        """
        # Step 1: Detach pending config if requested (default behavior)
        if detach_first:
            OpenApiGeneralCli.detach_config(engine)

        # Step 2: Read file content
        file_content = engine.run_cmd(f'cat {filepath}')
        logger.info(f"File content preview:\n{file_content[:500]}...")

        request_data = RequestData(
            user_name=engine.engine.username,
            password=engine.engine.password,
            endpoint_ip=engine.ip,
            resource_path='/',
            param_name='',
            param_value=''
        )

        # Step 3: Send PATCH request (creates revision)
        response = OpenApiRequest.send_patch_request(
            request_data,
            text_content=file_content,
            replace=False
        )

        # Check if operation failed
        if response and ('error' in response.lower() or 'failed' in response.lower()):
            return ResultObj(False, info=response, returned_value=response)

        result = ResultObj(True, info="Config patch successful (revision created)", returned_value=response)

        # Step 4: Apply if requested
        if not apply:
            return result

        try:
            apply_result = OpenApiGeneralCli.apply_config(engine, ask_for_confirmation=True)
            logger.info(f"Apply result: {apply_result}")

            # Check if apply failed
            if apply_result and any(err in str(apply_result).lower() for err in ['error', 'failed', 'fail']):
                if 'no config diff' not in str(apply_result).lower():
                    return ResultObj(False, info=f"Apply failed: {apply_result}", returned_value=apply_result)

            return ResultObj(True, info="Patch and apply successful", returned_value=response)
        except Exception as e:
            return ResultObj(False, info=f"Apply failed: {str(e)}", returned_value=str(e))

    @staticmethod
    def config_replace(engine, filepath, apply=True):
        """
        Replace configuration from file with optional apply.

        Args:
            engine: SSH engine
            filepath: Path to config file
            apply: If True, applies config and validates. If False, only creates revision

        Returns:
            ResultObj with success/failure status
        """
        # Step 1: Read file content
        file_content = engine.run_cmd(f'cat {filepath}')
        logger.info(f"File content preview:\n{file_content[:500]}...")

        request_data = RequestData(
            user_name=engine.engine.username,
            password=engine.engine.password,
            endpoint_ip=engine.ip,
            resource_path='/',
            param_name='',
            param_value=''
        )

        # Step 2: Send REPLACE request (creates revision)
        response = OpenApiRequest.send_patch_request(
            request_data,
            text_content=file_content,
            replace=True
        )

        # Check if operation failed
        if response and ('error' in response.lower() or 'failed' in response.lower()):
            return ResultObj(False, info=response, returned_value=response)

        result = ResultObj(True, info="Config replace successful (revision created)", returned_value=response)

        # Step 3: Apply if requested
        if not apply:
            return result

        try:
            apply_result = OpenApiGeneralCli.apply_config(engine, ask_for_confirmation=True)
            logger.info(f"Apply result: {apply_result}")

            # Check if apply failed
            if apply_result and any(err in str(apply_result).lower() for err in ['error', 'failed', 'fail']):
                if 'no config diff' not in str(apply_result).lower():
                    return ResultObj(False, info=f"Apply failed: {apply_result}", returned_value=apply_result)

            return ResultObj(True, info="Replace and apply successful", returned_value=response)
        except Exception as e:
            return ResultObj(False, info=f"Apply failed: {str(e)}", returned_value=str(e))
