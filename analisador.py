import os
import subprocess
import re
import csv
import shutil
import logging
from functools import wraps

# ===============================
# Configuração de logs
# ===============================
logging.basicConfig(
    filename='erros.log',
    level=logging.INFO,  # registra INFO, WARNING e ERROR
    format='[%(asctime)s] %(levelname)s - %(message)s'
)

class CloneError(Exception):
    """Erro personalizado para falhas de clonagem."""
    pass

def handle_error(func=None, *, context=""):
    """
    Função central de tratamento de erros.
    Pode ser usada diretamente OU como decorator.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                mensagem = f"Erro ao {context}: {e}" if context else f"Erro: {e}"
                print(mensagem)
                logging.error(mensagem)
                return None  # garante que o fluxo continue sem quebrar
        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)

# ===============================
# Funções principais
# ===============================

@handle_error(context="clonar lista de repositórios")
def fetch_repositories(urls, destination):
    resultados_csv = []
    for url in urls:
        if not re.match(r"^https://.+\.git$", url):
            raise CloneError(f"A URL '{url}' não está no formato correto.")
        repository_data = fetch_repository(url, destination)
        if repository_data:
            resultados_csv.append(repository_data)

    subprocess.run(["git", "credential-cache", "--exit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    gerar_csv(resultados_csv, destination)

@handle_error(context="clonar o repositório")
def fetch_repository(url, destination):
    repository_name = re.sub(r'\.git$', '', os.path.basename(url))
    repository_dir = os.path.join(destination, repository_name)

    print("\n" + "="*60)
    print(f" Iniciando análise do repositório: {repository_name}")
    print("="*60 + "\n")
    logging.info(f"Iniciando análise do repositório: {repository_name}")

    if os.path.exists(repository_dir):
        msg = f"Repositório '{repository_name}' já existe. Pulando clonagem."
        print(msg)
        logging.warning(msg)
        return None

    subprocess.run(["git", "clone", "--config", "http.sslVerify=false", url, repository_dir], check=True)
    print(f"Repositório '{repository_name}' clonado com sucesso.")
    logging.info(f"Repositório '{repository_name}' clonado com sucesso.")

    data = generate_report(repository_name, repository_dir)
    cleanup_repository(repository_dir)

    print("\n" + "-"*60)
    print(f" Análise concluída para: {repository_name}")
    print("-"*60 + "\n")
    logging.info(f"Análise concluída para: {repository_name}")

    return data

@handle_error(context="gerar relatório")
def generate_report(repository_name, directory):
    report_data = {"repositorio": repository_name}
    extensions = ['.json', '.xml', '.config']
    keywords = ['pwd', 'usr', 'username', 'password', 'usuario', 'senha', 'UserSecret', 'Catalog']
    jwt_regex = r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'

    for keyword in keywords:
        report_data[keyword] = 0
    report_data['jwt_tokens'] = 0

    relatorio_path = os.path.join(directory, "relatorio.txt")
    ocorrencias_encontradas = False

    keywords_pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)

    with open(relatorio_path, 'w', encoding='utf-8') as relatorio:
        relatorio.write("="*70 + "\n")
        relatorio.write(f" RELATÓRIO DE ANÁLISE - {repository_name}\n")
        relatorio.write("="*70 + "\n\n")

        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.endswith(ext) for ext in extensions):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()

                            for line_num, line in enumerate(file_content.splitlines(), start=1):
                                if keywords_pattern.search(line):
                                    ocorrencias_encontradas = True
                                    encontrados = []
                                    for keyword in keywords:
                                        if re.search(re.escape(keyword), line, re.IGNORECASE):
                                            report_data[keyword] += 1
                                            encontrados.append(keyword)

                                    # Saída formatada
                                    relatorio.write(f"[Arquivo]   {path}\n")
                                    relatorio.write(f"[Linha]     {line_num}\n")
                                    relatorio.write(f"[Achados]   {', '.join(encontrados)}\n")
                                    relatorio.write(f"[Conteúdo]  {line.strip()}\n")
                                    relatorio.write("-"*60 + "\n")

                            jwt_matches = re.findall(jwt_regex, file_content)
                            if jwt_matches:
                                ocorrencias_encontradas = True
                                report_data['jwt_tokens'] += len(jwt_matches)
                                for token in jwt_matches:
                                    for line_num, line in enumerate(file_content.splitlines(), start=1):
                                        if token in line:
                                            relatorio.write(f"[Arquivo]   {path}\n")
                                            relatorio.write(f"[Linha]     {line_num}\n")
                                            relatorio.write("[Achados]   TOKEN JWT\n")
                                            relatorio.write(f"[Conteúdo]  {token}\n")
                                            relatorio.write("-"*60 + "\n")
                                            break
                    except Exception as e:
                        mensagem = f"Erro ao ler o arquivo {path}: {e}"
                        print(mensagem)
                        logging.error(mensagem)

    if ocorrencias_encontradas:
        print(f"Relatório gerado: {relatorio_path}")
        logging.info(f"Relatório gerado: {relatorio_path}")
    else:
        os.remove(relatorio_path)
        logging.info(f"Nenhuma ocorrência encontrada no repositório '{repository_name}'.")

    return report_data

@handle_error(context="gerar CSV")
def gerar_csv(dados, destino):
    if not dados:
        print("Nenhum dado para gerar CSV.")
        logging.warning("Tentativa de gerar CSV sem dados.")
        return

    csv_path = os.path.join(destino, "relatorio_resumo.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=dados[0].keys(), delimiter=';')
        writer.writeheader()
        writer.writerows(dados)
    print(f"\n📄 Resumo salvo em: {csv_path}\n")
    logging.info(f"Resumo CSV salvo em: {csv_path}")

@handle_error(context="limpar repositório")
def cleanup_repository(directory):
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if item != "relatorio.txt":
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                try:
                    os.remove(item_path)
                except Exception as e:
                    mensagem = f"Erro ao remover {item_path}: {e}"
                    print(mensagem)
                    logging.error(mensagem)
    print(f"🧹 Repositório '{directory}' limpo. Apenas relatorio.txt mantido.")
    logging.info(f"Repositório '{directory}' limpo.")

# ===============================
# Execução principal
# ===============================
if __name__ == "__main__":
    base_directory = input("Digite o diretório base para clonar os repositórios: ").strip()

    if not os.path.isdir(base_directory):
        handle_error(context="validar diretório base")(lambda: (_ for _ in ()).throw(CloneError("Diretório de destino inválido.")))()
    else:
        # ✅ Lista de repositórios definida no código
        repository_urls = [
            "https://github.com/ThacioSantana/Analise_de_Repositorios.git"
        ]

        fetch_repositories(repository_urls, base_directory)
