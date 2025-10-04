#!/usr/bin/env python3
"""
Script to create a bug ticket from JSON input file.
"""
import os
import sys
import json
import yaml
import subprocess
from datetime import datetime
from pathlib import Path
import argparse
import base64
from rm_via_post import RedMineAccess
import re
import shutil
import random

TITLE_PLACEHOLDER = "[Functional / Non-Functional ] [optional: &quot;Keyword&quot;] | user symptoms"
USER_INPUT_REQUIRED = "???"
SWITCH_COMPONENT_ID = 337
VALID_DUMP_FOLDER = 'valid_dump_for_rm_api'
CONN_CFG = {
    'api_key': '376bbab7be51101c4da0cbb239e094ddc3821ee6',
    'user': 'X-Redmine-Switch-User:',
    'priority': 6
}


def load_bug_data_from_json(json_file):
    """Load bug data from JSON file"""
    try:
        with open(json_file, 'r') as f:
            bug_data = json.load(f)
        return bug_data
    except FileNotFoundError:
        print(f"❌ Error: JSON file not found: {json_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON format: {e}")
        sys.exit(1)


def extract_testbed_topology(pytest_cmd_args, setup_name):
    testbed_match = re.search(r'--testbed\s+(\S+)', pytest_cmd_args)
    if not testbed_match:
        return ""
    testbed_full_name = testbed_match.group(1)
    if testbed_full_name.startswith(setup_name + '-'):
        testbed_topology = testbed_full_name[len(setup_name) + 1:]
        return testbed_topology
    else:
        return testbed_full_name
    return ""


def extract_attachments(attachments):
    extracted_attachments = []
    for attachment in attachments:
        if os.path.exists(attachment):
            extracted_attachments.append(attachment)
        else:
            if '/cases_dumps' in attachment:
                session_dir_full_path, dump_relative_path = attachment.split('/cases_dumps', 1)
                session_id = os.path.basename(session_dir_full_path)
                compressed_dumps_file_path = os.path.join(session_dir_full_path, session_id + '.tgz')
                extracted_path = extract_files(session_dir_full_path, compressed_dumps_file_path, 'cases_dumps', os.path.basename(dump_relative_path))
                if extracted_path:
                    extracted_attachments.append(extracted_path)
    valid_attachments = validate_attachments_for_rm_api(extracted_attachments)
    return valid_attachments


def extract_files(session_dir_full_path, compressed_dumps_file_path, target_directory, target_file):
    try:
        subprocess.run(["tar", "-xzf", compressed_dumps_file_path, "-C", session_dir_full_path, target_directory], check=True)
        target_path = f"{session_dir_full_path}/{target_directory}/{target_file}"
        return target_path
    except Exception as e:
        return None


def validate_attachments_for_rm_api(attachments):
    """
    RM api has an issue when in the attachment path there is characters as [, ].
    This function will copy the attachments to a target directory and replace the these characters.
    """
    validated_attachments = []
    target_dir = session_valid_dump_for_rm_api_folder
    os.makedirs(target_dir, exist_ok=True)

    for attachment in attachments:
        original_filename = os.path.basename(attachment)
        cleaned_filename = original_filename.replace('[', '-').replace(']', '')
        cleaned_attachment_path = os.path.join(target_dir, cleaned_filename)
        try:
            shutil.copy2(attachment, cleaned_attachment_path)
            validated_attachments.append(cleaned_attachment_path)
        except Exception as e:
            print(f"Warning: Failed to copy {attachment} to {cleaned_attachment_path}: {e}")
    return validated_attachments


def create_data_for_rm_api(bug_data):
    data_for_rm_api = {}
    data_for_rm_api['bug_manager_id'] = bug_data['project']
    data_for_rm_api["title"] = bug_data.get('bug_title') if bug_data.get('bug_title') else TITLE_PLACEHOLDER
    data_for_rm_api["version"] = bug_data.get('detected_in_version', "detected in version..")
    data_for_rm_api["description"] = create_description_for_rm(bug_data)
    data_for_rm_api["show_stopper"] = bug_data['show_stopper']
    data_for_rm_api["degradation"] = bug_data['is_degradation']
    data_for_rm_api["component_id"] = SWITCH_COMPONENT_ID
    data_for_rm_api["author"] = bug_data['bug_author']
    data_for_rm_api["attachments"] = extract_attachments(bug_data.get('dump_files', []))
    return data_for_rm_api


