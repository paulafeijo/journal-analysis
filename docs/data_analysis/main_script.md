# Journal Analysis Data Fetching – Main Script

## Overview

This script serves as a controller for fetching journal data in multiple steps.
It executes multiple data collection and processing scripts using the `subprocess module`, recieving the **base journal ISSN** and passing it as input to each step.

## Script flow

### User input

As input, the user is asked to enter the **base journal ISSN**, which will be used in all data fetching scripts.


### Data fetching steps

| Step | Script | Description |
|------|--------|-------------|
| 1 | `data_fetching/fetch_articles.py` | Fetches articles from the base journal. |
| 2 | `data_fetching/fetch_authors.py` | Retrieves author details for the base journal’s articles. |
| 3 | `data_fetching/references_citations.py` | Collects reference and citation information for the journal’s articles. |
| 4 | `data_fetching/top_competitors_citations.py` | Identifies top competitor journals based on citation patterns. |
| 5 | `data_fetching/fetch_competitor_articles.py` | Downloads article data for top competitors. |
| 6 | `data_fetching/fetch_competitor_authors.py` | Retrieves author details for competitor journal articles. |
| 7 | `data_fetching/generating_final_db.py` | Compiles all gathered data into a final structured database. |
| 8 | `data_fetching/error_tracking.py` | Saves error logs for tracking and debugging purposes. |


### Subprocess execution

Each step is run as a separate Python process.

```
subprocess.run(
    ["python", "path/to/script.py"], 
    input=base_issn.encode()
)
```


`input=base_issn.encode()` ensures the ISSN is passed as standard input to the script.

This approach isolates each task, allowing independent execution and debugging.


### Completion message

After all steps, the script returns the following message:

```
✅ All steps completed! Your final database is ready.
```

