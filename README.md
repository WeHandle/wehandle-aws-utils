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

## Estrutura do Projeto

```
automation-aws-utils/
├── src/
│   └── automation_aws_utils/
│       ├── __init__.py
│       └── py.typed
├── pyproject.toml
└── README.md
```
