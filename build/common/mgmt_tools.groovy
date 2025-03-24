package com.mellanox.jenkins
import java.time.YearMonth
import java.util.regex.Pattern

/**
 * Extracts YearMonth from a branch name if it contains a valid date pattern
 * @param branchName The branch name that may contain a date
 * @return YearMonth object if valid date found, null otherwise
 */
YearMonth extractYearMonth(String branchName) {
    def match = Pattern.compile(".*(\\d{4})(\\d{2}).*").matcher(branchName);
    if (!match.matches()) return null;
    def year = Integer.parseInt(match.group(1));
    def month = Integer.parseInt(match.group(2));
    if (month < 1 || month > 12) return null;
    return YearMonth.of(year, month);
}

/**
 * Checks if a given branch name represents a date that is newer (or equal) 
 * compared to a specified comparison branch.
 *
 * @param comparisonBranch The reference branch in "YYYYMM" format (e.g., "202411").
 * @param branchName The branch name that may contain a date (e.g., "202412_rc").
 * @return true if branchName represents a branch that is newer or equal to comparisonBranch, false otherwise.
 */
boolean is_branch_newer_than(String comparisonBranch, String branchName) {
    def branchDate = extractYearMonth(branchName);
    if (branchDate == null) return false;
    
    def compareDate = extractYearMonth(comparisonBranch);
    if (compareDate == null) return false;
    
    return branchDate.isAfter(compareDate) || branchDate.equals(compareDate);
}

/**
 * Checks if a branch name contains a valid date pattern
 * @param branch The branch name to check
 * @param date The date to compare against (unused parameter kept for backward compatibility)
 * @return true if branch contains a valid date pattern, false otherwise
 */
boolean is_branch_matching_date(String branch) { 
    return extractYearMonth(branch) != null;
}

/**
 * Common function to get lastrc version for a given tool type
 * Branch Name Selection Logic:
 * - If branch name matches *YYYYMM* pattern and is newer or equal to compared_branch:
 *   Uses YYYYMM_RC; if that doesn't exist, falls back to master_RC (stability)
 * - If branch name matches *YYYYMM* pattern but is older than 202405:
 *   Uses LastRC of the branch's own RC version
 * - If branch name doesn't match any *YYYYMM* pattern:
 *   Uses master_RC (stability)
 * @param target_branch the target branch
 * @param tool_type the tool type ("sonic" or "dpu")
 * @param version_path the version path
 * @param parse_version_func the function to parse the version
 * @param compared_branch the branch to compare against
 * @return the lastrc version
 */
def get_lastrc_version_common(target_branch, tool_type, version_path, parse_version_func, compared_branch) {
    try {
        print "Getting lastrc ${tool_type.toUpperCase()} version"
        def lastrc_path
        // Check if the target branch is matching date pattern
        if (is_branch_matching_date(target_branch)) {

            // Check if the target branch is newer than the compared branch
            if (is_branch_newer_than(compared_branch, target_branch)) {
                echo "Target branch ${target_branch} is newer than ${compared_branch}"
                def match = Pattern.compile(".*(\\d{6}).*").matcher(target_branch)

                // Extract the year and month from the target branch
                def year_month = match.matches() ? match.group(1) : { error 'Error parsing year and month from branch name' }()
                def lastrc_rc = get_lastrc_path(year_month, "${tool_type}_yearmonth_RC", version_path)
                echo "lastrc_rc: ${lastrc_rc}"
                // Check if the lastrc path exists for the target branch, if not, use the stability lastrc path
                lastrc_path = fileExists(lastrc_rc) ? lastrc_rc : 
                    get_lastrc_path_with_validation(target_branch, "${tool_type}_stability", version_path)
            } else {
                if (tool_type == "dpu") {
                    echo "Branch ${target_branch} is older than ${compared_branch}, So DPU should not be used"
                    return null
                }
                echo "Branch ${target_branch} is older than ${compared_branch}, taking own RC"
                lastrc_path = get_lastrc_path_with_validation(target_branch, "${tool_type}_own_RC", version_path)
            }
        } else {
            // If the target branch is not matching date pattern, use the stability lastrc path
            echo "Branch ${target_branch} is not matching date pattern using default lastrc master_RC"  
            lastrc_path = get_lastrc_path_with_validation(target_branch, "${tool_type}_stability", version_path)
        }
        def lastrc_link = NGCITools().ciTools.run_sh_return_output("readlink ${lastrc_path}")
        def lastrc_version = parse_version_func(lastrc_link, version_path)
        print "CI will use branch: ${target_branch} lastrc version: ${lastrc_version} for running BAT"
        return lastrc_version
    } catch (Throwable lastrc_ex) {
        echo "Error getting lastrc version: ${lastrc_ex}"
        echo "No lastrc soft link is available for branch ${target_branch} (${tool_type.toUpperCase()})."
        return null
    }
}

