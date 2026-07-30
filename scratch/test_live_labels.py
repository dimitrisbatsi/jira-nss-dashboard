import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import json
from dotenv import load_dotenv
load_dotenv()

from src.api.jira_client import JiraAPIClient
from modules.test_issues_etl import get_dynamic_jira_fields
from src.etl.transformers import transform_jira_custom_fields

try:
    client = JiraAPIClient()
    my_fields, custom_fields_mapping = get_dynamic_jira_fields("jira_custom_fields.csv")

    print("[*] my_fields requested:", my_fields[:150] + "...")

    # Query 10 Jira tickets where labels is not empty
    generator = client.get_issues_chunked(jql_query='labels IS NOT EMPTY AND updated >= "2026-01-01 00:00" ORDER BY updated DESC', chunk_size=10, requested_fields=my_fields)

    found_labels_count = 0
    for batch in generator:
        for raw_issue in batch:
            fields = raw_issue.get("fields", {})
            key = raw_issue.get("key", "Unknown")
            print(f"\nTicket {key}:")
            print("  - 'labels' key in fields?:", "labels" in fields)
            print("  - raw labels value:", repr(fields.get("labels")))
            
            cfs = transform_jira_custom_fields(raw_issue, custom_fields_mapping)
            label_cfs = [cf for cf in cfs if cf.CustomFieldName == "labels" or cf.CustomFieldID == 999999]
            print("  - transformed label CustomFields:", [l.model_dump() for l in label_cfs])
            if label_cfs:
                found_labels_count += len(label_cfs)
        break

    print(f"\nTotal label custom fields generated: {found_labels_count}")
except Exception as e:
    import traceback
    print("Error:", e)
    traceback.print_exc()
