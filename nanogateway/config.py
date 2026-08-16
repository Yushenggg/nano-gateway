import os
from pathlib import Path
from pydantic import BaseModel
import yaml
from dotenv import load_dotenv


class InjectionGuardrailConfig(BaseModel):
    enabled: bool = False
    action: str = "block"
    block_message: str = "Request blocked by NanoGateway: potential prompt injection detected"


class GuardrailsConfig(BaseModel):
    injection: InjectionGuardrailConfig = InjectionGuardrailConfig()


class Settings(BaseModel):
    url: str = "https://api.openai.com/v1"
    guardrails: GuardrailsConfig = GuardrailsConfig()
    db_path: str = ".nanogateway/data.db"


def _resolve_url(yaml_value: str = "https://api.openai.com/v1") -> str:
    return os.environ.get("NANOGATEWAY_URL", yaml_value)


def load_config(config_path: str | None = None) -> Settings:
    # Load .env files from project directory first, then home
    for env_path in [Path(".env"), Path.home() / ".env"]:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            break

    yaml_data: dict = {}

    if config_path:
        path = Path(config_path).expanduser()
        if path.exists():
            with open(path) as f:
                yaml_data = yaml.safe_load(f) or {}
    else:
        for candidate in [Path("nano-rules.yaml"), Path(".nanogateway/config.yaml")]:
            if candidate.exists():
                with open(candidate) as f:
                    yaml_data = yaml.safe_load(f) or {}
                break

    url = _resolve_url(yaml_data.get("url", "https://api.openai.com/v1"))

    guardrails_data = yaml_data.get("guardrails") or {}
    injection_cfg = guardrails_data.get("injection", {})
    guardrails = GuardrailsConfig(
        injection=InjectionGuardrailConfig(**injection_cfg) if injection_cfg else InjectionGuardrailConfig()
    )

    db_path = yaml_data.get("db_path", ".nanogateway/data.db")
    db_path = str(Path(db_path).expanduser())

    return Settings(
        url=url,
        guardrails=guardrails,
        db_path=db_path,
    )
