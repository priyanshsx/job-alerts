#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: scripts/reset_leads.py
# Purpose: start a client's Leads over after its targeting changed. Deletes the client's leads,
#          and marks its relevant postings for re-classification under the new rules, except
#          employer types you name with --keep-excluded (e.g. consultancy), which the new rules
#          exclude anyway, so they aren't paid for again. Collected postings are kept.
#          Afterwards: delete the rows below the header in the client's Leads tab by hand
#          (sync never deletes rows), then fetch, classify, prioritize, leads, sync.
# Usage:   python3 scripts/reset_leads.py --client kymeer --keep-excluded consultancy agency
#--------------------------------------------------------------#

# Imports libraries
import argparse
from job_alerts.core.db import get_conn, get_client_id
#--------------------------------------------------------------#

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--keep-excluded", nargs="*", default=[],
                        help="employer types not to re-classify (the new rules exclude them)")
    parser.add_argument("--all", action="store_true",
                        help="re-classify every posting, relevant or not (after the definition of relevant changed)")
    parser.add_argument("--leads-only", action="store_true",
                        help="only delete the leads; keep every posting's classification (free)")
    args = parser.parse_args()

    conn = get_conn()
    client_id = get_client_id(conn, args.client)
    if args.leads_only:
        deleted = conn.execute("DELETE FROM leads WHERE client_id = ?", (client_id,)).rowcount
        conn.commit()
        conn.close()
        print(f"[{args.client}] {deleted} leads deleted (no re-classification). "
              "Now clear the Leads tab rows below the header, then run prioritize, leads and sync.")
        return
    if args.all:
        reset = conn.execute("UPDATE job_postings SET classified_at = NULL, priority = NULL "
                             "WHERE client_id = ?", (client_id,)).rowcount
        deleted = conn.execute("DELETE FROM leads WHERE client_id = ?", (client_id,)).rowcount
        conn.commit()
        conn.close()
        print(f"[{args.client}] {deleted} leads deleted; all {reset} postings will be re-classified "
              f"(about INR {reset * 0.75:.0f}). Now clear the Leads tab rows below the header.")
        return
    skip = list(args.keep_excluded)
    placeholders = ",".join("?" * len(skip)) or "''"
    reset = conn.execute(
        f"UPDATE job_postings SET classified_at = NULL, priority = NULL "
        f"WHERE client_id = ? AND is_relevant = 1 AND COALESCE(employer_type, '') NOT IN ({placeholders})",
        (client_id, *skip)).rowcount
    conn.execute(f"UPDATE job_postings SET priority = NULL WHERE client_id = ? "
                 f"AND COALESCE(employer_type, '') IN ({placeholders})", (client_id, *skip))
    deleted = conn.execute("DELETE FROM leads WHERE client_id = ?", (client_id,)).rowcount
    conn.commit()
    conn.close()
    print(f"[{args.client}] {deleted} leads deleted; {reset} postings will be re-classified "
          f"(about INR {reset * 0.75:.0f}). Now clear the Leads tab rows below the header.")
#--------------------------------------------------------------#

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
