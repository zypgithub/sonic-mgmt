def email_message(file_path) {
    echo "Add Tables Details to email from ${file_path}"
    table_content = NGCITools().ciTools.run_sh_return_output("cat ${file_path}")
    echo "Tables Details: ${table_content}"
    env.on_the_fly_head_banners = table_content
}


def pre(name) {
    echo "PRE:: Run upload_regression_results_to_msft.py"
    return true
}

def run_step(name) {
    try {
          echo "Run upload_regression_results_to_msft.py script on ngts sonic-mgmt docker"
          sonic_version = env."${name}_sonic_version"
          command = env."${name}_command"
          params = env."${name}_parameters"
          container_name = env."${name}_container_name"
          echo "Jenkins Job Parameters"
          echo "sonic_version ${sonic_version}"
          echo "command ${command}"
          echo "script additional parameters ${params}"
          echo "container_name ${container_name}"
          script_dir = "/root/mars/workspace/sonic-mgmt/ngts/scripts/upload_regression_results_to_msft/"
          script_name = "upload_regression_results_to_msft.py"
          script_path = "${script_dir}${script_name}"
          build_table_name = "build_mail_table.txt"
          script_params = ["--sonic_version ${sonic_version}", "${command}"]
          dir("ngts/scripts/upload_regression_results_to_msft"){
            parsed_params = NGCITools().ciTools.run_sh_return_output("python ./parse_script_params.py --params \"${params}\" --command ${command}")
          }
          echo "parsed script additional params ${parsed_params}"
          if (command == "export") {
            echo "Running upload script with export command"
            if (!params.contains("true,true,")){
                raise "User did not mark approval box, aborting export"
            }
          }
          script_params.add(parsed_params)
          script_params_str = script_params.join(' ')
          pythonpath = "PYTHONPATH=/root/mars/workspace/sonic-mgmt/:/devts/"
          python_int = "/ngts_venv/bin/python"
          script_cmd = "${pythonpath} ${python_int} ${script_path} ${script_params_str}"
          echo "script_cmd ${script_cmd}"
          docker_cmd = "sudo docker exec --env-file /tmp/${container_name}_env_file.sh ${container_name} bash -c \"cd /root/ && ${script_cmd}\""
          echo "docker_cmd ${docker_cmd}"
          NGCITools().ciTools.run_sh("${docker_cmd}")
          echo "Copy build table from docker"
          currentDir = new File(System.getProperty("user.dir")).parent
          echo "currentDir ${currentDir}"
          path = "${currentDir}/${build_table_name}"
          NGCITools().ciTools.run_sh("sudo docker cp ${container_name}:${script_dir}${build_table_name} ${path}")
          email_message(path)
          return true
      }
    catch (Throwable exc) {
        NGCITools().ciTools.set_error_in_env(exc, "user", name)
        return false
    }
}

def cleanup(name) {
    return true
}

def headline(name) {
    return "${name} " + env."${name}_status"
}

def summary(name) {
    if (env."${name}_status" != "Success") {
        return env."${name}_status" + " - exception: " + env."${name}_error"
    } else {
        return env."${name}_status"
    }
}

return this