#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
import yaml
from pydantic import BaseModel, ConfigDict
from job_alerts.core.db import ROOT
#--------------------------------------------------------------#

class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")

class TitleRule(Loose):
    match: list[str]
    points: int 
    persona: str 

class CompanySize(Loose):
    min: int 
    max: int 
    points: int

class Segment(Loose):
    name: str
    description: str
    priority: int 
    industries: dict[str, int]
    countries: dict[str, int] = {}
    company_size: CompanySize
    titles: list[TitleRule]
    exclude_titles: list[str] = []

class Listening(Loose):
    job_keywords: list[str]
    job_exclude_keywords: list[str] = []
    job_countries: list[str]

class Digest(Loose):
    email_to: list[str]
    max_items: int = 20 

class ClientConfig(Loose):
    client: str
    display_name: str 
    offer: str 
    positioning: str
    segments: list[Segment]
    listening: Listening
    digest: Digest 

def _deep_merge(base: dict, override: dict) -> dict: 
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value 
    return merged 

def _read_yaml(path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}

def load_config(client: str) -> ClientConfig: 
    client_file = ROOT / "config" / "clients" / client / "config.yaml"
    if not client_file.exists():
        raise FileNotFoundError(f"No config for client '{client} at {client_file}.")

    client_data = _read_yaml(client_file)
    template_name = client_data.get("template", "b2b")
    template_data = _read_yaml(ROOT / "config" / "templates" / f"{template_name}.yaml")

    return ClientConfig.model_validate(_deep_merge(template_data, client_data))
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#