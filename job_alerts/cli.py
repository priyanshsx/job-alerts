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
from job_alerts.outreach import draft_outreach, run_outreach, send_test, report
from job_alerts.costs import write_costs
from job_alerts import enrich
from job_alerts.research import run as research
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
        ("lookup", "turn the Manual Lookup tab (links and/or domains) into leads and find their emails"),
        ("outreach-draft", "draft emails for leads ticked Reach out (Outreach tab)"),
        ("outreach", "read replies, then send at most one approved email (run from cron)"),
        ("outreach-test", "send the newest draft to yourself to test the mailbox"),
        ("outreach-report", "replies per email type"),
        ("costs", "update the Costs tab (spend per week and month, cost per lead)"),
        ("people-run", "find people, send the weekly email, then sync the People tab")
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--client", required=True)
        if name in ("digest", "people-digest"):
            cmd.add_argument("--dry-run", action="store_true", help="save the HTML without sending")
        if name == "outreach-test":
            cmd.add_argument("--to", required=True, help="your own address")

    cmd = sub.add_parser("enrich", help="crawler: domains and emails for leads (all clients; run from cron)")
    cmd.add_argument("--client", help="one client only (default: all clients with a sheet)")
    cmd.add_argument("--all", action="store_true", help="all clients (the default)")
    cmd.add_argument("--minutes", type=float, default=8, help="stop taking new leads after this long")

    cmd = sub.add_parser("research", help="research notes: recent company updates for leads with an email")
    cmd.add_argument("--client", required=True)
    cmd.add_argument("--lead", type=int, help="one lead only, even if it isn't due")
    cmd.add_argument("--minutes", type=float, default=8, help="stop taking new leads after this long")
    cmd.add_argument("--rematch", action="store_true", help="re-apply the keywords to pages already read")

    args = parser.parse_args()
    if args.command == "research":
        usage.set_context(args.client, "research")
        research.run(args.client, lead_id=args.lead, minutes=args.minutes, rematch=args.rematch)
        return
    if args.command == "enrich":
        enrich.run([args.client] if args.client else None, minutes=args.minutes)
        return
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
    elif args.command == "outreach-draft":
        draft_outreach(args.client)
    elif args.command == "outreach":
        run_outreach(args.client)
    elif args.command == "outreach-test":
        send_test(args.client, args.to)
    elif args.command == "outreach-report":
        report(args.client)
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