#!/usr/bin/env python3
"""
Allure Nightly Summary Tool - Main Entry Point

This module provides the CLI interface for the Allure Summary tool.

Usage:
    python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --email user@nvidia.com
    python -m allure_summary --url "https://allure.nvidia.com/.../reports/201/index.html" --email user@nvidia.com
    python -m allure_summary --project nvos-juliet-10-7-145-52 --dry-run
"""

import argparse
import os
import re
import sys
from typing import Optional, Tuple

from ngts.scripts.allure_summary.config import LLM_DEFAULT_MODEL, MailList
from ngts.scripts.allure_summary.models import ReportSummary
from ngts.scripts.allure_summary.allure_client import AllureClient, fetch_report_summary
from ngts.scripts.allure_summary.analyzer import analyze_all_failures
from ngts.scripts.allure_summary.llm_client import LLMGatewayClient, analyze_failures_with_llm
from ngts.scripts.allure_summary.templates import generate_html_email
from ngts.scripts.allure_summary.email_sender import send_email
from ngts.scripts.allure_summary.logger import setup_logger, get_logger

# Path where allure_reporter.py writes the predicted URL
VERIFICATION_FILES_DIR = "/auto/sw_system_project/NVOS_INFRA/verification_files"


def get_url_from_verification_file(project_name: str) -> Optional[str]:
    """
    Read the Allure report URL from the verification file.

    The allure_reporter.py script writes the predicted URL to:
    /auto/sw_system_project/NVOS_INFRA/verification_files/{project_name}.txt

    Note: The file may use different naming conventions:
    - {project_name}.txt
    - {project_name}-session-reports.txt

    If both exist, we use the MOST RECENTLY MODIFIED one to ensure
    we get the current run's report.

    Args:
        project_name: The Allure project name (e.g., nvos-juliet-10-7-145-52)

    Returns:
        The URL string if file exists and is readable, None otherwise
    """
    logger = get_logger()

    # Try different file naming patterns
    possible_names = [
        f"{project_name}-session-reports.txt",  # Session-based reports
        f"{project_name}.txt",                   # Direct project reports
    ]

    # Find all existing files and their modification times
    found_files = []
    for filename in possible_names:
        file_path = os.path.join(VERIFICATION_FILES_DIR, filename)
        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            found_files.append((file_path, filename, mtime))
            logger.debug(f"Found verification file: {filename} (mtime: {mtime})")

    if not found_files:
        logger.warning(f"No verification file found for project: {project_name}")
        return None

    # Sort by modification time (most recent first) and use the newest
    found_files.sort(key=lambda x: x[2], reverse=True)
    best_file_path, best_filename, best_mtime = found_files[0]

    # Log if we had multiple files
    if len(found_files) > 1:
        from datetime import datetime
        times = [(f, datetime.fromtimestamp(m).strftime('%Y-%m-%d %H:%M:%S'))
                 for _, f, m in found_files]
        logger.info(f"Multiple verification files found: {times}")
        logger.info(f"Using most recent: {best_filename}")

    # Read the URL from the best file
    try:
        with open(best_file_path, 'r') as f:
            url = f.read().strip()
            if url:
                logger.info(f"✅ Found URL in verification file ({best_filename}): {url}")
                return url
            else:
                logger.warning(f"Verification file is empty: {best_file_path}")
                return None
    except IOError as e:
        logger.error(f"Failed to read verification file: {e}")
        return None


def parse_allure_url(url: str) -> Tuple[str, Optional[int]]:
    """
    Parse an Allure report URL to extract project name and report ID.

    Examples:
        https://allure.nvidia.com/allure-docker-service/projects/nvos-crocodile-10-245-21-19-session-reports/reports/201/index.html
        -> ('nvos-crocodile-10-245-21-19-session-reports', 201)
    """
    pattern = r'/projects/([^/]+)/reports/(\d+|latest)'
    match = re.search(pattern, url)

    if not match:
        raise ValueError(f"Could not parse Allure URL: {url}")

    project_name = match.group(1)
    report_id_str = match.group(2)
    report_id = int(report_id_str) if report_id_str.isdigit() else None

    return project_name, report_id


