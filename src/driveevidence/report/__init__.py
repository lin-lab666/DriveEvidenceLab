"""Report generation: Markdown and HTML summaries from a run directory."""

from driveevidence.report.generator import (
    ReportSummary,
    generate_html,
    generate_markdown,
    load_report,
)

__all__ = [
    "ReportSummary",
    "load_report",
    "generate_markdown",
    "generate_html",
]
