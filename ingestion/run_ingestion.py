"""
Runs the full DE2 ingestion flow against data/landing/.
"""
from ingestion import detect_files, process_file

files = detect_files("data/landing")
print(f"Detected {len(files)} file(s): {files}\n")

for filepath in files:
    result = process_file(
        filepath,
        raw_dir="data/raw",
        rejected_dir="data/rejected",
        log_path="logs/ingestion_log.jsonl",
    )
    print(result)