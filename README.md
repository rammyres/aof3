# Protocolo de Devoluções — Controle de Alvarás

Aplicação web em Python (Flask) com banco de dados SQLite para registrar
devoluções indevidas de alvarás feitas por PSOs/CENOPs, com estatísticas
e área de administração protegida por senha.

## O que tem aqui

- **Registrar** (público, sem login): lançar uma devolução — número do
  alvará (`AAAA/SSSSSSSSS`), prefixo do PSO/CENOP, motivo e data.
- **Estatísticas** (público, sem login): resumo, gráficos por motivo,
  por prefixo e por período, além do ranking geral.
- **Administração** (exige login): cadastrar/remover prefixos e
  motivos, exportar/importar backup, trocar a senha de acesso.

Só a Administração exige senha — quem só precisa registrar devolução
ou consultar estatísticas não precisa de login. Se quiser exigir login
para tudo, isso é uma mudança pequena no `app.py` (adicionar
`@login_required` nas rotas `registrar` e `estatisticas`) — me avise se
preferir assim.

## Instalação e execução local

```bash
# 1. crie um ambiente virtual (recomendado)
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. instale as dependências
pip install -r requirements.txt

# 3. rode a aplicação
python app.py
```

Acesse em `http://127.0.0.1:5000`.

Na primeira execução o sistema cria automaticamente o banco de dados
(`instance/protocolo.db`) e um usuário administrador padrão. As
credenciais aparecem **no terminal**, assim:

```
 Usuário administrador padrão criado:
   usuário: admin
   senha:   altere-esta-senha
 Entre em /admin/login e troque a senha imediatamente.
```

**Troque essa senha assim que entrar**, em Administração → Senha de
acesso.

## Onde ficam os dados

Tudo fica em `instance/protocolo.db` (SQLite), que **não** é enviado ao
Git (está no `.gitignore`). Faça backups regulares pela própria
aplicação: Administração → Backup de dados → Exportar backup (.json).
Esse arquivo permite restaurar tudo (prefixos, motivos e registros) em
outra instalação, em Importar backup.

## Hospedagem

Isso **não é mais compatível com GitHub Pages** (que só serve arquivos
estáticos). Você precisa de um servidor que execute Python. Algumas
opções comuns e gratuitas/baratas para uma ferramenta interna pequena:

- **PythonAnywhere** — bem simples para apps Flask pequenas.
- **Render** ou **Railway** — deploy direto a partir de um repositório
  Git, com plano gratuito limitado.
- Um servidor/VM da própria instituição, rodando com **gunicorn** por
  trás de um **nginx** com HTTPS.

Para produção, **não** use `python app.py` (modo debug). Use por
exemplo:

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

e coloque atrás de um proxy com HTTPS. Trafegar a senha de
administração sem HTTPS expõe a senha na rede.

## Estrutura do projeto

```
app.py                  → rotas e lógica da aplicação
schema.sql               → esquema do banco SQLite
requirements.txt         → dependências Python
templates/                → páginas HTML (Jinja2)
  base.html               → layout comum (cabeçalho, abas, mensagens)
  registrar.html
  estatisticas.html
  admin_login.html
  admin/
    prefixos.html
    motivos.html
    backup.html
    senha.html
static/css/style.css      → estilo visual
instance/                 → banco de dados (criado automaticamente, não versionado)
```

## Segurança — pontos a observar

- A senha de administração é armazenada com hash (`werkzeug.security`,
  PBKDF2), nunca em texto puro.
- A chave de sessão (`SECRET_KEY`) é gerada automaticamente e salva em
  `instance/secret.key` na primeira execução. Se quiser definir a sua
  própria, exporte a variável de ambiente `FLASK_SECRET_KEY` antes de
  rodar.
- O formulário de "apagar todos os dados" exige a senha de
  administração novamente, como segunda confirmação.
- Esta aplicação não implementa limite de tentativas de login
  (rate limiting). Para uso exposto na internet, considere colocar
  atrás de um proxy com essa proteção, ou usar `flask-limiter`.
