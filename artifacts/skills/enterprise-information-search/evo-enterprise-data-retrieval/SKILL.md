---
name: evo-enterprise-data-retrieval
description: "Retrieves information from enterprise data to answer questions about products, teams, and processes"
---

# Enterprise Data Retrieval Skill

## Overview
This skill provides utility functions for searching and extracting information from
enterprise product data files. It discovers the data schema at runtime rather than
assuming fixed field names or structures.

## End-to-End Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-enterprise-data-retrieval/scripts')
from utils import run_end_to_end, validate_answer

# Run end-to-end: reads questions, searches data, writes answer.json
result = run_end_to_end(
    question_path='/root/question.txt',
    data_dir='/root/DATA',
    output_path='/root/answer.json'
)

# Validate the output
errors = validate_answer('/root/answer.json')
assert len(errors) == 0, f"Validation errors: {errors}"
print("Done! Answer written to /root/answer.json")
```

## Available Functions

- `load_product_data(product_name, data_dir)` - Load a product data file
- `load_employee_data(data_dir)` - Load employee metadata
- `search_slack(product_data, keywords)` - Search messaging data by keywords
- `find_document_authors_and_reviewers(product_data, doc_type)` - Find authors and reviewers for a document type across all available sources
- `find_competitor_insights(product_data)` - Find team members who discussed competitor strengths/weaknesses
- `find_competitor_demo_urls(product_data)` - Find external demo URLs for competitor products
- `create_answer(answers_dict, output_path)` - Write answer file with proper format
- `run_end_to_end(question_path, data_dir, output_path)` - Full pipeline from questions to answers
- `validate_answer(output_path)` - Validate answer file format and constraints

## Key Patterns
- Document authors: found in document metadata author fields
- Document reviewers: found in messaging feedback and transcript participant lists
- Competitor insights: initiated by messages introducing competitor products for discussion
- Demo URLs: external URLs containing "demo" (filtered from internal URLs)
