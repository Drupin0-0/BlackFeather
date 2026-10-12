# Sincrow

Aplicação web para organizar projetos, tarefas e comunicação de equipes. O projeto usa Django, Django REST Framework e Django Channels.

## Configuração

O projeto lê variáveis do arquivo `.env` na raiz. Nunca versionar segredos. Configure, no mínimo, as credenciais do banco e `SECRET_KEY`; use `DEBUG=True` somente em desenvolvimento.

Variáveis adicionais para a publicação:

| Variável | Uso |
| --- | --- |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por vírgula. |
| `CSRF_TRUSTED_ORIGINS` | Origens HTTPS confiáveis, separadas por vírgula. |
| `SECURE_SSL_REDIRECT` | Ativa redirecionamento HTTPS quando o proxy/servidor estiver configurado corretamente. |
| `SECURE_COOKIES` | Marca cookies de sessão e CSRF como seguros em HTTPS. |
| `SECURE_HSTS_SECONDS` | HSTS em segundos; habilite somente após confirmar HTTPS em todos os subdomínios aplicáveis. |
| `SUPPORT_EMAIL` | Canal público de suporte; se vazio, usa `EMAIL_REMETENTE`. |
| `DATA_CONTROLLER_NAME` | Nome legal do controlador/responsável pelo tratamento de dados. |
| `DATA_CONTROLLER_CONTACT` | Canal de privacidade para solicitações dos titulares; se vazio, usa `SUPPORT_EMAIL`. |
| `N8N_WEBHOOK_URL` | Integração opcional de automação; consulte o aviso de privacidade antes de ativar. |

## Antes de disponibilizar publicamente

- Preencha a identidade e o contato do controlador, o contato de suporte e os dados jurídicos da organização. As páginas de privacidade e termos são textos-base, não parecer jurídico.
- Revise bases legais, prazos de retenção e exclusão, fornecedores/suboperadores, transferências internacionais, contratos e o fluxo de atendimento aos direitos previstos na LGPD com assessoria adequada.
- Documente e valide quais dados são enviados aos fornecedores de e-mail, Google OAuth e n8n. Não ative integrações externas sem avaliação e transparência adequadas.
- Configure `DEBUG=False`, `SECRET_KEY` forte e exclusiva, hosts/origens corretos, HTTPS e cookies seguros. Revise a checklist do Django para deployment antes de produção.
- Substitua configurações locais de banco, servidor ASGI/WSGI e canal do Django Channels por serviços de produção adequados; não use senhas de exemplo nem o servidor de desenvolvimento.
- Execute a suíte de testes e verificações de segurança, teclado, leitor de tela, contraste, dispositivos móveis, recuperação de conta, exclusão e permissões antes de cada lançamento.

Esses passos são uma lista de preparação técnica e não certificam conformidade legal ou segurança absoluta.