# Sistema Cipolatti - Guia de Uso

## 🔐 Aba USUÁRIOS - Para Que Serve?

A aba **Usuários** é onde você gerencia **quem pode acessar o sistema Cipolatti** e **qual o nível de permissão** de cada pessoa.

### Diferença Entre Colaborador e Usuário:

- **COLABORADOR**: É a pessoa que trabalha na empresa, recebe EPI, usa ferramentas. Está cadastrado na aba "Colaboradores" mas **NÃO tem acesso ao painel**.

- **USUÁRIO**: É alguém que vai **usar o sistema Cipolatti** (fazer login, cadastrar EPIs, registrar entregas, etc.). 

### Quando Usar a Aba Usuários:

1. **Criar login para gestores** que vão operar o sistema
2. **Definir níveis de acesso** (Super-admin, Admin, Gestor)
3. **Bloquear/desbloquear** acessos ao sistema
4. **Resetar senhas** de usuários

### Como Funciona o RBAC (Controle de Acesso):

#### **Super-Administrador** (você)
- Acesso TOTAL
- Único que pode gerenciar a licença do painel (adicionar dias)
- Pode criar outros Admins e Gestores

#### **Administrador**
- Acesso quase total
- Pode criar usuários Gestores
- Pode gerenciar todas as funcionalidades exceto a licença do painel

#### **Gestor**
- Acesso operacional completo
- Cadastra colaboradores, EPIs, ferramentas
- Faz entregas e devoluções
- NÃO pode criar outros usuários

### Exemplo Prático:

**Situação**: João é colaborador (eletricista), recebe EPIs.  
**Cadastro**: João está na aba "Colaboradores" (nome, CPF, cargo, foto)  
**Acesso ao sistema**: João NÃO precisa estar na aba "Usuários" porque ele não vai operar o sistema.

**Situação**: Maria é supervisora de segurança, vai operar o Cipolatti.  
**Cadastro**: Maria pode estar ou não na aba "Colaboradores"  
**Acesso ao sistema**: Maria PRECISA estar na aba "Usuários" com papel "Gestor" para fazer login e usar o sistema.

### Você Pode Vincular:

Quando criar um usuário, você pode vincular ele a um colaborador (campo `employee_id`). Isso é útil se a pessoa é funcionário E também opera o sistema.

---

## 📝 Páginas Implementadas

### ✅ COMPLETAS

1. **Login** - Autenticação com troca de senha obrigatória
2. **Dashboard** - Estatísticas, alertas, licença do painel
3. **Colaboradores** - Nome completo, CPF, RG, Matrícula, Empresa, Cargo, Setor, Foto (webcam ou upload)
4. **Empresas** - Cadastro completo de empresas
5. **EPIs** - TODOS os campos: fornecedor, data compra, nota fiscal, cor, validade, busca funcionando
6. **Ferramentas** - Cadastro completo com QR code, patrimônio, fornecedor
7. **Kits** - Criar kits com EPIs e Ferramentas
8. **Equipe Externa** - Cadastro de empresas terceirizadas e seus membros
9. **Documentação** - Criar modelos de documentos (termos, treinamentos)
10. **Estoque** - Alertas de estoque baixo e validade próxima
11. **Usuários** - Gerenciar acessos ao sistema (RBAC)
12. **Configurações** - Gerenciar licença do painel (Super-admin)

### ⚠️ EM DESENVOLVIMENTO

- **Entrega de EPI** - Funciona parcialmente (precisa baixar modelos do face-api.js para reconhecimento facial completo)

---

## 🎯 Próximos Passos Recomendados

1. Baixar modelos face-api.js em `/app/frontend/public/models`
2. Testar reconhecimento facial na página Entrega de EPI
3. Adicionar fornecedores antes de cadastrar EPIs
4. Migrar para MongoDB se quiser fazer deploy no Emergent

---

## 📊 Banco de Dados

**Status Atual**: PostgreSQL local funcionando
**Para Deploy**: Precisa migrar para MongoDB (Emergent não suporta PostgreSQL)
