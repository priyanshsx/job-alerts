#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 

import argparse 
import shutil 
from datetime import datetime, timezone 

from job_alerts.core.db import ROOT, get_conn 

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="short lowercase name")
    parser.add_argument("--template", default="b2b")
    args = parser.parse_args()
    name = args.name.lower()
    
    # 1. Config folder, copied from the template (never overwrites an existing config)
    client_dir = ROOT / "config" / "clients" / name
    client_dir.mkdir(parents=True, exist_ok=True)
    config_file = client_dir / "config.yaml"
    if config_file.exists():
        print(f"Config for '{name}' already exists, leaving it untouched.")
    else:
        shutil.copy(ROOT / "config" / "templates" / f"{args.template}.yaml", config_file)

    # 2. Output folder for this client's digests
    (ROOT / "outputs" / name / "digests").mkdir(parents=True, exist_ok=True)

    # 3. Row in the clients table
    conn = get_conn()
    conn.execute(
        "INSERT INTO clients (name, config_path, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (name) DO NOTHING",
        (name, f"config/clients/{name}/config.yaml",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    print(f"Client '{name}' ready. Fill in {config_file}")

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#