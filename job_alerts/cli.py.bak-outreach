#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import argparse
from job_alerts.collect import collect
from job_alerts.describe import describe
from job_alerts.classify import classify
from job_alerts.prioritize import prioritize
from job_alerts.leads import build_leads
from job_alerts.core import usage
from job_alerts.sync import sync
from job_alerts.digest import send_digest
from job_alerts.people import find_people
from job_alerts.people_digest import send_people_digest
from job_alerts.people_sync import people_sync
from job_alerts.contacts import contacts, lookup
from job_alerts.costs import write_costs
#--------------------------------------------------------------#

def main():
    parser = argparse.ArgumentParser(prog="job_alerts")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("fetch", "fetch and store new job postings"),
        ("describe", "fetch full job descriptions for new postings"),
        ("classify", "classify new job postings with the LLM"),
        ("prioritize", "apply priority rules from the config"),
        ("leads", "create or update leads from prioritized postings"),
        ("digest", "build and send the digest email"),
        ("sync", "two-way sync between leads and the Google Sheet"),
        ("run", "fetch, describe, classify, prioritize, build leads, send and sync, in one go"),
        ("people-find", "search for new people matching the target titles"),
        ("people-digest", "build and send the weekly people email"),
        ("people-sync", "two-way sync between people and the People tab"),
        ("contacts", "find contacts and emails for leads and people ticked in the sheet"),
        ("lookup", "find emails for the LinkedIn links pasted in the Manual Lookup tab"),
        ("costs", "update the Costs tab (spend per week and month, cost per lead)"),
        ("people-run", "find people, send the weekly email, then sync the People tab")
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--client", required=True)
        if name in ("digest", "people-digest"):
            cmd.add_argument("--dry-run", action="store_true", help="save the HTML without sending")

    args = parser.parse_args()
    usage.set_context(args.client, args.command)       # search costs are logged per client and command

    if args.command == "fetch":
        collect(args.client)
    elif args.command == "describe":
        describe(args.client)
    elif args.command == "classify":
        classify(args.client)
    elif args.command == "prioritize":
        prioritize(args.client)
    elif args.command == "leads":
        build_leads(args.client)
    elif args.command == "digest":
        send_digest(args.client, dry_run=args.dry_run)
    elif args.command == "sync":
        sync(args.client)
    elif args.command == "run":
        collect(args.client)
        describe(args.client)
        classify(args.client)
        prioritize(args.client)
        build_leads(args.client)
        send_digest(args.client)
        sync(args.client)
    elif args.command == "people-find":
        find_people(args.client)
    elif args.command == "people-digest":
        send_people_digest(args.client, dry_run=args.dry_run)
    elif args.command == "people-sync":
        people_sync(args.client)
    elif args.command == "contacts":
        contacts(args.client)
    elif args.command == "lookup":
        lookup(args.client)
    elif args.command == "people-run":
        find_people(args.client)
        send_people_digest(args.client)
        people_sync(args.client)
    elif args.command == "costs":
        write_costs(args.client)

    # Runs that spend money also refresh the Costs tab (a problem there never fails the run)
    if args.command in ("run", "people-run", "contacts"):
        try:
            write_costs(args.client)
        except Exception as e:
            print(f"[{args.client}] costs tab not updated: {e}")


if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#