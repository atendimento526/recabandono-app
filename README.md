# Recuperação de Abandono — Nuvemshop

App público para a Nuvemshop que detecta abandonos de checkout e envia mensagens de recuperação via WhatsApp (Z-API) com cupom de desconto.

---

## 1. Instalar dependências

```bash
pip install -r requirements.txt --break-system-packages
```

---

## 2. Configurar variáveis de ambiente

Copie o arquivo de exemplo e preencha com seus dados:

```bash
cp .env.exemplo .env
nano .env
```

Variáveis:

| Variável | Descrição |
|---|---|
| `NUVEMSHOP_APP_ID` | ID do app no portal de parceiros |
| `NUVEMSHOP_CLIENT_SECRET` | Client Secret do app |
| `APP_BASE_URL` | URL pública do servidor, sem barra final (ex: `https://meuip.com`) |
| `SECRET_KEY` | Chave aleatória para segurança de sessão |

---

## 3. Iniciar o servidor

```bash
bash start.sh
```

O servidor sobe na porta **8001**. Acesse `http://localhost:8001/` para ver o health check.

---

## 4. Reinício automático com cron

Para reiniciar o app automaticamente se o servidor cair, adicione ao cron:

```bash
crontab -e
```

Cole a linha abaixo (verifica a cada minuto se o processo está rodando):

```
* * * * * pgrep -f "uvicorn main:app" || bash /root/abandono-app/start.sh >> /root/abandono-app/abandono.log 2>&1
```

---

## 5. Registrar o app no portal de parceiros

Acesse [partners.nuvemshop.com.br](https://partners.nuvemshop.com.br) e crie um novo app com as seguintes URLs:

| Campo | Valor |
|---|---|
| **URL de callback OAuth** | `{APP_BASE_URL}/auth/install` |
| **URL do webhook de abandono** | `{APP_BASE_URL}/webhook/abandoned` |

Após criar o app, copie o **App ID** e o **Client Secret** para o seu `.env`.

---

## 6. Fluxo de instalação pelo lojista

1. O lojista clica em "Instalar" na App Store da Nuvemshop
2. Autoriza o app via OAuth
3. É redirecionado para `/painel/{store_id}`
4. Preenche as credenciais da Z-API e configura o cupom
5. O app começa a monitorar abandonos automaticamente

---

## 7. Estrutura de arquivos

```
abandono-app/
├── main.py          # FastAPI — endpoints principais
├── database.py      # SQLModel — modelos e helpers do banco
├── oauth.py         # OAuth Nuvemshop e registro de webhooks
├── webhooks.py      # Processamento de webhooks de abandono
├── scheduler.py     # APScheduler — agendamento de envios
├── whatsapp.py      # Integração Z-API
├── templates/       # Jinja2 HTML templates
├── static/          # CSS
├── abandono.db      # Banco SQLite (criado automaticamente)
├── .env             # Variáveis de ambiente (criar a partir de .env.exemplo)
├── requirements.txt
└── start.sh
```

---

## 8. Endpoints

| Método | Path | Descrição |
|---|---|---|
| GET | `/` | Health check |
| GET | `/auth/install` | Callback OAuth pós-autorização |
| GET | `/painel/{store_id}` | Painel de configuração da loja |
| POST | `/painel/{store_id}/config` | Salvar configurações |
| POST | `/webhook/abandoned` | Receber webhooks da Nuvemshop |
| GET | `/sucesso` | Página de instalação concluída |
| GET | `/erro` | Página de erro |
