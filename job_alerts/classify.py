#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
from datetime import datetime, timezone
from typing import Literal 
from pydantic import BaseModel, Field 
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.llm import call_llm 
#--------------------------------------------------------------#

# Declares relevant classes 
class PostingClassification(BaseModel):
    is_relevant: bool 
    employer_type: Literal["manufacturer_supplier", "consultancy", "large_enterprise", "other_industry", "agency", "unknown"]
    role_type: Literal["project", "lead", "routine", "other"]
    erp_system: Literal["sap", "infor", "dynamics", "oracle", "other", "unknown"]
    segment: Literal["supplier", "partner", "none"]
    priority: int = Field(ge=1, le=3)
    reason: str 
#--------------------------------------------------------------#

# Prompt for the llm call 
PROMPT = """
            You screen German job postings for {display_name}.

            What {display_name} sells: {offer}
            Who they are: {positioning}
            Target industries for suppliers: {industries}

            Classify this posting. 

            Title: {title}
            Company: {company}
            Location: {location}

            Definitions: 
            - is_relevant: true if the role is about master data, data quality or data governance in a business or ERP context. Flase for unrelated meanings (e.g.: lab data, mobile device management) or if employer is a staffing agency.
            - employer_type:
                manufacturer_supplier = mid-sized manufacturer or supplier (roughly 50-2,000 employees)
                consultancy = IT or SAP consultancy, systems integrator or ERP reseller
                large_enterprise = large corporation or group (well-known, many thousands of employees)
                other_industry = insurance, banking, utilities, public sector, healthcare, retail, etc.
                agency = staffing or recruitment agency
                unknown = cannot tell
            - role_type:
                project = migration, implementation, transformation or architecture role
                lead = team lead or head of a data function
                routine = ongoing clerk or specialist work (e.g. "Sachbearbeiter Stammdaten")
            - segment: supplier if employer_type is manufacturer_supplier; partner if consultancy;
                otherwise none.
            - priority:
                1 = manufacturer_supplier in a target industry with a project or lead role
                2 = manufacturer_supplier with a routine role, or a consultancy hiring master data /
                    SAP MDG people (a subcontracting lead)
                3 = everything else that is relevant
            - reason: one short sentence explaining the priority, in English.

            If you don't recognize the company, judge from the name and title, and use "unknown"
            rather than guessing a large company.
"""
#--------------------------------------------------------------#

def classify(client: str) -> None:
    cfg = load_config(client)
    supplier = next(s for s in cfg.segments if s.name == "supplier")
    industries = ", ".join(supplier.industries)

    conn = get_conn()
    client_id = get_client_id(conn, client)
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE client_id = ? AND classified_at IS NULL",
        (client_id,),
    ).fetchall()

    counts = {1: 0, 2: 0, 3: 0, "irrelevant": 0}
    for row in rows:
        prompt = PROMPT.format(
            display_name=cfg.display_name, offer=cfg.offer.strip(),
            positioning=cfg.positioning.strip(), industries=industries,
            title=row["title"], company=row["company_name"], location=row["location"]
        )

        result = call_llm("classify_posting", prompt, PostingClassification, client_id)

        conn.execute(
            """
                UPDATE job_postings SET is_relevant = ?, employer_type = ?, role_type = ?, 
                erp_system = ?, segment = ?, priority = ?, reason = ?, classified_at = ?
                WHERE id = ?
            """,
            (int(result.is_relevant), result.employer_type, result.role_type, result.erp_system, result.segment,
             result.priority, result.reason, datetime.now(timezone.utc).isoformat(), row["id"])
        )
        conn.commit()
        counts[result.priority if result.is_relevant else "irrelevant"] += 1

    conn.close()
    print(f"[{client}] classified {len(rows)}: {counts}")
    #--------------------------------------------------------------#
#---------------------end-of-code----------------------------------#