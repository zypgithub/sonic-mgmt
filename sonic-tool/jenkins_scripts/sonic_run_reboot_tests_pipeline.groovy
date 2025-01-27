SESSION_IDS = [:]


def get_vault_creds() {
    def vault_config = [vaultUrl: 'https://prod.vault.nvidia.com',
    vaultNamespace: "nbu-system-sw-sonic",
    vaultCredentialId: 'vault-sonic-approle-prod',
    engineVersion: 1]
    def vault_path_prefix = "nvidia/nbu/mars/sonic/kv"
    def secrets = [
        [path: "${vault_path_prefix}/stm_server",
        engineVersion: 1,
        secretValues: [[envVar: 'STM_USER', vaultKey: 'user'],
        [envVar: 'STM_PASSWORD', vaultKey: 'password']]],
        [path: "${vault_path_prefix}/sonic_server",
        engineVersion: 1,
        secretValues: [[envVar: 'SONIC_SERVER_USER', vaultKey: 'user'],
        [envVar: 'SONIC_SERVER_PASSWORD', vaultKey: 'password']]]
    ]

    return [vault_config, secrets]
}


def get_SetupNameRebootTypeMap(setup_name) {

    reboot_types = []

    if (env.fast_reboot_executors.trim()) {
        fast_reboot_executors = env.fast_reboot_executors.split(',')
        if (fast_reboot_executors.contains(setup_name)) {
            reboot_types.add("fast")
        }
    }

    if (env.warm_reboot_executors.trim()) {
        warm_reboot_executors = env.warm_reboot_executors.split(',')
        if (warm_reboot_executors.contains(setup_name)) {
            reboot_types.add("warm")
        }
    }

    return reboot_types
}


def getSetupNames(){

    setup_names = []

    if (env.fast_reboot_executors.trim()) {
        fast_reboot_executors = env.fast_reboot_executors.split(',')
	    fast_reboot_executors.each{ value ->
            setup_names.add(value)
		}
    }

    if (env.warm_reboot_executors.trim()) {
        warm_reboot_executors = env.warm_reboot_executors.split(',')
        warm_reboot_executors.each{ value ->
            if (value in setup_names) {
                echo "Already exist"
            } else {
                 setup_names.add(value)
            }
        }
    }
    return setup_names
}


def cloneRepoAndCheckoutBranch() {
    // Clone sonic-mgmt repo and checkout into branch
    sh "rm -rf ./*"
    sh 'git clone "http://10.7.77.140:8080/switchx/sonic/sonic-mgmt"'
    sh "cd sonic-mgmt && git checkout ${env.sonic_mgmt_branch}"
    sh "cd sonic-mgmt && git branch"
}


def prepareSonicMgmtTarball() {
    // Create sonic-mgmt tarball
    sh 'tar -czvf jenkins_reboot_tests_runner.db.1.tgz sonic-mgmt/'
    sh 'cp jenkins_reboot_tests_runner.db.1.tgz /.autodirect/sw_regression/system/SONIC/MARS/tarballs/'
    sh 'chmod 777 /.autodirect/sw_regression/system/SONIC/MARS/tarballs/jenkins_reboot_tests_runner.db.1.tgz'
    // Copy tarball to MTBC location to allow MTBC setups to be able to run reboot tests
    sh 'cp jenkins_reboot_tests_runner.db.1.tgz /.autodirect/sw_regression/mtbcsw/system/SONIC/MARS/tarballs/'
    sh 'chmod 777 /.autodirect/sw_regression/mtbcsw/system/SONIC/MARS/tarballs/jenkins_reboot_tests_runner.db.1.tgz'
}


