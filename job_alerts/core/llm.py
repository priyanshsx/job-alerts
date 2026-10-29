#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import hashlib 
import json 
import os 
import re 
from datetime import datetime, timezone 
from typing import TypeVar 
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from job_alerts.core.db import ROOT, get_conn
#--------------------------------------------------------------#

# Global variables 
load_dotenv(ROOT / ".env")   
MODEL = os.environ["LLM_MODEL"]
PRICE_IN = float(os.getenv("LLM_PRICE_INPUT_PER_MTOK") or 0)
PRICE_OUT = float(os.getenv("LLM_PRICE_OUTPUT_PER_MTOK") or 0)
_client = OpenAI(
    base_url="https://api.unoblox.ai/v1",
    api_key=os.environ["UNOBLOX_API_KEY"],
)
T = TypeVar("T", bound=BaseModel)
#--------------------------------------------------------------#

# Gets the current time 
def _now() -> str: 
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

# 
def _cache_key(prompt: str, schema: type[BaseModel]) -> str:
    shape = json.dumps(schema.model_json_schema(), sort_keys=True)
    return hashlib.sha256(f"{MODEL}|{shape}|{prompt}".encode()).hexdigest()
#--------------------------------------------------------------#

# Gets the json file 
def _extract_json(text: str):
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return json.loads(match.group(1) if match else text.strip())
#--------------------------------------------------------------#

# Computes the cost of each call from llm 
def _log_cost(conn, task: str, client_id: int, usage) -> None:
    cost = (usage.prompt_tokens * PRICE_IN + usage.completion_tokens * PRICE_OUT) / 1_000_000
    conn.execute(
        "INSERT INTO llm_calls (client_id, task, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (client_id, task, usage.prompt_tokens, usage.completion_tokens, cost, _now()),
    )
#--------------------------------------------------------------#

# Calls the LLM 
def call_llm(task: str, prompt: str, schema: type[T], client_id: int, max_tokens: int = 1500, retries: int = 2) -> T:
    conn = get_conn()
    key = _cache_key(prompt, schema)

    row = conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
    if row:
        conn.close()
        return schema.model_validate_json(row["response"])

    messages = [{
        "role": "user",
        "content": f"{prompt}\n\nRespond with JSON only, matching this JSON schema:\n"
                    f"{json.dumps(schema.model_json_schema())}"
    }]

    # calls validates and retries if the output is invalid 
    last_error = None 
    for _ in range(retries + 1):
        resp = _client.chat.completions.create(
            model=MODEL, max_tokens=max_tokens, messages=messages,
        )
        text = resp.choices[0].message.content or ""
        _log_cost(conn, task, client_id, resp.usage)
        try:
            result = schema.model_validate(_extract_json(text))
            break
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That JSON was invalid: {e}. Return corrected JSON only."}
            ]
    else:
        conn.commit()
        conn.close()
        raise RuntimeError(f"[{task}] invalid output after {retries + 1} attempts: {last_error}")

    conn.execute(
        "INSERT INTO llm_cache (key, task, response, created_at) VALUES (?, ?, ?, ?)"
        "ON CONFLICT (key) DO UPDATE SET response = excluded.response, created_at = excluded.created_at",
        (key, task, result.model_dump_json(), _now())
    )
    conn.commit()
    conn.close()
    return result 
#--------------------------------------------------------------#