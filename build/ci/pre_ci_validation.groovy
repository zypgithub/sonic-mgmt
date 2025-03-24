package vars

def pre(name) {
    return true
}

def set_dpu_bin(topic_map) {
    def DPU_bin_path
    if (topic_map["IMAGE_DPU_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_DPU_BRANCH"]) &&
            topic_map["IMAGE_DPU_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_DPU_VERSION"])) {
        error "IMAGE_BRANCH and IMAGE_VERSION cannot be defined together. remove one or both of them from Gerrit topic to continue "
    }

    def dpu_branch = env.GERRIT_BRANCH ? env.GERRIT_BRANCH : "smart-switch-master"
    if (topic_map["IMAGE_DPU_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_DPU_BRANCH"])) {
        dpu_branch = topic_map["IMAGE_DPU_BRANCH"]
        print "DPU image branch name is defined by topic: ${dpu_branch}"
    }

    def dpu_version_name
    if (topic_map["IMAGE_DPU_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_DPU_VERSION"])) {
        dpu_version_name = topic_map["IMAGE_DPU_VERSION"]
        print "DPU image version is defined by topic \"IMAGE_DPU_VERSION\"."
    } else {
        def mgmt_tools = NGCITools().ciTools.load_project_lib("${env.SHARED_LIB_FILE}")
        dpu_version_name = mgmt_tools.get_dpu_lastrc_version(dpu_branch)

        // This part should throw exception in the future and align with SONIC case.
        // It was decided to skip DPU tests if the lastrc version is not defined or found
        // We will do it when dpu lastrc methodology will be aligned with sonic
        if (dpu_version_name == null) {
            echo "DPU image version is not defined by lastrc link for branch: ${dpu_branch}, in that case will skip DPU tests"
            echo "Setting SKIP_SONIC_HW_SS_BAT to true"
            env.SKIP_SONIC_HW_SS_BAT = true
            DPU_bin_path = "Not Defined"
        }
    }
    // In the future we should throw exception if DPU_bin_path is not defined and remove this if
    if (DPU_bin_path != "Not Defined") {
        DPU_bin_path = "${env.DPU_VERSION_DIRECTORY}/${dpu_version_name}/dev/Nvidia-bluefield/sonic-nvidia-bluefield.bfb"
        if (! new File(DPU_bin_path).exists()) {
            error "ERROR:SONiC bin file not found: ${DPU_bin_path}"
        }
    }
    env.DPU_BIN = DPU_bin_path
    print "DPU_BIN = ${env.DPU_BIN}"
}

def set_sonic_bin(topic_map, project) {
    if (topic_map["IMAGE_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_BRANCH"]) &&
            topic_map["IMAGE_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_VERSION"])) {
        error "IMAGE_BRANCH and IMAGE_VERSION cannot be defined together. remove one or both of them from Gerrit topic to continue "
    }

    def sonic_branch = env.GERRIT_BRANCH ? env.GERRIT_BRANCH : "master"
    if (topic_map["IMAGE_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_BRANCH"])) {
        sonic_branch = topic_map["IMAGE_BRANCH"]
        print "SONiC image branch name is defined by topic: ${sonic_branch}"
    }

    def sonic_version_name
    if (topic_map["IMAGE_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_VERSION"])) {
        sonic_version_name = topic_map["IMAGE_VERSION"]
        print "SONiC image version  is defined by topic \"IMAGE_VERSION\"."
    } else {
        def mgmt_tools = NGCITools().ciTools.load_project_lib("${env.SHARED_LIB_FILE}")
        sonic_version_name = mgmt_tools.get_sonic_lastrc_version(sonic_branch)
        print "SONiC image version is defined by lastrc link for branch: ${sonic_branch}"
        if (sonic_version_name == null) {
            error "ERROR: SONiC image version is not defined by lastrc link for branch: ${sonic_branch}"
        }
    }

    if (sonic_version_name.contains("_Public")) {
        env.VERSION_DIRECTORY = env.VERSION_DIRECTORY + "/public"
    }

    def sonic_bin_path = "${env.VERSION_DIRECTORY}/${sonic_version_name}/dev/Mellanox/sonic-mellanox.bin"
    env.README_PATH = "${env.VERSION_DIRECTORY}/${sonic_version_name}/dev"
    if (! new File(sonic_bin_path).exists()) {
        print "SONiC bin file not found: ${sonic_bin_path}\nWill try the old conventsion (without 'dev' folder)"
        sonic_bin_path = sonic_bin_path.replace("/dev/","/")
        env.README_PATH = "${env.VERSION_DIRECTORY}/${sonic_version_name}"
        if (! new File(sonic_bin_path).exists()) {
            error "ERROR:SONiC bin file not found: ${sonic_bin_path}"
        }
    }

    env.SONIC_BIN = sonic_bin_path
    print "SONIC_BIN = ${env.SONIC_BIN}"
}

