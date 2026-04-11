import json
from pathlib import Path

def generate_parity_report(data, output_path: Path):
    output_path.write_text(json.dumps(data, indent=2))
