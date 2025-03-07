import requests
import json
import os
import sys

# Get environment variables
api_key = os.environ['GEMINI_API_KEY']
diff_files = os.environ['DIFF_FILES']
diff_content = os.environ['DIFF_CONTENT']
commits = os.environ['COMMITS']
branch_name = os.environ['BRANCH_NAME']

# Gemini API endpoint
url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# Prepare prompt (Enhanced to include label generation)
prompt = f"""You are assisting in creating a pull request for a project.
The project is a timber framing generator written in Python. This tool automatically
generates framing elements (studs, plates, headers, etc.) for construction models.

Given the git diff, commit messages, and branch name below, generate:
1. A concise pull request title
2. A detailed description explaining the changes
3. Appropriate labels for categorizing this PR

Consider these label categories:
- feature: New functionality or enhancements
- bug: Bug fixes and corrections
- refactor: Code restructuring without functional changes
- documentation: Documentation updates or improvements
- test: Test additions or modifications
- ci: CI/CD configuration changes
- mock: CI mocking system changes
- wall-data: Wall data extraction or processing components
- framing-elements: Changes to framing element generation
- utils: Utility functions and helpers
- cell-decomposition: Cell analysis and segmentation

Branch name: {branch_name}

Git diff files:
{diff_files}

Commit messages:
{commits}

Diff content (truncated):
{diff_content}

Return the results in the following format:
```
PR TITLE: [Generated title]

PR DESCRIPTION:
[Generated description with ## headings for sections, e.g., ## Summary, ## Changes, ## Testing]

LABELS: [comma-separated list of applicable labels, at least one but no more than three]
```
"""

# Prepare request payload
payload = {
  "contents": [{"parts":[{"text": prompt}]}],
  "generationConfig": {
    "temperature": 0.7,
    "maxOutputTokens": 1000 # Increased max tokens
  }
}

headers = {
  "Content-Type": "application/json",
  "x-goog-api-key": api_key
}

# Make the API request
try:
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()  # Raise an exception for bad status codes

    # Extract the generated text (Corrected JSON parsing)
    result = response.json()
    generated_text = result["candidates"][0]["content"]["parts"][0]["text"]

    # Write to output file
    with open('pr_content.txt', 'w') as f:
        f.write(generated_text)

    print("Successfully generated PR content")

except requests.exceptions.RequestException as e:
    print(f"Error during API request: {e}")
    sys.exit(1)
except (KeyError, IndexError) as e:
    print(f"Error parsing API response: {e}")
    sys.exit(1)

