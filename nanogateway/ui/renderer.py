from pathlib import Path
from string import Template

TEMPLATE_DIR = Path(__file__).parent / "templates"


def render(template_path: str, **context: object) -> str:
    template = Template((TEMPLATE_DIR / template_path).read_text(encoding="utf-8"))
    return template.safe_substitute({key: str(value) for key, value in context.items()})
