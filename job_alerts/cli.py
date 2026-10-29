#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import argparse 
from job_alerts.collect import collect 
#--------------------------------------------------------------#

def main():
    parser = argparse.ArgumentParser(prog="job_alerts")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = sub.add_parser("fetch", help="fetch and store new job postings")
    fetch_cmd.add_argument("--client", required=True)
    args = parser.parse_args()

    if args.command == "fetch":
        collect(args.client)

if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#