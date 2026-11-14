#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.llm import call_llm
#--------------------------------------------------------------#

# Global variables
DESCRIPTION_CHARS = 4000   # how much of each description the LLM reads (keeps cost down)
#--------------------------------------------------------------#

# Output shape the LLM must return
class PostingClassification(BaseModel):
    is_relevant: bool
    employer_type: Literal["manufacturer_supplier", "consultancy", "large_enterprise",
                           "other_industry", "agency", "unknown"]
    role_type: Literal["project", "lead", "routine", "other"]
    erp_system: Literal["sap", "infor", "dynamics", "oracle", "other", "unknown"]
    segment: Literal["supplier", "partner", "none"]
    language_requirement: Literal["english_ok", "german_only", "unclear"]
    company_size: Literal["small", "mid", "large", "unknown"]
    employee_estimate: int | None = None
    named_customers: list[str] = []
    supplies_anchor_customer: bool
    supplier_evidence: str | None = None
    business_model: Literal["b2b", "b2c", "both", "unknown"] = "unknown"
    priority: int = Field(ge=1, le=3)
    reason: str
#--------------------------------------------------------------#

# Prompt for AI call
PROMPT = """You screen job postings for {display_name}.

What {display_name} sells: {offer}
Who they are: {positioning}
Target industries for suppliers: {industries}

Reference examples of good and bad matches:
{examples}

Classify this posting.

Title: {title}
Company: {company}
Location: {location}
Description:
{description}

Definitions:
- is_relevant: {relevance}
- employer_type:
  manufacturer_supplier = manufacturer or supplier (including pharma and contract manufacturers)
  consultancy = IT or SAP consultancy, systems integrator, ERP reseller, IT services firm or
                managed (security) service provider such as an MSSP or MDR provider
  large_enterprise = large corporation or group with more than {max_employees} employees
  other_industry = insurance, banking, utilities, public sector, retail, healthcare, etc.
  agency = staffing or recruitment agency
  unknown = cannot tell
- role_type: project (migration, implementation, transformation, architecture, or a time-bound
  contract), lead (team lead or head of a function), routine (ongoing specialist or individual
  contributor work).
- business_model: who the company sells to: b2b (businesses), b2c (consumers), both, or unknown.
- language_requirement:
  english_ok = English is the working language, OR the posting asks for English and the local
               language, OR the posting is written in English and does not demand the local language
  german_only = fluent or business-level command of the local language (German, Dutch, Spanish,
                Polish, ...) is required and English is not mentioned as sufficient (a posting
                written only in the local language with no mention of English counts)
  unclear = cannot tell
- company_size: small (<250 employees), mid (250-{max_employees}), large (>{max_employees}),
  unknown. Use what the description says (e.g. "über 1.000 Mitarbeitende"). If it states a
  number, put it in employee_estimate; otherwise null. Do not guess numbers.
- named_customers: big customers the description explicitly names (e.g. retailers, car makers).
  Only names that appear in the text. Empty list if none.
- supplies_anchor_customer: true only if a named customer is on this list: {anchors}
- supplier_evidence: the exact short phrase from the description that names the customer,
  copied word for word. Null if none.
- segment: supplier if manufacturer_supplier; partner if consultancy; otherwise none.
- priority: 1 = strong match like the reference example, 2 = possible, 3 = weak.
- reason: one short sentence in English describing the company and role (not the priority).

Never invent facts that are not in the posting."""
#--------------------------------------------------------------#

def _examples_text(examples: list[dict]) -> str:
    if not examples:
        return "(none)"
    return "\n".join(
        f"- {e.get('company')}: {e.get('verdict')}. {str(e.get('why', '')).strip()}" for e in examples
    )
#--------------------------------------------------------------#

def classify(client: str) -> None:
    cfg = load_config(client)
    supplier = next((s for s in (cfg.segments or []) if s.name == "supplier"), None)
    industries = ", ".join(supplier.industries) if supplier else "(any)"
    anchors = (getattr(cfg, "supply_chain", None) or {}).get("anchor_customers", [])
    examples = _examples_text(cfg.job_alerts.get("reference_examples", []))
    max_employees = cfg.job_alerts.get("max_employees", 3000)
    relevance = str(cfg.job_alerts.get("relevance") or (
        "true if the role is about master data, data quality or data governance in a business or "
        "ERP context. False for unrelated meanings or staffing agencies.")).strip()

    conn = get_conn()
    client_id = get_client_id(conn, client)
    max_per_run = int(cfg.job_alerts.get("max_classify_per_run", 300))     # cost guard, newest first
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE client_id = ? AND classified_at IS NULL "
        "ORDER BY created_at DESC LIMIT ?",
        (client_id, max_per_run),
    ).fetchall()
    print(f"[{client}] classifying {len(rows)} postings")

    counts = {1: 0, 2: 0, 3: 0, "irrelevant": 0}
    failed = 0
    for i, row in enumerate(rows, start=1):
        description = (row["description"] or "")[:DESCRIPTION_CHARS]
        prompt = PROMPT.format(
            display_name=cfg.display_name, offer=cfg.offer.strip(),
            positioning=cfg.positioning.strip(), industries=industries,
            examples=examples, anchors=", ".join(anchors) or "(none)",
            max_employees=max_employees, relevance=relevance,
            title=row["title"], company=row["company_name"], location=row["location"],
            description=description or "(no description available)",
        )
        try:
            result = call_llm("classify_posting", prompt, PostingClassification, client_id)
        except RuntimeError as e:
            failed += 1
            print(f"  {i}/{len(rows)}  failed: {row['title']} ({e})")
            continue
        #--------------------------------------------------------------#

        # Safety checks: keep supplier claims only if they really appear in the description
        text = description.lower()
        evidence = result.supplier_evidence
        if evidence and evidence.lower() not in text:
            evidence = None
        customers = [c for c in result.named_customers if c.lower() in text]
        supplies_anchor = bool(evidence) and any(
            a.lower() in c.lower() for c in customers for a in anchors
        )
        #--------------------------------------------------------------#

        conn.execute(
            """UPDATE job_postings SET is_relevant = ?, employer_type = ?, role_type = ?,
               erp_system = ?, segment = ?, language_requirement = ?, company_size = ?,
               employee_estimate = ?, named_customers = ?, supplies_anchor_customer = ?,
               supplier_evidence = ?, business_model = ?, priority = ?, reason = ?, classified_at = ?
               WHERE id = ?""",
            (int(result.is_relevant), result.employer_type, result.role_type,
             result.erp_system, result.segment, result.language_requirement,
             result.company_size, result.employee_estimate, ", ".join(customers),
             int(supplies_anchor), evidence, result.business_model, result.priority, result.reason,
             datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        counts[result.priority if result.is_relevant else "irrelevant"] += 1
        print(f"  {i}/{len(rows)}  {result.language_requirement:<11} {result.company_size:<7} "
              f"{'SUPPLIER ' if supplies_anchor else ''}{row['title'][:55]}")

    conn.close()
    print(f"[{client}] classified {len(rows) - failed}, failed {failed}: {counts}")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#