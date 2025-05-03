# check_policies.ps1
Write-Host "🚀 Checking all AI agent YAML policies in /templates..."

# Récupère l'interpréteur Python du venv actif Poetry
$poetryEnv = poetry env info --path
$python = Join-Path $poetryEnv "Scripts\python.exe"

# Exécute le validateur
& $python "app/static/agents/validate_policies.py" "app/static/agents/templates"

