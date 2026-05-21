# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.1.3] - 2026-05-21

### Alterado

- Bump `uv_build` requirement de `>=0.9.17,<0.10.0` para `>=0.11.15,<0.12.0` — traz fixes de segurança upstream:
  - [GHSA-3cv2-h65g-fgmm](https://github.com/astral-sh/tokio-tar/security/advisories/GHSA-3cv2-h65g-fgmm) (TAR parser differential)
  - [GHSA-4gg8-gxpx-9rph](https://github.com/astral-sh/uv/security/advisories/GHSA-4gg8-gxpx-9rph) (entry points escaping scripts dir)

### Adicionado

- `.github/dependabot.yml` — configuração weekly para `uv` e `github-actions` (mesmo padrão das outras libs do time).