def setup_name_to_project(setup_name: str) -> str:
    """
    Convert MARS setup name to Allure project name.

    Example: NVOS_juliet_10_7_145_52 -> nvos-juliet-10-7-145-52
    """
    return setup_name.lower().replace("_", "-")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Allure Nightly Regression Summary Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using MARS setup name (recommended):
  python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --email user@nvidia.com

  # Using full URL (just copy from browser):
  python -m allure_summary --url "https://allure.nvidia.com/.../reports/201/index.html" --email user@nvidia.com

  # Using project name with specific report:
  python -m allure_summary --project nvos-juliet-10-7-145-52 --report-id 201 --output report.html

  # Dry run (no email sent):
  python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --email user@nvidia.com --dry-run

  # Using pre-defined mail list:
  python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --mail-list CORE_TEAM

  # With AI-powered analysis (requires LLM Gateway credentials):
  export LLM_GATEWAY_TOKEN="your-nvauth-token"
  python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --use-llm --email user@nvidia.com

Mail Lists Available:
  CORE_TEAM     - Core verification team
  EXTENDED_TEAM - Extended team with stakeholders
  PLATFORM_TEAM - Platform verification team
  SYSTEM_TEAM   - System verification team
  ALL           - All stakeholders
        """
    )

    # Input options
    input_group = parser.add_argument_group("Input Options")
    input_group.add_argument("--url", help="Full Allure report URL")
    input_group.add_argument("--project", help="Allure project name")
    input_group.add_argument("--setup-name", help="MARS setup name (auto-converts to project)")
    input_group.add_argument("--report-id", type=int, help="Specific report ID (default: latest)")

    # Email options
    email_group = parser.add_argument_group("Email Options")
    email_group.add_argument("--email", help="Comma-separated list of email recipients")
    email_group.add_argument("--mail-list", choices=[m.name for m in MailList] + ["SKIP"],
                             help="Use a pre-defined mail distribution list (SKIP = no email)")
    email_group.add_argument("--dry-run", action="store_true", help="Don't send email, just preview")

    # AI/LLM options
    llm_group = parser.add_argument_group("AI Analysis Options")
    llm_group.add_argument("--use-llm", action="store_true",
                           help="Enable AI-powered analysis via NVIDIA LLM Gateway")
    llm_group.add_argument("--llm-model", default="gpt-4o",
                           help="LLM model to use (default: gpt-4o)")

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument("--output", help="Save HTML to file")
    output_group.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Validate that we have either URL, project, or setup-name
    if not args.url and not args.project and not args.setup_name:
        parser.error("Either --url, --project, or --setup-name is required")

    # Validate that we have either email or mail-list or output
    if not args.email and not args.mail_list and not args.output:
        parser.error("Either --email, --mail-list, or --output is required")

    return args


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    logger = setup_logger(verbose=args.verbose)
    logger.info("=" * 60)
    logger.info("Allure Nightly Summary Tool v1.0.0")
    logger.info("=" * 60)

    # Determine project name and report ID
    if args.url:
        try:
            project_name, report_id = parse_allure_url(args.url)
            logger.info(f"Parsed URL: project={project_name}, report_id={report_id or 'latest'}")
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
    elif args.setup_name:
        base_project_name = setup_name_to_project(args.setup_name)
        project_name = base_project_name
        report_id = args.report_id
        logger.info(f"Converted setup '{args.setup_name}' -> base project '{base_project_name}'")

        # Try to get URL from verification file (written by allure_reporter.py)
        # This ensures we get the CURRENT run's report, not the previous one
        if report_id is None:
            verification_url = get_url_from_verification_file(base_project_name)
            if verification_url:
                try:
                    # Parse the full project name and report ID from the URL
                    # This handles the -session-reports suffix correctly
                    parsed_project, report_id = parse_allure_url(verification_url)
                    project_name = parsed_project  # Use the actual project name from URL
                    logger.info(f"Using project '{project_name}' and report #{report_id} from verification file")
                except ValueError:
                    logger.warning("Could not parse verification file URL, will use latest from API")
            else:
                logger.info("No verification file found, will try both project naming patterns")
                # Both patterns are valid - some setups use -session-reports suffix
                # Will be handled in fetch logic below
    else:
        project_name = args.project
        report_id = args.report_id
        logger.info(f"Using project: {project_name}")

    # Fetch report data
    logger.info("-" * 40)
    logger.info("Fetching report data...")

    client = AllureClient()
    summary = fetch_report_summary(client, project_name, report_id)

    if summary.error:
        logger.error(f"Failed to fetch report: {summary.error}")
        sys.exit(1)

    # Log summary
    logger.info("-" * 40)
    logger.info(f"📊 Report Summary:")
    logger.info(f"   {summary}")
    logger.info(f"   Duration: {summary.duration_minutes:.1f} minutes")
    logger.info(f"   Failed/Broken tests: {len(summary.failed_tests)}")

    # Show first 5 failures
    for test in summary.failed_tests[:5]:
        logger.info(f"   [{test.status.upper()}] {test.name}")
    if len(summary.failed_tests) > 5:
        logger.info(f"   ... and {len(summary.failed_tests) - 5} more")

    # Analyze failures
    logger.info("-" * 40)
    logger.info("Analyzing failures...")

    analyses = analyze_all_failures(summary.failed_tests)

    # LLM Analysis (if enabled)
    llm_analysis = None
    if args.use_llm:
        logger.info("-" * 40)
        logger.info("🤖 Running AI-powered analysis...")

        llm_client = LLMGatewayClient(model=args.llm_model)
        if llm_client.is_available():
            llm_analysis = analyze_failures_with_llm(summary, llm_client)
            if llm_analysis:
                logger.info("✅ AI analysis complete")
            else:
                logger.warning("AI analysis returned no results")
        else:
            logger.warning("LLM Gateway credentials not found!")
            logger.warning("Set LLM_GATEWAY_TOKEN env var (NV-Auth) or")
            logger.warning("Set LLM_CLIENT_ID + LLM_CLIENT_SECRET env vars (SSA OAuth)")
            logger.info("Continuing without AI analysis...")

    # Generate HTML
    logger.info("-" * 40)
    logger.info("Generating HTML report...")

    html = generate_html_email(summary, analyses, llm_analysis)

    # Save to file if requested
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(html)
            logger.info(f"✅ HTML saved to: {args.output}")
        except IOError as e:
            logger.error(f"Failed to save HTML: {e}")

    # Determine recipients
    recipients = []
    if args.email:
        # SKIP means no email should be sent (not configured in setup)
        if args.email.upper() == "SKIP":
            logger.info("📧 Email not configured - no email will be sent")
            logger.info("   (Configure 'allure_summary_emails' in .setup file to enable)")
        else:
            recipients = [r.strip() for r in args.email.split(",") if r.strip()]
            if recipients:
                logger.info(f"📧 Recipients from config: {', '.join(recipients)}")
    elif args.mail_list:
        # SKIP means no email should be sent (mail list not configured in setup)
        if args.mail_list.upper() == "SKIP":
            logger.info("📧 Mail list set to SKIP - no email will be sent")
            logger.info("   (Configure 'allure_mail_list' in .setup file to enable)")
        else:
            from ngts.scripts.allure_summary.config import get_mail_list
            recipients = get_mail_list(args.mail_list)
            if recipients:
                logger.info(f"Using mail list '{args.mail_list}': {recipients}")
            else:
                logger.warning(f"Mail list '{args.mail_list}' not found or empty")

    # Send email
    if recipients:
        logger.info("-" * 40)
        subject = f"Nightly Regression Summary - {project_name} - {summary.pass_rate:.1f}% Pass Rate"

        success = send_email(
            recipients=recipients,
            subject=subject,
            html_body=html,
            dry_run=args.dry_run
        )

        if not success and not args.dry_run:
            logger.error("Failed to send email")
            sys.exit(1)
    else:
        if not args.output:
            logger.info("📧 No recipients configured - email not sent")

    logger.info("=" * 60)
    logger.info("Done!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
