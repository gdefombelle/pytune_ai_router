# pytune_ai_router
PyTune AI Router
🚀 Microservice FastAPI pour router les agents de conversation AI de PyTune.

✨ Fonctionnalités principales
Chargement dynamique des politiques de dialogue (.yml).

Évaluation intelligente du contexte utilisateur.

Réponse structurée : message + suggestions d'actions.

Architecture modulaire : facile d'ajouter de nouveaux agents.

📂 Structure du projet
bash
Copy
Edit
pytune_ai_router/
├── app/
│   ├── agents/           # Fichiers de policies YAML (ex: welcome_agent.yml)
│   ├── core/             # Cœur du moteur de dialogue (context resolver, policy loader, policy engine)
│   ├── models/           # Modèles Pydantic : UserContext, Policy, ConversationStep, etc.
│   ├── routers/          # Routes FastAPI (ex: /ai/welcome_agent/start)
│   ├── main.py           # Démarrage FastAPI avec Lifespan
│   └── __init__.py
├── run.py                # Script pour lancer Uvicorn
├── Dockerfile            # Dockerisation du microservice
├── deploy_ai_router.ps1  # Script de build et de déploiement Docker
├── README.md             # (ce fichier)
🚀 Lancer en local
bash
Copy
Edit
python run.py
Service disponible sur :

arduino
Copy
Edit
http://localhost:8006
🔗 Principales routes API
Méthode	URL	Description
POST	/ai/welcome_agent/start	Lance le Welcome Agent pour guider l'utilisateur après login
🔥 Exemple de retour de /ai/welcome_agent/start
json
Copy
Edit
{
  "message": "I'd love to know more about your piano. Could you describe it to me?",
  "actions": [
    {
      "suggest_action": "Describe my piano",
      "route_to": "/pianos"
    }
  ],
  "meta": {}
}
🛠️ Technologies utilisées
FastAPI (backend)

Pydantic (modèles de données)

HTTPx (requêtes inter-microservices)

Docker (déploiement)

🧠 Fonctionnement général
Le frontend appelle /ai/welcome_agent/start.

Le router welcome_agent_router.py :

Récupère le contexte utilisateur via context_resolver.py.

Charge et évalue la politique YAML via policy_loader.py.

Retourne un message + actions adaptées à l'utilisateur.

Le frontend affiche dynamiquement le message et les options.

📈 Prochaines évolutions prévues
Déploiement d'autres agents (diagnosis_agent, tuning_agent, etc).

Support multilingue (anglais, français).

Gestion avancée des erreurs et fallback AI.

Ajout de méta-données conversationnelles pour enrichir l'expérience.

📝 Notes techniques
Le UserContext est obtenu depuis le microservice pytune_user.

Pas d'accès direct à PostgreSQL depuis ce microservice.

Les politiques (*.yml) permettent d'ajouter de nouveaux agents sans coder.

👨‍💻 Auteurs
Gabriel (Product & Dev Owner)

PyTune AI Core Team

PyTune AI Router fait partie de la plateforme PyTune, dédiée à l'accordage, diagnostic et maintenance assistée des pianos via IA.

