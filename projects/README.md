# Reproducible projects

Copy `template/` to a folder with a short project name. Keep code, a README, and non-sensitive settings in Git. Keep downloaded data in that project's `input/` folder and generated files in its `outputs/` folder. The ignore rules preserve `.gitkeep` files so both folders exist in a fresh clone.

Each project README should record:

- The question, data source and version, download steps, and source checksum.
- Required Python and package versions, plus exact commands to run the work.
- Column names, units, timezone, quality rules, and any exclusions.
- Parameters, random seeds, expected outputs, and known limitations.

Use the root environment when its dependencies fit. If a project needs different dependencies, keep its requirements file inside its own folder and use a separate virtual environment. Do not add project-only dependencies to the Streamlit environment.

`analyze.py` and `create_brief.py` are specific to the published Louisiana case study. They contain fixed source checks, dates, and report text; they are not general analysis commands for a new dataset. The app's **Process New Data** page supports evaluating other compatible monitoring CSVs.
