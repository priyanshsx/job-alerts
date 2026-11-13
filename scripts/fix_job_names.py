#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: scripts/fix_job_names.py
# Purpose: repair company names of job-board postings saved with a broken name: a page title
#          ("Security Analyst At Zoracom"), a web-address slug ("Addepar1"), a generic word
#          ("Application") or a site suffix ("Oracle - Jobs"). The company is taken from the
#          posting's web address instead. Renames the matching leads too (skipped when another
#          lead already has the corrected name). All clients. No AI, no searches.
# Usage:   python3 scripts/fix_job_names.py
#--------------------------------------------------------------#

# Imports libraries
from job_alerts.core.db import get_conn
from job_alerts.core.names import normalize_name
from job_alerts.sources.ats_search import SITES, _title_and_company, clean_company, company_from_url, looks_broken
#--------------------------------------------------------------#

def main() -> None:
    conn = get_conn()
    placeholders = ",".join("?" * len(SITES))
    rows = conn.execute(f"SELECT id, client_id, source, url, title, company_name FROM job_postings "
                        f"WHERE source IN ({placeholders})", tuple(SITES)).fetchall()
    postings = leads = skipped = 0
    for r in rows:
        old_name, title = r["company_name"], r["title"]
        if not looks_broken(old_name):
            continue
        company = ""
        if r["source"] == "linkedin_jobs" and " at " in (title or ""):
            title, company = _title_and_company("linkedin_jobs", title, "")
        company = clean_company(company)
        if looks_broken(company):
            company = company_from_url(r["source"], r["url"]) or clean_company(old_name)
        if not company or company == old_name or looks_broken(company):
            continue
        conn.execute("UPDATE job_postings SET title = ?, company_name = ? WHERE id = ?",
                     (title, company, r["id"]))
        postings += 1
        old_key, new_key = normalize_name(old_name), normalize_name(company)
        lead = conn.execute("SELECT id FROM leads WHERE client_id = ? AND name_normalized = ?",
                            (r["client_id"], old_key)).fetchone()
        if not lead:
            continue
        if conn.execute("SELECT 1 FROM leads WHERE client_id = ? AND name_normalized = ?",
                        (r["client_id"], new_key)).fetchone():
            skipped += 1                             # already a lead under its real name
            continue
        conn.execute("UPDATE leads SET company_name = ?, name_normalized = ? WHERE id = ?",
                     (company, new_key, lead["id"]))
        leads += 1
    conn.commit()
    conn.close()
    print(f"fixed {postings} postings, renamed {leads} leads, {skipped} left as they were (duplicates)")
#--------------------------------------------------------------#

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
