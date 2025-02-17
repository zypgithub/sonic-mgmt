package com.mellanox.jenkins.generic_modules
import java.util.regex.Matcher
import java.util.regex.Pattern

def set_bat_skip(name, skip_list) {
    for (bat_to_skip in skip_list) {
        switch(bat_to_skip) {
            case "SPC_HW":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "ETH", "SPC", "Skipped=status")
                env.SKIP_SONIC_HW_SPC_BAT = "true"
                break
            case "SPC3_HW":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "ETH", "SPC3", "Skipped=status")
                env.SKIP_SONIC_HW_SPC3_BAT = "true"
                break
            case "SPC4_HW":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "ETH", "SPC4", "Skipped=status")
                env.SKIP_SONIC_HW_SPC4_BAT = "true"
                break
            case "SS_HW":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "SMARTSWITCH", "SPC3/BF3", "Skipped=status")
                env.SKIP_SONIC_HW_SS_BAT = "true"
                break
            case "SPC_SIMX":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "SIMX", "SPC", "Skipped=status")
                env.SKIP_SONIC_SIMX_SPC_BAT = "true"
                break
            case "SPC3_SIMX":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "SIMX", "SPC3", "Skipped=status")
                env.SKIP_SONIC_SIMX_SPC3_BAT = "true"
                break
            case "SPC4_SIMX":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "SIMX", "SPC4", "Skipped=status")
                env.SKIP_SONIC_SIMX_SPC4_BAT = "true"
                break
            case "QTM2":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "IB", "QTM2", "Skipped=status")
                env.SKIP_NVOS_BAT = "true"
                break
            case "ETH_COMMUNITY":
                NGCITools().ciTools.insert_test_result_to_matrix(name, "ETH_COMMUNITY", "SPC", "Skipped=status")
                env.SKIP_COMMUNITY_REGRESSION = "true"
                break
        }
    }
}

def pre(name) {
    return true
}


def run_step(name) {
    def SONIC_CANONICAL_HW_BAT = ["SPC_HW", "SPC3_HW", "SPC4_HW", "SS_HW"]
    def SONIC_CANONICAL_SIMX_BAT = ["SPC_SIMX", "SPC3_SIMX", "SPC4_SIMX"]
    def SONIC_CANONICAL_BAT = SONIC_CANONICAL_HW_BAT + SONIC_CANONICAL_SIMX_BAT
    def SONIC_COMMUNITY_BAT = ["ETH_COMMUNITY"]
    def NVOS_BAT = ["QTM2"]
    try {
        print "Component match = ${env.CHANGED_COMPONENTS}"
        if (env.RUN_COMMUNITY_REGRESSION && env.RUN_COMMUNITY_REGRESSION.toBoolean() == true &&  env.CHANGED_COMPONENTS && env.CHANGED_COMPONENTS.contains("NoMatch")) {
            print "Topic \"RUN_COMMUNITY_REGRESSION=true\" and changed files triggered community regression tests"
        } else {
            set_bat_skip(name, ["ETH_COMMUNITY"])
        }

        if (env.CHANGED_COMPONENTS && (!env.CHANGED_COMPONENTS.contains("NVOS_BAT_ONLY")
                && !env.CHANGED_COMPONENTS.contains("COMMON_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("NoMatch"))){
            print "'NVOS' BAT are skipped"
            set_bat_skip(name, NVOS_BAT)
        }

        if (env.CHANGED_COMPONENTS && (env.CHANGED_COMPONENTS.contains("SONIC_COMMUNITY_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("SONIC_BAT_ONLY")
                && !env.CHANGED_COMPONENTS.contains("COMMON_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("NoMatch"))){
            print "'SONIC Canonical' BAT are skipped"
            set_bat_skip(name, SONIC_CANONICAL_BAT)
        }

        //If only yaml changed, only run SONIC SIMX SPC BAT
        if (env.CHANGED_COMPONENTS && env.CHANGED_COMPONENTS.contains("COMMON_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("SONIC_BAT_ONLY")
                && !env.CHANGED_COMPONENTS.contains("NVOS_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("NoMatch")){
            print "Checking whether the changes are only in the error/skip yaml files."
            def yaml_patterns = [~/tests\/common\/plugins\/loganalyzer_dynamic_errors_ignore\/.*\.yaml/,
                                 ~/tests\/common\/plugins\/conditional_mark\/.*\.yaml/]
            def git_change = NGCITools().ciTools.run_sh_with_output("git diff-tree --no-commit-id --name-only -r HEAD").readLines()
            print git_change
            env.CHECK_YAML_ONLY = "true"
            for (def line in git_change){
                def no_match_yaml = "true"
                for (def pattern in yaml_patterns) {
                    if (pattern.matcher(line).matches()) {
                        no_match_yaml = "false"
                        break
                    }
                }
                if (no_match_yaml == "true") {
                    print "The change is not only in the test/error skip yaml files, set env.CHECK_YAML_ONLY to false"
                    env.CHECK_YAML_ONLY = "false"
                    break
                }
            }
            if (env.CHECK_YAML_ONLY == "true"){
                print "The changes are only in the error/skip yaml files, run only the yaml validation test on SPC SIMX."
                // Only run one SPC SIMX setup
                set_bat_skip(name, SONIC_CANONICAL_BAT + NVOS_BAT - "SPC_SIMX")
                env.SIMX_NONE_BLOCKER = "false"
            }
        }

        //If NVOS only, disable all sonic BAT
        if (env.CHANGED_COMPONENTS && (env.CHANGED_COMPONENTS.contains("NVOS_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("SONIC_BAT_ONLY")
                && !env.CHANGED_COMPONENTS.contains("COMMON_BAT_ONLY") && !env.CHANGED_COMPONENTS.contains("SONIC_COMMUNITY_BAT_ONLY")
                && !env.CHANGED_COMPONENTS.contains("NoMatch"))){
            print "'SONIC' BAT are skipped"
            set_bat_skip(name, SONIC_CANONICAL_BAT + SONIC_COMMUNITY_BAT)
        }

        if (env.GERRIT_BRANCH.startsWith("nvos_ver-")){
            print "NVOS developer branch, will skip SONiC BAT"
            set_bat_skip(name, SONIC_CANONICAL_BAT + SONIC_COMMUNITY_BAT)
        }
        if (env.GERRIT_BRANCH.startsWith("develop-")){
            print "SONiC developer branch, will skip NVOS BAT"
            set_bat_skip(name, NVOS_BAT)
        }

        return true
    }
    catch (Throwable exc) {
        NGCITools().ciTools.set_error_in_env(exc, "user", name)
        return false

    }
}


def post(name) {
    return true
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