def create_description_for_rm(bug_data):
    attachments = bug_data.get('dump_files', ["not available"])[0]
    report_url = bug_data['report_url']
    setup_name = bug_data.get('setup_name', USER_INPUT_REQUIRED)
    pytest_cmd_args = bug_data.get('pytest_cmd_args', USER_INPUT_REQUIRED)
    test_description = bug_data['description']
    testbed_topology = extract_testbed_topology(pytest_cmd_args, setup_name)
    hwsku = bug_data.get('hw_sku', USER_INPUT_REQUIRED)
    description = [
        "<p><ins><strong>Issue description</strong></ins></p>",
        "<p>{test_description}</p>",
        "<br/>",
        "<ul>",
        "<li><strong>The test case is: <span style=\"background-color:#2ecc71\">automated</span></strong></li>",
        "\t<li><strong>Duplicate Check: confirmed/unconfirmed</strong></li>",
        "\t<li><strong>Is this a new test? <span style=\"background-color:#2ecc71\">No</span></strong></li>",
        "\t<li><strong>How long it takes to reproduce the issue? <span style=\"background-color:#2ecc71\">???</span></strong></li>",
        "\t<li><strong>How often the issue is reproduced and what probability? <span style=\"background-color:#2ecc71\">???</span></strong></li>",
        "\t<li><strong>Is this a degradation(based on test result)? <span style=\"background-color:#2ecc71\">???</span></strong></li>",
        "\t<li><strong>Is this a new flow or an existing flow that was changed recently: <span style=\"background-color:#2ecc71\">Existing</span></strong></li>",
        "\t<li><strong>Root cause (if already detected): </strong></li>",
        "\t<li><strong>Test log(path/url):</strong> <a href=\"{report_url}\"><strong>allure report</strong></a></li>",
        "</ul>",
        "<p><ins><strong>Setup description</strong></ins></p>",
        "<ul>",
        "\t<li><strong>Testbed name: <span style=\"background-color:#2ecc71\">{setup_name}</span></strong></li>",
        "\t<li><strong>Testbed topology: <span style=\"background-color:#2ecc71\">topology: {testbed_topology}, hwsku: {hwsku}</span></strong></li>",
        "\t<li><strong>Which traffic runs on the setup:</strong></li>",
        "\t<li><strong>Topology diagram (optional):</strong></li>",
        "</ul>",
        "<p><ins><strong>Steps to reproduce</strong></ins></p>",
        "<ul>",
        "\t<li><strong>Run the test with the following command:</strong></li>\n\t</ul>\n\t<pre>{pytest_cmd_args}</pre>\n\t<ul>",
        "</ul>",
        "<p><ins><strong>Observed behavior</strong></ins></p>",
        "<p> <strong><span style=\"background-color:#2ecc71\">????</span></strong></p>",
        "<p><strong><ins>Expected behavior</ins></strong></p>",
        "<p> <strong><span style=\"background-color:#2ecc71\">????</span></strong></p>",
        "<p><ins><strong>Attachments</strong></ins></p>",
        "<p> <strong><span style=\"background-color:#2ecc71\">Full dump is available in attachments:</span></strong></p>",
        "<pre>{attachments}</pre>"
    ]
    description_string = " ".join(description)
    return description_string.format(
        test_description=test_description,
        report_url=report_url,
        setup_name=setup_name,
        testbed_topology=testbed_topology,
        hwsku=hwsku,
        pytest_cmd_args=pytest_cmd_args,
        attachments=attachments
    )


def create_rm_bug(rm_object, data_for_rm_api):
    b_id = rm_object.create_bug(data_for_rm_api)
    if not b_id:
        print("failed to create bug")
    else:
        bug_info = rm_object.get_bug_info(b_id)
        print("created bug successfully {}".format(bug_info))


def create_local_dump_folder(session_id):
    """Create the local dump folder for the session"""
    session_folder = f"{VALID_DUMP_FOLDER}/{session_id}"
    os.makedirs(session_folder, exist_ok=True)
    return session_folder


def clean_valid_attachments():
    """Clean up the directory created by validate_attachments_for_rm_api"""
    target_dir = session_valid_dump_for_rm_api_folder
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir)
            print(f"✅ Cleaned up directory: {target_dir}")
        except Exception as e:
            print(f"⚠️ Warning: Failed to clean up directory {target_dir}: {e}")
    else:
        print(f"ℹ️ Directory {target_dir} does not exist, nothing to clean")


def main():
    global session_id
    global session_valid_dump_for_rm_api_folder
    parser = argparse.ArgumentParser(description='Create a bug ticket from JSON input file')
    parser.add_argument('json_file', help='JSON file containing bug details')
    args = parser.parse_args()
    bug_data = load_bug_data_from_json(args.json_file)
    session_id = bug_data.get('mars_session', '') + str(random.randint(0, 1000))
    session_valid_dump_for_rm_api_folder = create_local_dump_folder(session_id=session_id)
    CONN_CFG['user'] = CONN_CFG['user'] + bug_data['bug_author']
    rm = RedMineAccess(CONN_CFG)
    data_for_rm_api = create_data_for_rm_api(bug_data)
    create_rm_bug(rm, data_for_rm_api)
    clean_valid_attachments()


if __name__ == "__main__":
    main()
