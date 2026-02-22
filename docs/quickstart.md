# Quickstart

## Install

```bash
pip install pytableau
```

For optional features:

```bash
pip install pytableau[hyper]   # Hyper bridge
pip install pytableau[server]  # Server publish/download workflows
```

## Open a workbook

```python
from pytableau import Workbook

workbook = Workbook.open("sales.twbx")
print(workbook.version)
```

## Generate from a template

```python
from pytableau import Workbook

wb = Workbook.from_template(
    "bar_chart",
    __DIMENSION__="Region",
    __MEASURE__="Sales",
    __PLACEHOLDER_DS__="SalesData",
    __WORKSHEET__="Sales by Region",
)
wb.template.map_fields({"__DASHBOARD__": "Regional Overview"})
wb.template.validate_all_mapped()
wb.save_as("regional_report.twbx")
```
