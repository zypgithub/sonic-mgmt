import allure
import logging
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType, PackageConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_constants.constants_nvos import ConfState

logger = logging.getLogger()


class Packages(BaseComponent):
    def __init__(self, parent_obj=None, path=None):
        file_path = path if path else '/packages'
        BaseComponent.__init__(self, parent=parent_obj, path=file_path)
        self.repositories = Repositories(self)
        self.keys = Keys(self)

    def get_packages_field_values(self, field_names=[PackageConsts.REPO_ID, PackageConsts.KEY, PackageConsts.USE_VRF]):
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
        values = {}
        for field_name in field_names:
            if field_name in output.keys():
                values[field_name] = output[field_name]
            else:
                values[field_name] = ""
        return values

    def verify_show_packages_output(self, expected_dictionary):
        with allure.step("Verify show packages output"):
            logging.info("Verify show packages output")
            output = self.get_packages_field_values()
            logger.info("Expected show packages output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output.keys()

    def verify_repository_in_show_packages_output(self, repository):
        with allure.step("Verify repository {} exists in show packages output".format(repository)):
            logging.info("Verify repository {} exists in show packages output".format(repository))
            output = self.get_packages_field_values()
            assert repository in output.get(PackageConsts.REPO_ID, {}), "repository {} does not exist in the show packages output".format(repository)
            return output.get(PackageConsts.REPO_ID, {}).get(repository)

    def set_use_vrf(self, vrf_value, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set use-vrf with value : {}".format(vrf_value)):
            logging.info("Set use-vrf with value : {}".format(vrf_value))
            result = self.set(op_param_name=PackageConsts.USE_VRF, op_param_value=vrf_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_use_vrf(self, apply=False, ask_for_confirmation=False):
        return self.unset(PackageConsts.USE_VRF, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def show_packages_output(self):
        with allure.step("Verify show packages output"):
            logging.info("Verify show packages output")
            output = self.get_packages_field_values()
            return output

    def unset_packages_configuration(self, verify_cleanup=True, apply=True, ask_for_confirmation=True):
        """
        Unset all packages configuration and optionally verify cleanup

        Args:
            verify_cleanup: Whether to verify that configuration was properly cleaned up
            apply: Whether to apply the unset operation immediately
            ask_for_confirmation: Whether to ask for confirmation when applying

        Returns:
            Result of the unset operation or False if verification fails
        """
        with allure.step("Unset all packages configuration"):
            logger.info("Unsetting all packages configuration")

            try:
                # Perform the unset operation
                unset_result = self.unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
                unset_result.verify_result(should_succeed=True)
                logger.info("Successfully unset all packages configuration")

                if verify_cleanup:
                    # Verify cleanup was successful
                    packages_output = self.get_packages_field_values()
                    logger.info(f"Packages output after unset: {packages_output}")

                    # Check if only system default repositories remain
                    if packages_output and PackageConsts.REPO_ID in packages_output:
                        remaining_repo_urls = list(packages_output[PackageConsts.REPO_ID].keys())
                        system_default_repos = [repo for repo in remaining_repo_urls if repo.startswith('copy:')]
                        non_system_repos = [repo for repo in remaining_repo_urls if not repo.startswith('copy:')]

                        if not non_system_repos:
                            logger.info(f"Verified: All user-configured packages cleared. Only system defaults remain: {system_default_repos}")
                        else:
                            logger.warning(f"User-configured repositories still present: {non_system_repos}")
                            return False
                    else:
                        logger.info("Verified: All packages configuration cleared via show command")

                return unset_result

            except Exception as e:
                logger.error(f"Failed to unset packages configuration: {e}")
                raise

    def nv_action_fetch_system_packages(self, engines, remote_url, scope="", vrf=""):
        try:
            cmd = "nv action fetch system packages key " + remote_url
            if scope:
                cmd += " scope " + scope
                if vrf:
                    cmd += " vrf " + vrf

            output = engines.dut.run_cmd(cmd)
            return output
        except Exception as cli_err:
            assert False, cli_err

    def nv_action_delete_system_packages(self, engines, key):
        cmd = "nv action delete system packages key " + key
        output = engines.dut.run_cmd(cmd)
        return output

    def get_system_packages_key(self):
        """
        Get system packages keys information - delegates to keys component

        Returns:
            Dictionary containing the keys information
        """
        return self.keys.get_system_packages_key()


class Keys(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/key')
        self.keys_dict = {}

    def set_key(self, key_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set key with id : {}".format(key_id)):
            logging.info("Set key with id : {}".format(key_id))
            key_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            self.set(op_param_name=key_id, op_param_value=key_value, expected_str=expected_str,
                     apply=apply, ask_for_confirmation=ask_for_confirmation)
            key = Key(self, key_id)
            self.keys_dict.update({key_id: key})
            return key

    def unset_key(self, key_id, apply=False, ask_for_confirmation=False):
        result_obj = self.keys_dict[key_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.keys_dict.pop(key_id)
        return result_obj

    def verify_show_keys_list(self, expected_keys_list):
        with allure.step("Verify keys {} exists in show packages key output".format(expected_keys_list)):
            logging.info("Verify keys {} exists in show packages key output".format(expected_keys_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_keys_list, output.keys()).verify_result()

    def get_system_packages_key(self):
        """
        Get system packages keys information

        Returns:
            Dictionary containing the keys information
        """
        try:
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            return output
        except Exception as e:
            logger.error(f"Failed to get system packages key: {e}")
            return {}


class Key(BaseComponent):
    def __init__(self, parent_obj=None, key_id=''):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + key_id)
        self.key_id = key_id

    def verify_show_key_output(self, expected_dictionary):
        with allure.step("Verify show packages key {} output".format(self.key_id)):
            logging.info("Verify show packages key {} output".format(self.key_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            logger.info("Expected show key output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output


class Repositories(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/repository')
        self.repositories_dict = {}

    def set_repository(self, repo_url_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set repository with url : {}".format(repo_url_id)):
            logging.info("Set repository with url : {}".format(repo_url_id))
            repo_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            self.set(op_param_name=repo_url_id, op_param_value=repo_value, expected_str=expected_str,
                     apply=apply, ask_for_confirmation=ask_for_confirmation)
            repository = Repository(self, repo_url_id)
            self.repositories_dict.update({repo_url_id: repository})
            return repository

    def unset_repository(self, repo_url_id, apply=False, ask_for_confirmation=False):
        result_obj = self.repositories_dict[repo_url_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.repositories_dict.pop(repo_url_id)
        return result_obj

    def verify_show_repositories_list(self, expected_repositories_list):
        with allure.step("Verify repositories {} exists in show packages repository output".format(expected_repositories_list)):
            logging.info("Verify repositories {} exists in show packages repository output".format(expected_repositories_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_repositories_list, output.keys()).verify_result()

    def get_repository_output(self, repo_url_id):
        with allure.step("Verify show packages repository {} output".format(repo_url_id)):
            logging.info("Verify show packages repository {} output".format(repo_url_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            return output.get(repo_url_id, {})


class Repository(BaseComponent):
    def __init__(self, parent_obj=None, repo_url_id=''):
        # URL-encode slashes in repository URL to prevent them from being interpreted as path separators
        encoded_repo_url = repo_url_id.replace('/', '%2F')
        BaseComponent.__init__(self, parent=parent_obj, path='/' + encoded_repo_url)
        self.repo_url_id = repo_url_id
        self.distributions = Distributions(self)

    def set_insecure(self, insecure_value, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set insecure with value : {}".format(insecure_value)):
            logging.info("Set insecure with value : {}".format(insecure_value))
            result = self.set(op_param_name=PackageConsts.INSECURE, op_param_value=insecure_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_insecure(self, apply=False, ask_for_confirmation=False):
        return self.unset(PackageConsts.INSECURE, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_source(self, source_value, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set source with value : {}".format(source_value)):
            logging.info("Set source with value : {}".format(source_value))
            result = self.set(op_param_name=PackageConsts.SOURCE, op_param_value=source_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_source(self, apply=False, ask_for_confirmation=False):
        return self.unset(PackageConsts.SOURCE, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_key(self, key_value, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set key with value : {}".format(key_value)):
            logging.info("Set key with value : {}".format(key_value))
            result = self.set(op_param_name=PackageConsts.KEY, op_param_value=key_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_key(self, apply=False, ask_for_confirmation=False):
        return self.unset(PackageConsts.KEY, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def get_repository_output(self):
        """Get repository output for verification"""
        with allure.step("Get show packages repository output"):
            logging.info("Get show packages repository output")
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            return output

    def verify_show_repository_output(self, expected_dictionary):
        with allure.step("Verify show packages repository {} output".format(self.repo_url_id)):
            logging.info("Verify show packages repository {} output".format(self.repo_url_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            logger.info("Expected show repository output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output


class Distributions(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/distribution')
        self.distributions_dict = {}

    def set_distribution(self, repo_dist_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set distribution with id : {}".format(repo_dist_id)):
            logging.info("Set distribution with id : {}".format(repo_dist_id))
            dist_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            self.set(op_param_name=repo_dist_id, op_param_value=dist_value, expected_str=expected_str,
                     apply=apply, ask_for_confirmation=ask_for_confirmation)
            distribution = Distribution(self, repo_dist_id)
            self.distributions_dict.update({repo_dist_id: distribution})
            return distribution

    def unset_distribution(self, repo_dist_id, apply=False, ask_for_confirmation=False):
        result_obj = self.distributions_dict[repo_dist_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.distributions_dict.pop(repo_dist_id)
        return result_obj

    def verify_show_distributions_list(self, expected_distributions_list):
        with allure.step("Verify distributions {} exists in show packages repository distribution output".format(expected_distributions_list)):
            logging.info("Verify distributions {} exists in show packages repository distribution output".format(expected_distributions_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_distributions_list, output.keys()).verify_result()


class Distribution(BaseComponent):
    def __init__(self, parent_obj=None, repo_dist_id=''):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + repo_dist_id)
        self.repo_dist_id = repo_dist_id
        self.pools = Pools(self)

    def verify_show_distribution_output(self, expected_dictionary):
        with allure.step("Verify show packages repository distribution {} output".format(self.repo_dist_id)):
            logging.info("Verify show packages repository distribution {} output".format(self.repo_dist_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            logger.info("Expected show distribution output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output


class Pools(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/pool')
        self.pools_dict = {}

    def set_pool(self, repo_pool_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set pool with id : {}".format(repo_pool_id)):
            logging.info("Set pool with id : {}".format(repo_pool_id))
            pool_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            result = self.set(op_param_name=repo_pool_id, op_param_value=pool_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            pool = Pool(self, repo_pool_id)
            self.pools_dict.update({repo_pool_id: pool})
            return result

    def unset_pool(self, repo_pool_id, apply=False, ask_for_confirmation=False):
        result_obj = self.pools_dict[repo_pool_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.pools_dict.pop(repo_pool_id)
        return result_obj

    def verify_show_pools_list(self, expected_pools_list):
        with allure.step("Verify pools {} exists in show packages repository distribution pool output".format(expected_pools_list)):
            logging.info("Verify pools {} exists in show packages repository distribution pool output".format(expected_pools_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_pools_list, output.keys()).verify_result()


class Pool(BaseComponent):
    def __init__(self, parent_obj=None, repo_pool_id=''):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + repo_pool_id)
        self.repo_pool_id = repo_pool_id

    def verify_show_pool_output(self, expected_dictionary):
        with allure.step("Verify show packages repository distribution pool {} output".format(self.repo_pool_id)):
            logging.info("Verify show packages repository distribution pool {} output".format(self.repo_pool_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            logger.info("Expected show pool output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output

    def get_pool_output(self):
        with allure.step("Verify show packages repository distribution pool {} output".format(self.repo_pool_id)):
            logging.info("Verify show packages repository distribution pool {} output".format(self.repo_pool_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show(rev=ConfState.APPLIED)).get_returned_value()
            return output
