import hashlib
import json
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.utils import timezone


class GitHubRepositoryError(Exception):
    """Erro ao validar ou consultar um repositório público do GitHub."""


def parse_github_repository_url(value):
    """Valida uma URL do GitHub e retorna (proprietário, repositório)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Informe a URL de um repositório do GitHub.')

    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != 'https'
        or parsed.netloc.lower() != 'github.com'
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError('Use uma URL HTTPS no formato https://github.com/usuario/repositorio.')

    parts = [part for part in parsed.path.strip('/').split('/') if part]
    if len(parts) != 2:
        raise ValueError('A URL deve apontar diretamente para um repositório do GitHub.')

    owner, repository = parts
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', owner):
        raise ValueError('O nome de usuário ou organização do GitHub não é válido.')

    if repository.lower().endswith('.git'):
        repository = repository[:-4]
    if (
        not repository
        or repository in {'.', '..'}
        or not re.fullmatch(r'[A-Za-z0-9._-]+', repository)
    ):
        raise ValueError('O nome do repositório do GitHub não é válido.')

    return owner, repository


def get_repository_activity(repository_url):
    """Retorna até 100 commits recentes e a contagem por autor do repositório público."""
    owner, repository = parse_github_repository_url(repository_url)
    cache_key = 'github:commits:' + hashlib.sha256(
        f'{owner.lower()}/{repository.lower()}'.encode('utf-8')
    ).hexdigest()
    cached_activity = cache.get(cache_key)
    if cached_activity is not None:
        return cached_activity

    api_url = (
        f'https://api.github.com/repos/{quote(owner, safe="")}/'
        f'{quote(repository, safe="")}/commits?per_page=100'
    )
    request = Request(
        api_url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Sincrow-Project-Activity',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        if error.code == 404:
            raise GitHubRepositoryError(
                'Repositório não encontrado ou privado. Esta versão aceita apenas repositórios públicos.'
            ) from error
        if error.code in {403, 429}:
            raise GitHubRepositoryError(
                'O GitHub limitou temporariamente as consultas. Tente novamente mais tarde.'
            ) from error
        raise GitHubRepositoryError('O GitHub não conseguiu consultar este repositório.') from error
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubRepositoryError(
            'Não foi possível conectar à API do GitHub agora. Tente novamente mais tarde.'
        ) from error

    if not isinstance(payload, list):
        raise GitHubRepositoryError('O GitHub retornou uma resposta inesperada.')

    commits = []
    contributors = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        commit_data = item.get('commit') or {}
        author_data = commit_data.get('author') or {}
        github_author = item.get('author') or {}
        author_name = (github_author.get('login') or author_data.get('name') or 'Autor desconhecido').strip()
        message = (commit_data.get('message') or '').splitlines()[0][:180]
        date = author_data.get('date') or ''
        html_url = item.get('html_url') or ''
        if not html_url.startswith('https://github.com/'):
            continue

        commit = {
            'author': author_name,
            'message': message or 'Commit sem mensagem',
            'date': date,
            'url': html_url,
        }
        commits.append(commit)

        contributor = contributors.setdefault(author_name, {
            'name': author_name,
            'login': github_author.get('login') or '',
            'count': 0,
            'latest_commit': date,
            'latest_message': message or 'Commit sem mensagem',
            'latest_url': html_url,
        })
        contributor['count'] += 1

    contributor_rows = sorted(
        contributors.values(),
        key=lambda row: (-row['count'], row['name'].lower()),
    )[:10]
    total = len(commits)
    activity = {
        'success': True,
        'repository': f'{owner}/{repository}',
        'commits': commits[:8],
        'contributors': contributor_rows,
        'total_commits': total,
        'contributors_count': len(contributors),
        'sample_limit': 100,
    }
    cache.set(cache_key, activity, 300)
    return activity


def get_open_pull_request_activity(repository_url):
    """Resume PRs abertas e destaca pedidos de revisão e itens parados há 72h."""
    owner, repository = parse_github_repository_url(repository_url)
    cache_key = 'github:pull-requests:' + hashlib.sha256(
        f'{owner.lower()}/{repository.lower()}'.encode('utf-8')
    ).hexdigest()
    cached_activity = cache.get(cache_key)
    if cached_activity is not None:
        return cached_activity

    api_url = (
        f'https://api.github.com/repos/{quote(owner, safe="")}/'
        f'{quote(repository, safe="")}/pulls?state=open&per_page=30'
    )
    request = Request(
        api_url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Sincrow-Review-Flow',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        if error.code == 404:
            raise GitHubRepositoryError(
                'Não foi possível consultar PRs: repositório inexistente ou privado.'
            ) from error
        if error.code in {403, 429}:
            raise GitHubRepositoryError(
                'O GitHub limitou temporariamente a consulta de PRs. Tente novamente mais tarde.'
            ) from error
        raise GitHubRepositoryError('O GitHub não conseguiu consultar as PRs deste repositório.') from error
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubRepositoryError(
            'Não foi possível conectar à API do GitHub para consultar as PRs.'
        ) from error

    if not isinstance(payload, list):
        raise GitHubRepositoryError('O GitHub retornou uma resposta inesperada para as PRs.')

    now = timezone.now()
    pull_requests = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        html_url = item.get('html_url') or ''
        if not html_url.startswith(f'https://github.com/{owner}/{repository}/pull/'):
            continue

        updated_at = item.get('updated_at') or ''
        try:
            parsed_updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            age_hours = max(0, int((now - parsed_updated_at).total_seconds() // 3600))
        except (TypeError, ValueError):
            age_hours = 0

        requested_reviewers = item.get('requested_reviewers') or []
        requested_reviewers = [
            reviewer.get('login') or reviewer.get('name')
            for reviewer in requested_reviewers
            if isinstance(reviewer, dict) and (reviewer.get('login') or reviewer.get('name'))
        ]
        head = item.get('head') or {}
        user = item.get('user') or {}
        pull_requests.append({
            'number': item.get('number'),
            'title': (item.get('title') or 'Pull request sem título')[:180],
            'url': html_url,
            'author': (user.get('login') or 'Autor desconhecido')[:80],
            'branch': ((head.get('ref') or 'branch desconhecida')[:100]),
            'draft': bool(item.get('draft')),
            'created_at': item.get('created_at') or '',
            'updated_at': updated_at,
            'age_hours': age_hours,
            'stale': age_hours >= 72,
            'requested_reviewers': requested_reviewers[:8],
        })

    pull_requests.sort(key=lambda item: (-item['age_hours'], item['number'] or 0))
    activity = {
        'success': True,
        'pull_requests': pull_requests[:20],
        'open_count': len(payload),
        'review_requested_count': sum(bool(item['requested_reviewers']) for item in pull_requests),
        'stale_count': sum(item['stale'] and not item['draft'] for item in pull_requests),
        'sample_limit': 30,
    }
    cache.set(cache_key, activity, 300)
    return activity
