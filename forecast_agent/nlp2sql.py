"""NLP → BigQuery SQL using Claude API. Falls back to a canned query when no API key is set."""

import os
import logging

logger = logging.getLogger(__name__)

_SCHEMA_DESCRIPTION = """\
BigQuery table: `{project}.{dataset}.{table}`
Columns:
  - month          DATE         Monthly grain (always YYYY-MM-01)
  - customer_type  STRING       'new' or 'existing'
  - product_line   STRING       'classic' or 'super'
  - customer_count INTEGER      Head-count for that month / type / product combination
"""

_FALLBACK_SQL = """\
SELECT
    month,
    customer_type,
    product_line,
    SUM(customer_count) AS customer_count
FROM `{project}.{dataset}.{table}`
WHERE month >= DATE_SUB(CURRENT_DATE(), INTERVAL 5 YEAR)
GROUP BY 1, 2, 3
ORDER BY month ASC
"""


def generate_historical_query(
    natural_language: str,
    project: str,
    dataset: str,
    table: str,
) -> str:
    """Convert a natural-language description into a BigQuery SQL query."""
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key or project == "demo":
        logger.info("No ANTHROPIC_API_KEY found or demo mode — using fallback SQL.")
        return _FALLBACK_SQL.format(project=project, dataset=dataset, table=table)

    import anthropic

    schema = _SCHEMA_DESCRIPTION.format(project=project, dataset=dataset, table=table)
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=(
            "You are a BigQuery SQL expert. Given a table schema and a natural-language "
            "request, return ONLY valid BigQuery Standard SQL — no markdown, no explanation. "
            "Always filter to the last 5 years and order by month ASC."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Schema:\n{schema}\n\nRequest: {natural_language}",
            }
        ],
    )

    sql = response.content[0].text.strip()
    logger.info("Claude-generated SQL:\n%s", sql)
    return sql
