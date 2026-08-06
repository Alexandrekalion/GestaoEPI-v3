# GestaoEPI V3

Versao historica de sistema full stack para gestao de EPIs, entregas, colaboradores, estoque, relatorios e rastreabilidade.

## Visao geral

O GestaoEPI V3 representa uma etapa mais completa da evolucao do sistema, com modulos operacionais, relatorios, historico de entregas, controle de acesso por perfil e recursos de identificacao por QR Code e reconhecimento facial.

O repositorio deve ser apresentado como versao historica anterior as versoes V4 e 5.x.

## Problema resolvido

Operacoes com EPIs precisam controlar quem recebeu cada item, qual estoque esta disponivel, quais equipamentos estao vencidos ou proximos do vencimento e quais registros sustentam auditorias internas. Esta versao centraliza esses processos em uma aplicacao web com API dedicada.

## Publico e contexto de uso

- Seguranca do trabalho.
- Almoxarifado.
- Gestores operacionais.
- Times que precisam consultar entregas, historicos, fichas e relatorios.

## Principais funcionalidades confirmadas

- Autenticacao e perfis de usuario.
- Dashboard operacional.
- Cadastro de colaboradores, empresas, fornecedores, EPIs, ferramentas e kits.
- Controle de estoque, validade e quantidades.
- Historico de entregas.
- Geracao de relatorios e fichas em PDF.
- Exportacao/importacao identificada nas dependencias e rotas.
- Reconhecimento facial com face-api.js.
- Leitura e rastreabilidade por QR Code.
- Seeds e testes backend para cenarios operacionais.

## Como funciona

O frontend React organiza as telas do sistema e consome uma API FastAPI. O backend gerencia autenticacao, regras de acesso, cadastros, relatorios, entregas, estoque e persistencia em MongoDB.

## Tecnologias utilizadas

- Python
- FastAPI
- MongoDB
- React
- JavaScript
- Tailwind CSS
- face-api.js
- html5-qrcode
- qrcode
- ReportLab
- OpenPyXL

## Arquitetura resumida

- `backend/`: API, autenticacao, banco, schemas, seeds, relatorios e testes.
- `frontend/`: SPA React, paginas, componentes de interface, layout e modelos faciais.
- `test_reports/`: evidencias historicas de teste.
- `memory/`: anotacoes de evolucao e produto.

## Status

Versao historica mais madura que as versoes iniciais, mas ainda anterior a linha V4 e 5.x. Deve ser usada como registro da evolucao tecnica do projeto.

## Relacao com outras versoes

Esta versao sucede `GestaoEPI-v2` e antecede `GestaoEPI-V4` e os repositorios 5.x. A evolucao identificada inclui relatorios, historico operacional e maior cobertura dos fluxos de entrega.

## Limitacoes conhecidas

- Requer revisao de seguranca antes de destaque publico amplo.
- Nao ha confirmacao de ambiente de producao ativo.
- Como versao historica, pode conter artefatos e decisoes superadas por versoes posteriores.

## Participacao no desenvolvimento

O projeto evidencia atuacao em arquitetura full stack, APIs REST, interfaces administrativas, regras de negocio para seguranca do trabalho, relatorios, rastreabilidade e evolucao de produto por versoes.

## Autoria

Desenvolvido por Michele Santana — Kalion Tecnologia
