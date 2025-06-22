Write-Host "🚀 Checking all AI agent YAML policies in /templates..."

# Récupère l’interpréteur Python du venv Poetry
$python = (poetry env info --path) + "\Scripts\python.exe"

# Lance le validateur
& $python "app/static/agents/validate_policies.py"