/**
 * Get the lastrc version for the SONIC
 * @param target_branch the target branch
 * @return the lastrc version
 */
def get_sonic_lastrc_version(target_branch) {
    return get_lastrc_version_common(target_branch, "sonic", env.VERSION_DIRECTORY, this.&parse_sonic_lastrc_version, "202405")
}

/**
 * Get the lastrc version for the DPU
 * @param target_branch the target branch
 * @return the lastrc version
 */
def get_dpu_lastrc_version(target_branch) {
    return get_lastrc_version_common(target_branch, "dpu", env.DPU_VERSION_DIRECTORY, this.&parse_dpu_lastrc_version, "202505")
}

/**
 * Get the lastrc version for the NVOS
 * @param target_branch the target branch
 * @return the lastrc version
 */
def get_nvos_lastrc_version(target_branch) {
    //Check for lastrc
    try {
        print "Getting lastrc NVOS version"
        def version_path = env.NVOS_VERSION_DIRECTORY
        def lastrc = NGCITools().ciTools.run_sh_return_output("readlink ${version_path}/lastrc_${target_branch}")
        def lastrc_version = lastrc.replace("${version_path}", "").replace("/dev/","/").replace("/amd64/", "").replace("/", "")
        print "CI will use branch:${target_branch} lastrc version: ${lastrc_version} for running BAT"
        return lastrc_version
    } catch (Throwable lastrc_ex) {
        //Handle non exist links
        error "No lastrc soft link is available for branch ${target_branch}. please contact DevOps for more help"
    }
}


/**
 * Parse the lastrc version from the lastrc path
 * @param lastrc the lastrc path
 * @param version_path the version path
 * @return the lastrc version
 */
def parse_sonic_lastrc_version(lastrc, version_path) {
    if (lastrc.contains("_Public")) {
        version_path = version_path  + "/public"
    }
    def lastrc_version = lastrc.replace("${version_path}", "").replace("/dev/","/").replace("/Mellanox/sonic-mellanox.bin", "").replace("/", "")
    return lastrc_version
}

/**
 * Parse the lastrc version for the DPU
 * @param lastrc the lastrc path
 * @param version_path the version path
 * @return the lastrc version
 */
def parse_dpu_lastrc_version(lastrc, version_path) {
    def lastrc_version = lastrc.replace("${version_path}", "").replace("/dev/","/").replace("/Nvidia-bluefield/sonic-nvidia-bluefield.bfb", "").replace("/", "")
    return lastrc_version
}

/**
 * Get the lastrc path for the target branch
 * @param branch the target branch
 * @param tool_type the tool type ("sonic" or "dpu")
 * @param version_path the version path
 * @return the lastrc path
 */
def get_lastrc_path(branch, tool_type, version_path) {
    def lastrc_path = "${version_path}/${get_stability_filename(branch, tool_type)}"
    return lastrc_path
}

/**
 * Get the lastrc path with validation
 * @param branch the branch name
 * @param tool_type the tool type ("sonic" or "dpu")
 * @param version_path the version path
 * @return the lastrc path
 */
def get_lastrc_path_with_validation(branch, tool_type, version_path) {
    def lastrc_path = get_lastrc_path(branch, tool_type, version_path)
    echo "Check if lastrc path exists: ${lastrc_path}"
    if (!fileExists(lastrc_path)) {
        error "No lastrc soft link is available for branch ${branch}."
    }
    echo "Found lastrc path: ${lastrc_path}"
    return lastrc_path
}

/**
 * Get stability lastrc filename based on the branch.
 * @param branch the branch name
 * @param tool_type the tool type ("sonic" or "dpu")
 * @return the stability lastrc filename
 */
def get_stability_filename(branch, tool_type) {
    def stability_filenames = [
        "sonic_stability"           : "master_RC-lastrc-internal-stability-sonic-mellanox.bin",
        "dpu_stability"             : "master_RC-lastrc-internal-stability-sonic-nvidia-bluefield.bfb",
        "sonic_yearmonth_RC"        : "${branch}_RC-lastrc-internal-sonic-mellanox.bin",
        "dpu_yearmonth_RC"          : "${branch}_RC-lastrc-internal-sonic-nvidia-bluefield.bfb",
        "sonic_own_RC"              : "${branch}-lastrc-internal-sonic-mellanox.bin",
        "dpu_own_RC"                : "${branch}-lastrc-internal-sonic-nvidia-bluefield.bfb"              
    ]
    return stability_filenames.get(tool_type.trim()) ?: error("Unknown device type: ${tool_type}. Supported types: ${stability_filenames.keySet()}")
}
return this
