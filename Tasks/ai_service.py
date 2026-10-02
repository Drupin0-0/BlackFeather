import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Tasks.models import Task

logger = logging.getLogger(__name__)

PRIORIDADES_VALIDAS = {"low", "medium", "high"}
MAX_TAREFAS = 15


def _membros_payload(project):
    membros = project.members.all().select_related("profile").prefetch_related("profile__skills")
    payload = []
    for u in membros:
        profile = getattr(u, "profile", None)
        payload.append({
            "id": u.pk,
            "name": profile.name if profile and profile.name else u.email,
            "skills": [s.name for s in profile.skills.all()] if profile else [],
        })
    return payload


def _chamar_n8n(project, membros):
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        return None

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    secret = os.getenv("N8N_WEBHOOK_SECRET")
    if secret:
        headers["X-Webhook-Secret"] = secret

    body = {
        "project": {
            "id": project.pk,
            "title": project.title,
            "description": project.description or "",
        },
        "available_members": membros,
        "context": {"request_type": "task_generation"},
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, ValueError, TimeoutError):
        logger.exception("Falha ao chamar o webhook n8n (task_generation)")
        return None


def _validar_tarefas(data, ids_validos):
    """Nunca confia cegamente na IA: sanitiza tudo antes de gravar."""
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return []

    tarefas = []
    for item in data["tasks"][:MAX_TAREFAS]:
        if not isinstance(item, dict):
            continue
        titulo = str(item.get("title") or "").strip()[:100]
        if not titulo:
            continue

        try:
            responsavel = int(item.get("assigned_user_id"))
        except (TypeError, ValueError):
            responsavel = None
        if responsavel not in ids_validos:
            responsavel = None

        prioridade = item.get("priority")
        if prioridade not in PRIORIDADES_VALIDAS:
            prioridade = "medium"

        tarefas.append({
            "title": titulo,
            "description": str(item.get("description") or "").strip(),
            "priority": prioridade,
            "assigned_user_id": responsavel,
        })
    return tarefas


def gerar_tarefas_para_projeto(project):
    """Retorna quantas tarefas foram criadas (0 se a IA falhar)."""
    membros = _membros_payload(project)
    ids_validos = {m["id"] for m in membros}

    data = _chamar_n8n(project, membros)
    tarefas = _validar_tarefas(data, ids_validos)
    if not tarefas:
        return 0

    Task.objects.bulk_create([
        Task(
            project=project,
            title=t["title"],
            description=t["description"],
            priority=t["priority"],
            task_responsible_id=t["assigned_user_id"],
        )
        for t in tarefas
    ])
    return len(tarefas)
