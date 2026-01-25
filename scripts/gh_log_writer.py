# GhPython script for writing logs to text files with timestamps
#
# Inputs:
#   folder_path (str): The folder where the log file will be saved
#   file_name (str): Base name for the log file (without extension)
#   text (str): The text content to write to the file
#   run (bool): Toggle to trigger writing
#
# Outputs:
#   file_path (str): The full path to the created file
#   status (str): Status message

import os
from datetime import datetime

# Default values if not provided
if folder_path is None:
    folder_path = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator\logs"
if file_name is None:
    file_name = "gh-output"
if text is None:
    text = ""

output_path = None
status = "Waiting for run trigger..."

if run:
    try:
        # Create folder if it doesn't exist
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # Generate timestamp in format YYYYMMDD_HHmm
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        # Create full filename with timestamp
        full_filename = f"{file_name}_{timestamp}.txt"
        output_path = os.path.join(folder_path, full_filename)

        # Write the text to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)

        status = f"Successfully wrote {len(text)} characters to {full_filename}"
        file_path = output_path

    except Exception as e:
        status = f"Error: {str(e)}"
        file_path = None
else:
    file_path = None
