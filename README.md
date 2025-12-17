# automation-aws-utils

Biblioteca Python interna para utilitários relacionados a AWS do time de automação.

## Requisitos

- Python >= 3.11
- uv (gerenciador de pacotes)

## Instalação

Para desenvolvimento:

```bash
uv sync --dev
```

Para uso em produção:

```bash
uv pip install .
```

## Desenvolvimento

### Ferramentas

- **pytest**: Framework de testes
- **ruff**: Linter e formatador de código
- **mypy**: Verificação estática de tipos

### Executar testes

```bash
uv run pytest
```

### Verificar código

```bash
uv run ruff check src/
uv run mypy src/
```

### Formatar código

```bash
uv run ruff format src/
```

## Funcionalidades Atuais

### Utilitários de S3

O módulo `automation_aws_utils.s3_utils` centraliza operações comuns com o Amazon S3
e expõe funções com tolerância a falhas típicas (timeouts, `AccessDenied`, `NoSuchKey`):

```python
from automation_aws_utils import s3_utils

local_path = s3_utils.download_file_from_s3("meu-bucket", "dados/arquivo.csv", "/tmp/arquivo.csv")
s3_utils.upload_file_to_s3(local_path, "meu-bucket-processado", "outputs/arquivo.csv")
metadata = s3_utils.get_object_metadata("meu-bucket", "dados/arquivo.csv")
```

As funções disparam exceções específicas (`S3FileNotFoundError`, `S3AccessDeniedError`,
`S3DownloadError`, `S3UploadError`) para que o chamador possa decidir se deve agendar
um retry ou tratar como falha definitiva.

### AWS Secrets Manager

O módulo `automation_aws_utils.secrets_manager` encapsula o fluxo recorrente de buscar
segredos (como credenciais do Google) e salvá-los no disco com permissões restritas:

```python
from automation_aws_utils import secrets_manager

google_creds = secrets_manager.fetch_secret_json("acesso-google")
secrets_manager.write_secret_to_file("acesso-google", "/tmp/google.json")
```

Exceções específicas (`SecretNotFoundError`, `SecretAccessDeniedError`,
`SecretDecryptionError`) ajudam o serviço a decidir se deve reprocessar o evento ou falhar
definitivamente.

## Publicação do Pacote

A action `.github/workflows/publish.yml` executa lint (`ruff`), testes (`pytest`), build e
publicação do pacote sempre que um release é publicado ou manualmente via `workflow_dispatch`.
Antes de disparar releases, configure os seguintes secrets no repositório/ambiente:

- `WEHANDLE_PYPI_URL`: Endpoint do registry privado da organização (ex.: GitHub Packages).
- `WEHANDLE_PYPI_TOKEN`: Token com permissão de publicação no registry (scope `packages:write`).

Fluxo sugerido para lançar uma nova versão interna:

1. Atualize `pyproject.toml` / `__version__`.
2. Crie um release tagueado (ex.: `v0.2.0`) pelo GitHub.
3. A action será executada automaticamente e publicará o pacote usando as credenciais acima.
