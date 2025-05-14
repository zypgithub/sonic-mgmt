import json
import sys
import statistics
from typing import Dict, Any
import subprocess

RUN_PERFORMANCE_TEST_SCRIPT = "/root/mars/workspace/sonic-mgmt/ngts/scripts/nv_optimizer/run_performance_test.sh"
RESULTS_FILE = "/root/mars/workspace/sonic-mgmt/ngts/performance_tests/nv_optimizer/results.txt"
SETUP_PARAMS_FILE = "/root/mars/workspace/sonic-mgmt/ngts/performance_tests/nv_optimizer/setup_params.json"


def compute_score(test_results: Dict[str, Any]) -> float:
    """
    Compute the score for the test results.
    The score is the average of the mean rx/tx rates minus the average of the mean occ/occ99 rates.
    """

    mean_rx, mean_tx = get_bw_mean(test_results)
    mean_occ_avg, mean_occ_99s = get_occ_mean(test_results)

    reward = (mean_rx + mean_tx) / 2 - (mean_occ_avg + mean_occ_99s) / 2 / 1000

    return reward


def main(args):
    with open(SETUP_PARAMS_FILE, 'r') as f:
        params = json.load(f)

    if args == 'init':
        initialize_tests(params['test_name'], params['setup_name'])
    elif args == 'cleanup':
        cleanup_tests(params['test_name'], params['setup_name'])
    else:
        try:
            parameter_set = json.loads(args)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format: {args}")
        run_test_and_return_reward(parameter_set, params)


def get_bw_mean(test_results):
    rx_rates = []
    tx_rates = []
    sample_keys = [k for k in test_results['Bandwidth_samples'].keys() if k.startswith('sample #')]

    for key in sample_keys:
        sample_data = test_results['Bandwidth_samples'][key]
        # Calculate mean rates across all ports for this sample
        sample_rx_rates = [port['rxRate'] for port in sample_data['bandwidth_dataframe']]
        sample_tx_rates = [port['txRate'] for port in sample_data['bandwidth_dataframe']]

        rx_rates.append(statistics.mean(sample_rx_rates))
        tx_rates.append(statistics.mean(sample_tx_rates))

    mean_rx = statistics.mean(rx_rates)
    mean_tx = statistics.mean(tx_rates)
    return mean_rx, mean_tx


def get_occ_mean(test_results):
    occ_avgs = []
    occ_99s = []
    sample_keys = [k for k in test_results['TC_samples'].keys() if k.startswith('sample #')]

    for key in sample_keys:
        sample_data = test_results['TC_samples'][key]
        occ_avg = [port['occAvg'] for port in sample_data['tc_dataframe']]
        occ_99 = [port['occ99'] for port in sample_data['tc_dataframe']]

        occ_avgs.append(statistics.mean(occ_avg))
        occ_99s.append(statistics.mean(occ_99))

    mean_occ_avg = statistics.mean(occ_avgs)
    mean_occ_99s = statistics.mean(occ_99s)
    return mean_occ_avg, mean_occ_99s


def run_test_and_return_reward(parameter_set, params):
    params['parameter_set'] = parameter_set
    test_results = run_tests(params['parameter_set'], params['test_name'], params['setup_name'], params['parameter_file_location'])
    reward = compute_score(test_results)
    output_json = {'measurement': reward}
    print(json.dumps(output_json))


def run_tests(parameter_set: Dict[str, Any], test_name: str, setup_name: str, parameter_file_location: str) -> Dict[str, Any]:
    """Example: "params": {
        "low_ar_thresh": 400,
        "med_ar_thresh": 800,
        "high_ar_thresh": 1200,
        "sib": 414,
        "tc_reserved_KB": 1,
        "tc_alpha_power": 1}
    """

    # Save the parameter set to the parameter file location
    with open(parameter_file_location, 'w') as f:
        json.dump(parameter_set, f)

    subprocess.run([RUN_PERFORMANCE_TEST_SCRIPT,
                   f"--setup_name={setup_name}",
                   f"--test_name={test_name}",
                   f"--parameter_file_location={parameter_file_location}"])

    # Read results from the results file
    try:
        with open(RESULTS_FILE, "r") as f:
            results = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise Exception(f"Error reading results file: {e}")
    return results


def initialize_tests(test_name: str, setup_name: str) -> None:
    print("initialize tests")
    rc = subprocess.run([RUN_PERFORMANCE_TEST_SCRIPT,
                         f"--setup_name={setup_name}",
                         f"--test_name={test_name}",
                         "--init"])
    return rc.returncode


def cleanup_tests(test_name: str, setup_name: str) -> None:
    print("cleanup tests")
    rc = subprocess.run([RUN_PERFORMANCE_TEST_SCRIPT,
                         f"--setup_name={setup_name}",
                         f"--test_name={test_name}",
                         "--cleanup"])
    return rc.returncode


if __name__ == "__main__":
    """
    Example usage:
    python switch_perf.py '{"parameter_set": {"low_ar_thresh": 400,"med_ar_thresh": 800,"high_ar_thresh": 1200,"sib": 414,"tc_reserved_KB": 1,"tc_alpha_power": 1}}'
    """
    main(sys.argv[1])
