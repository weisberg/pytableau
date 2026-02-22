# Cookbook

## Recipe 1: Template-Based Report Generation

Generate a dashboard from a starter template and swap in production field names before saving:

```python
from pathlib import Path
from pytableau import Workbook

wb = Workbook.from_template(
    "bar_chart",
    __DIMENSION__="Region",
    __MEASURE__="Sales",
)
wb.template.map_fields({"__WORKSHEET__": "Sales by Region"})
wb.template.map_datasource({"__PLACEHOLDER_DS__": "Sales Source"})
wb.template.validate_all_mapped()
wb.save_as(Path("out") / "sales_bar_report.twbx")
```

## Recipe 2: DataFrame → Workbook Pipeline

Create or replace a datasource extract from a pandas `DataFrame` and keep the workbook
metadata in sync with the new column set:

```python
from pathlib import Path
import pandas as pd
from pytableau import Workbook

df = pd.read_parquet("sales.parquet")  # any DataFrame-like object from pandas works
wb = Workbook.open("template_with_extract.twbx")
datasource = wb.datasources.get("SalesData")
if datasource is None:
    raise KeyError("Expected a datasource named 'SalesData'")

datasource.create_extract(df, table="Sales")
# or replace existing data:
# datasource.refresh_extract(df, table="Sales")
wb.save_as(Path("out") / "sales_from_dataframe.twbx")
```

## Recipe 3: CI/CD Connection Promotion

Promote a staged workbook into production by reusing the same publish surface with
environment-specific credentials:

```python
import os
from pytableau import Workbook

wb = Workbook.open("staging_sales.twbx")
wb.publish(
    server="https://tableau.example.com",
    project="Executive Analytics",
    token_name=os.environ["TABLEAU_TOKEN_NAME"],
    token_secret=os.environ["TABLEAU_TOKEN_SECRET"],
    site_id=os.environ.get("TABLEAU_SITE_ID", ""),
)
```

## Recipe 4: Workbook Auditing and Documentation

Produce a lightweight audit artifact from workbook metadata and compute one field’s
lineage graph.

```python
from pathlib import Path
from pytableau import Workbook

wb = Workbook.open("finance.twbx")
audit = wb.report().to_markdown()
Path("finance_audit.md").write_text(audit, encoding="utf-8")

lineage = wb.lineage().for_field("Gross Margin %")
if lineage is not None:
    print(f"{lineage.field} depends on {[dep.as_token() for dep in lineage.depends_on]}")
```

## Recipe 5: Server Lifecycle Automation

Use the server workflow helpers for one-pass download, mutate, republish loops.

```python
from pathlib import Path
from pytableau import Workbook
from pytableau.server.workflows import download_workbook, refresh_workbook

downloaded = download_workbook(
    server="https://tableau.example.com",
    workbook_id="workbook-id-123",
    destination=Path("quarterly_downloaded.twbx"),
    token_name="ci-token",
    token_secret="...secret...",
    site_id="",
)

def mutate(workbook: Workbook) -> None:
    worksheet = workbook.worksheets[0]
    worksheet.name = f"{worksheet.name} (Reviewed)"

refreshed = refresh_workbook(
    server="https://tableau.example.com",
    workbook_id="workbook-id-123",
    destination=Path("quarterly_refreshed.twbx"),
    project_id="Finance",
    modifier=mutate,
    token_name="ci-token",
    token_secret="...secret...",
    site_id="",
)
refreshed.publish(
    server="https://tableau.example.com",
    project="Finance",
    token_name="ci-token",
    token_secret="...secret...",
    site_id="",
)
```