def set_nvos_bin(topic_map, project){
    if (topic_map["IMAGE_NVOS_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_NVOS_BRANCH"]) &&
            topic_map["IMAGE_NVOS_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_NVOS_VERSION"])) {
        error "IMAGE_NVOS_BRANCH and IMAGE_NVOS_VERSION cannot be defined together. remove one or both of them from Gerrit topic to continue "
    }

    def nvos_branch = env.DEFAULT_NVOS_BRANCH ? env.DEFAULT_NVOS_BRANCH : "master"
    if (topic_map["IMAGE_NVOS_BRANCH"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_NVOS_BRANCH"])) {
        nvos_branch = topic_map["IMAGE_NVOS_BRANCH"]
        print "NVOS image branch name is defined by topic: ${nvos_branch}"
    } else if (project == "nvos") {
        if (env.GERRIT_BRANCH && NGCITools().ciTools.is_parameter_contains_value(env.GERRIT_BRANCH)) {
            nvos_branch = env.GERRIT_BRANCH.replace("dev_ver", "dev").replace("nvos_ver", "nvos")
            print "NVOS image branch name branch name: ${nvos_branch}"
        }
    }

    def nvos_version_name
    if (topic_map["IMAGE_NVOS_VERSION"] && NGCITools().ciTools.is_parameter_contains_value(topic_map["IMAGE_NVOS_VERSION"])) {
        nvos_version_name = topic_map["IMAGE_NVOS_VERSION"]
        print "NVOS image version  is defined by topic \"IMAGE_VERSION\"."
    } else {
        def mgmt_tools = NGCITools().ciTools.load_project_lib("${env.SHARED_LIB_FILE}")
        nvos_version_name =  mgmt_tools.get_nvos_lastrc_version(nvos_branch)
        print "NVOS image version is defined by lastrc link for branch: ${nvos_branch}"
    }

    def nvos_bin_path = "${env.NVOS_VERSION_DIRECTORY}/${nvos_version_name}/amd64/dev/nvos-amd64-${nvos_version_name}.bin"
    if (! new File(nvos_bin_path).exists()) {
        print "NVOS bin file not found: ${nvos_bin_path}\nWill try the old conventsion (without 'dev' folder)"
        nvos_bin_path = nvos_bin_path.replace("/dev/","/")
        if (! new File(nvos_bin_path).exists()) {
            error "ERROR: NVOS bin file not found: ${nvos_bin_path}"
        }
    }

    env.NVOS_BIN = nvos_bin_path
    print "NVOS_BIN = ${env.NVOS_BIN}"
}

