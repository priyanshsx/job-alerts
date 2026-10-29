#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

from job_alerts.core.db import ROOT, DB_PATH, get_conn

FOLDERS = ["data/cache", "outputs"]


def main():
    for folder in FOLDERS:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)

    schema = (ROOT / "db" / "schema.sql").read_text()
    conn = get_conn()
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#