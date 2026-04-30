# 📋 Dashboard de Acompanhamento Pedagógico — Check-in Mensal

Sistema desenvolvido para o Programa de Graduação QualiSaúde / UFRN, com o objetivo de monitorar o acompanhamento de alunos e facilitar a tomada de decisão pedagógica.

---

## 🚀 Funcionalidades

* Leitura automática de dados via Google Sheets
* Atualização automática a cada 5 minutos
* Visualização de indicadores (KPIs)
* Gráficos interativos (Plotly)
* Filtros por turma e orientador
* Tabela detalhada dos alunos
* Envio automático de alertas por email para orientadores

---

## 📦 Requisitos

Certifique-se de ter o Python instalado (versão 3.8 ou superior).

Instale as dependências com o comando:

```bash
pip install streamlit pandas plotly gspread google-auth
```

---

## 🔐 Configuração do Google Sheets

1. Acesse o Google Cloud Console
2. Crie um projeto
3. Ative as APIs:

   * Google Sheets API
   * Google Drive API
4. Crie uma conta de serviço
5. Gere um arquivo de credenciais (JSON)
6. Baixe o arquivo e renomeie para:

```
credenciais_google.json
```

7. Coloque esse arquivo na mesma pasta do projeto

8. Compartilhe sua planilha do Google Sheets com o email da conta de serviço

---

## ⚙️ Configuração do Projeto

No arquivo `main.py`, edite:

* `SPREADSHEET_ID`: ID da sua planilha
* `ABA_DASHBOARD`: nome da aba com dados processados
* `ABA_ALUNOS`: nome da aba com dados dos alunos

### 📧 Configuração de Email (opcional)

Para habilitar envio de alertas:

1. Use uma conta Gmail
2. Ative verificação em duas etapas
3. Gere uma senha de app
4. Configure no código:

```python
EMAIL_REMETENTE = "seu_email@gmail.com"
EMAIL_SENHA = "sua_senha_de_app"
```

---

## ▶️ Como Executar

No terminal, dentro da pasta do projeto, execute:

```bash
streamlit run main.py
streamlit python -m streamlit run main.py
```

Após isso, o navegador abrirá automaticamente com o dashboard.

---

## 🔄 Atualização dos Dados

* Os dados são atualizados automaticamente a cada 5 minutos
* Também é possível atualizar manualmente pelo botão "Atualizar dados" no sistema

---

## 📊 Estrutura Esperada do Google Sheets

### Aba: Dashboard

Deve conter colunas como:

* Aluno
* Orientador
* Última reunião
* Dias sem reunião
* Status geral
* Dias aguardando
* Qtd trabalhos

### Aba: Alunos

Deve conter:

* Nome do Aluno
* turma
* Email do Orientador

---

## ❗ Possíveis Erros

### Erro: módulo não encontrado

Solução:

```bash
pip install nome_do_modulo
```

---

### Erro: credenciais não encontradas

Verifique se o arquivo `credenciais_google.json` está na pasta correta.

---

## 🧠 Observações

* O sistema depende diretamente da estrutura da planilha
* Alterações no formato podem quebrar o dashboard
* Recomenda-se manter backup da planilha

---

## 👨‍💻 Autor

Rafael de Moura Cassiano Silva

---

## 📌 Licença

Uso acadêmico e institucional.
