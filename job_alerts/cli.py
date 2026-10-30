#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import argparse
from job_alerts.collect import collect
from job_alerts.classify import classify
from job_alerts.prioritize import prioritize
from job_alerts.digest import send_digest
from job_alerts.people import find_people
from job_alerts.people_digest import send_people_digest
#--------------------------------------------------------------#

def main():
    parser = argparse.ArgumentParser(prog="job_alerts")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("fetch", "fetch and store new job postings"),
        ("classify", "classify new job postings with the LLM"),
        ("prioritize", "apply priority rules from the config"),
        ("digest", "build and send the digest email"),
        ("run", "fetch, classify, prioritize and send, in one go"),
        ("people-find", "search for new people matching the target titles"),
        ("people-digest", "build and send the weekly people email"),
        ("people-run", "find people, then send the weekly email")
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--client", required=True)
        if name in ("digest", "people-digest"):
            cmd.add_argument("--dry-run", action="store_true", help="save the HTML without sending")

    args = parser.parse_args()

    if args.command == "fetch":
        collect(args.client)
    elif args.command == "classify":
        classify(args.client)
    elif args.command == "prioritize":
        prioritize(args.client)
    elif args.command == "digest":
        send_digest(args.client, dry_run=args.dry_run)
    elif args.command == "run":
        collect(args.client)
        classify(args.client)
        prioritize(args.client)
        send_digest(args.client)
    elif args.command == "people-find":
        find_people(args.client)
    elif args.command == "people-digest":
        send_people_digest(args.client, dry_run=args.dry_run)
    elif args.command == "people-run":
        find_people(args.client)
        send_people_digest(args.client)


if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#