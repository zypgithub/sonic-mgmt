"""
HTML Templates for Allure Summary Tool.
"""

from ngts.scripts.allure_summary.templates.email_template import generate_html_email
from ngts.scripts.allure_summary.templates.multi_system_template import generate_multi_system_email

__all__ = ["generate_html_email", "generate_multi_system_email"]