def run_step(name) {
    try {
        def topic = (GerritTools.get_topic(env.GERRIT_CHANGE_NUMBER)).replace("\"","")
        def topic_map = [:]
        for (_topic in topic.split(",")) {
            if (_topic.contains("=")) {
                topic_map[_topic.split("=")[0].trim()] = _topic.split("=", 2)[1].trim().replace("\"","")
            }
        }

        def project = "sonic"
        if (env.GERRIT_BRANCH.startsWith("dev-") || env.GERRIT_BRANCH.startsWith("dev_") ||env.GERRIT_BRANCH.startsWith("nvos")){
            project = "nvos"
        }
        if (topic_map["RUN_COMMUNITY_REGRESSION"] && topic_map["RUN_COMMUNITY_REGRESSION"].toBoolean() == true) {
            env.RUN_COMMUNITY_REGRESSION = true
        }

        if (topic.contains("SKIP_SPELLCHECK")){
            print "SKIP_SPELLCHECK is activated, spell check will not run"
            env.SKIP_SPELLCHECK = true
        }

        if (topic.contains("SKIP_BEAUTIFIER")){
            print "SKIP_BEAUTIFIER is activated, spell check will not run"
            env.SKIP_BEAUTIFIER = true
        }

        set_sonic_bin(topic_map, project)
        set_dpu_bin(topic_map)
        set_nvos_bin(topic_map, project)


        //Copy files to external storage
        env.nfs_dir = "/auto/sw_system_project/devops/sw-r2d2-bot/${env.JOB_NAME}/${currentBuild.number}"

        //copy build moduls dir
        if (!fileExists(env.nfs_dir + "/build")) {
            NGCITools().ciTools.run_sh("mkdir -p ${env.nfs_dir}/build/ci")
            NGCITools().ciTools.run_sh("mkdir -p ${env.nfs_dir}/sonic-mgmt")
            NGCITools().ciTools.run_sh("chmod -R 777 ${env.nfs_dir}")
            NGCITools().ciTools.run_sh("mkdir -p ${env.nfs_dir}/LOGS")
            NGCITools().ciTools.run_sh("chmod 777 ${env.nfs_dir}/LOGS")
            print "copying mgmt repo files to " + env."nfs_dir"
            NGCITools().ciTools.run_sh("cp -rf ./. ${env.nfs_dir}/sonic-mgmt/")
            NGCITools().ciTools.run_sh("cp -r build/. ${env.nfs_dir}/build/")
            //Copy bat properties from sonic_devops shared location (used by bat.groovy)
            NGCITools().ciTools.run_sh("cp /auto/sw_system_release/ci/sonic_devops/build/ci/bat_properties_file.txt ${env.nfs_dir}/build/ci/")
            NGCITools().ciTools.run_sh("cp /auto/sw_system_release/ci/nos/nvos/build/common/bat_properties_file.txt ${env.nfs_dir}/build/common/")
        }

        //copy sonic_devops build
        NGCITools().ciTools.run_sh("mkdir -p ${env.nfs_dir}/sonic_devops/build")
        NGCITools().ciTools.run_sh("chmod 777 ${env.nfs_dir}/sonic_devops/build")

        def common_properties_file_path = "/auto/sw_system_release/ci/sonic_devops/build/common/build.properties"
        def mars_property = "MARS_RELEASE_VERSION"
        def parameters = readFile(common_properties_file_path)
        def props = new Properties()
        props.load(new StringReader(parameters))
        print "Reading '${mars_property}' from: '${common_properties_file_path}'"
        env.MARS_RELEASE_VERSION = props.getProperty(mars_property)
        print("MARS_RELEASE_VERSION = ${env.MARS_RELEASE_VERSION}")


    } catch (Throwable ex) {
        NGCITools().ciTools.set_error_in_env(ex, "devops", name)
        return false
    }
    return true
}


def cleanup(name) {
    return true
}

def headline(name) {
    if ("${name}".contains(":")) {
        return "${name}".split(":")[0] + " " + env."${name}_status"
    } else {
        return "${name} " + env."${name}_status"
    }
}


def summary(name) {
    if (env."${name}_status" != "Success") {
        return env."${name}_status" + " - exception: " + env."${name}_error"
    } else {
        return env."${name}_status"
    }
}


return this