def runTestForSetup(setup_name){
    // Run tests for specific setup
    reboot_types = get_SetupNameRebootTypeMap(setup_name)

    base_versions_list = env.base_version
    target_version = env.target_version

    if (reboot_types.size() == 2) {
        exec_block_gen_arg = "--meinfo_execution_block_generator=\\\"[{'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/fast_reboot.db'}, {'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/warm_reboot.db'}]\\\""
    } else {
        reboot_types.each{ value ->
            db_file_name = "${value}_reboot.db"
            exec_block_gen_arg = "--meinfo_execution_block_generator=\\\"[{'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/${db_file_name}'}]\\\""
        }
    }

    // Convert setup name to .setup file name
    setup_file_name = setup_name.replace("_setup", ".setup")

    mars_setup_cli_path = "/.autodirect/sw_tools/Internal/MARS/mars_apps/RELEASE/4_2_1/bin/setup_cli.py"
    tarball_arg = "--meinfo_custom_tarball_name jenkins_reboot_tests_runner.db.1.tgz"

    // If no target ver - base_ver = target ver
    if (target_version.trim()) {
        echo "Target version is provided, will be executed test with an upgrade"
    } else {
        echo "Target version is not provided, the test will be executed without the upgrade"
        target_version = base_versions_list
    }

    base_ver_arg = "--meinfo_base_version ${target_version}"

    stm_cmd = "${mars_setup_cli_path} --cmd start --setup ${setup_name} --conf ${setup_file_name} ${tarball_arg} ${base_ver_arg} ${exec_block_gen_arg}"
    echo "Running CMD on STM: ${stm_cmd}"


    // Redirect STDERR to STDOUT to have them together in the same stream
    local_cmd = "sshpass -p ${env.STM_PASSWORD} ssh ${env.STM_USER}@mtr-stm-095 -o StrictHostKeyChecking=no \" ${stm_cmd} \" 2>&1"
    echo "Running CMD locally: ${local_cmd}"

    try {
        result = sh (script: local_cmd, returnStdout: true)
        // Get -2 the end element from output(it's always MARS session ID)
        session_id = result.tokenize()[-2]
        echo "Have session ID ${session_id}"
        run_failed = false
    } catch (Throwable exc) {
        run_failed = true
        echo "Failed to run MARS session"
    } finally {
        if (!run_failed) {
            // Add session ID to shared dict - later use it for collect report
            SESSION_IDS[setup_name] = session_id
        }
    }
}


def collectTestResults() {
    // Collect tests results
    echo "Collecting tests results for session IDs data: ${SESSION_IDS}"
    def (vault_config, secrets) = get_vault_creds()
    withVault([configuration: vault_config, vaultSecrets: secrets]) {
        SESSION_IDS.each{setup_name, session_id ->
            echo "Collecting results from setup: ${setup_name} session id: ${session_id}"
            sh "/ngts_venv/bin/python sonic-mgmt/sonic-tool/jenkins_scripts/sonic_run_reboot_tests_pipeline.py --session_id ${session_id} --setup_name ${setup_name}"
        }
    }
}


pipeline {

    agent {
        docker { image 'nbu-harbor.gtm.nvidia.com/sonic/docker-ngts:1.2.198'
                 args '--entrypoint="" -v /.autodirect/sw_regression/system/SONIC/MARS/tarballs:/.autodirect/sw_regression/system/SONIC/MARS/tarballs/ -v /.autodirect/sw_regression/mtbcsw/system/SONIC/MARS/tarballs:/.autodirect/sw_regression/mtbcsw/system/SONIC/MARS/tarballs/ '
            }
        }

    stages {
        stage('Preparation') {
            steps {
                cloneRepoAndCheckoutBranch()
                // Prepare .cases and .db files
                sh "/ngts_venv/bin/python sonic-mgmt/sonic-tool/jenkins_scripts/sonic_run_reboot_tests_pipeline.py --do_preparation"
                prepareSonicMgmtTarball()
            }
        }
        stage('Tests execution') {
                steps {
            script {
                parallel getSetupNames().collectEntries { name ->
                    ["Execution ${name}": {
                        // Following code will be executed in parallel for each chosen setup
                        stage(name) {
                            def (vault_config, secrets) = get_vault_creds()
                            withVault([configuration: vault_config, vaultSecrets: secrets]) {
                                runTestForSetup(name)
                            }
                        }
                    }]
                }
            }
        }
        }
        stage('Collect results') {
            steps {
                collectTestResults()
            }
        }
    }
 post {
        always {
            sh "/ngts_venv/bin/python sonic-mgmt/sonic-tool/jenkins_scripts/sonic_run_reboot_tests_pipeline.py --generate_report_email"
            emailext body: '${FILE,path="email_report.html"}',
                    to: "nbu-system-sw-sonic-ver@exchange.nvidia.com",
                    subject: '$PROJECT_NAME #$BUILD_NUMBER results'
        }
    }
}