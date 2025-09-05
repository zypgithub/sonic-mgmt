#!/usr/bin/env python3
"""
Script to send setup details via email based on simulation_details.json file.

This script reads a JSON file containing setup details and sends them via email
to the specified recipient. The JSON file path is constructed using the --setup_name
flag value.

Usage:
    python send_air_spin_email.py --setup_name <setup_name> --recipient <recipient>

Example:
    python send_air_spin_email.py --setup_name my_setup --recipient ikotvitskyi@nvidia.com
"""

import argparse
import json
import logging
import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any

path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)

from ngts.constants.constants import InfraConst


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def read_simulation_details(setup_name: str) -> Dict[str, Any]:
    """
    Read simulation details from the JSON file.

    Args:
        setup_name: Name of the setup to read details for

    Returns:
        Dictionary containing the simulation details

    Raises:
        FileNotFoundError: If the JSON file doesn't exist
        json.JSONDecodeError: If the JSON file is malformed
    """
    json_file_path = f"{InfraConst.MARS_SETUPS_FOLDER_PATH}{setup_name}/simulation_details.json"

    if not os.path.exists(json_file_path):
        raise FileNotFoundError(f"Simulation details file not found: {json_file_path}")

    logging.info(f"Reading simulation details from: {json_file_path}")

    with open(json_file_path, 'r') as file:
        data = json.load(file)

    logging.info(f"Successfully read simulation details for setup: {setup_name}")
    return data


def _get_template_path() -> str:
    """Get the single template file path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'templates', 'air_spin_template.html')


def _build_simulation_link(data: Dict[str, Any]) -> str:
    """Build simulation link HTML."""
    if 'simulation_id' not in data:
        return ""

    simulation_id = data['simulation_id']
    link_url = f"https://air-inside.nvidia.com/simulations/{simulation_id}"
    return f'<div class="info-item"><span class="info-label">Simulation Link:</span> <a href="{link_url}" target="_blank">{link_url}</a></div>'


def _build_info_items(data: Dict[str, Any]) -> str:
    """Build info items section HTML."""
    info_items = ""

    info_fields = [
        ('Sonic Management IP', 'sonic_mgmt_ip'),
        ('Simulation Name', 'simulation_name'),
        ('Simulation ID', 'simulation_id'),
        ('DUT Model', 'dut_model')
    ]

    for label, field_name in info_fields:
        if field_name in data:
            info_items += f'<div class="info-item"><span class="info-label">{label}:</span> {data[field_name]}</div>'

    return info_items


def _get_ssh_user_for_service(service_name: str) -> str:
    """
    Get the appropriate SSH user for a service based on its name.

    Args:
        service_name: Name of the service

    Returns:
        SSH username for the service
    """
    service_name_lower = service_name.lower()

    if 'dut' in service_name_lower:
        return 'admin'
    elif 'ha' in service_name_lower or 'hb' in service_name_lower:
        return 'root'
    elif 'oob-mgmt-server' in service_name_lower:
        return 'ubuntu'
    else:
        return 'admin'  # Default fallback


def _build_services_section(data: Dict[str, Any]) -> str:
    """Build services section HTML."""
    if 'services' not in data or not data['services']:
        return ""

    services_html = '<h2>Services</h2><table><thead><tr><th>Service Name</th><th>External Port</th><th>External Host</th></tr></thead><tbody>'

    for service in data['services']:
        name = service.get('name', 'N/A')
        port = service.get('external_port', 'N/A')
        host = service.get('external_host', 'N/A')
        services_html += f'<tr><td>{name}</td><td>{port}</td><td>{host}</td></tr>'

    services_html += '</tbody></table>'
    return services_html


def _build_ssh_commands_section(data: Dict[str, Any]) -> str:
    """Build SSH commands section HTML."""
    if 'services' not in data or not data['services']:
        return ""

    # Filter services that end with '-22'
    filtered_services = [service for service in data['services'] if service.get('name', '').endswith('-22')]

    if not filtered_services:
        return ""

    ssh_html = '<h2>SSH Commands</h2><div class="ssh-commands">'

    for service in filtered_services:
        name = service.get('name', 'N/A').replace('-22', '')
        port = service.get('external_port', 'N/A')
        host = service.get('external_host', 'N/A')

        # Generate SSH command
        if port != 'N/A' and host != 'N/A':
            ssh_user = _get_ssh_user_for_service(name)
            ssh_command = f'ssh {ssh_user}@{host} -p {port}'
            ssh_html += f'<div class="ssh-command-item"><span class="service-name">{name}:</span><br><code class="ssh-command">{ssh_command}</code></div>'

    ssh_html += '</div>'
    return ssh_html


def format_json_for_email(data: Dict[str, Any], setup_name: str) -> str:
    """
    Format JSON data into a readable HTML email format using a single template.

    Args:
        data: Dictionary containing the simulation details
        setup_name: Name of the setup

    Returns:
        Formatted HTML string for email content
    """
    # Load single template
    template_path = _get_template_path()
    with open(template_path, 'r') as template_file:
        template = template_file.read()

    # Prepare dynamic content
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build sections
    simulation_link = _build_simulation_link(data)
    info_items = _build_info_items(data)
    services_section = _build_services_section(data)
    ssh_commands_section = _build_ssh_commands_section(data)

    # Fill the template using string replacement
    html_content = template.replace('{{timestamp}}', timestamp)
    html_content = html_content.replace('{{setup_name}}', setup_name)
    html_content = html_content.replace('{{simulation_link}}', simulation_link)
    html_content = html_content.replace('{{info_items}}', info_items)
    html_content = html_content.replace('{{services_section}}', services_section)
    html_content = html_content.replace('{{ssh_commands_section}}', ssh_commands_section)

    return html_content


def send_email(recipient: str, subject: str, content: str):
    """
    Send email with the provided content.

    Args:
        recipient: Email address of the recipient
        subject: Email subject
        content: Email content
    """
    smtp_host = "mailgw.nvidia.com"
    smtp_port = 25
    from_email = "nbu-system-sw-sonic-ver@exchange.nvidia.com"

    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = recipient
        msg['Subject'] = subject

        # Add body to email as HTML
        msg.attach(MIMEText(content, 'html'))

        # Send email
        logging.info(f"Sending email to: {recipient}")
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()  # Enable TLS encryption
        server.send_message(msg)
        server.quit()

        logging.info("Email sent successfully")

    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        raise


def init_parser():
    """Initialize command line argument parser."""
    description = 'Send AirSpin setup details via email based on simulation_details.json file'

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        '--setup_name',
        required=True,
        help='Name of the setup to read simulation details for'
    )

    parser.add_argument(
        '--recipient',
        required=True,
        help='Email recipient'
    )

    return parser.parse_args()


def main():
    """Main function."""
    setup_logging()

    try:
        args = init_parser()

        # Read simulation details
        simulation_data = read_simulation_details(args.setup_name)

        # Format data for email
        email_content = format_json_for_email(simulation_data, args.setup_name)

        # Generate subject
        subject = f"{args.setup_name} AirSpin setup details"

        # Send email
        send_email(args.recipient, subject, email_content)

        logging.info("Script completed successfully")

    except FileNotFoundError as e:
        logging.error(f"File not found: {str(e)}")
        return 1
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format: {str(e)}")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
