from string import Template

def interpolate_yaml(template: str, context: dict) -> str:
    return Template(template).safe_substitute(context or {})
