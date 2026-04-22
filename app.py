import streamlit as st
import pandas as pd
import requests
import smtplib
from email.message import EmailMessage
from datetime import datetime

# ==========================================
# CONFIGURAÇÕES DA DÍVIDA E E-MAIL
# ==========================================
VALOR_INICIAL = 78600.00
DATA_INICIAL = "2026-04-01" # Formato de sistema: AAAA-MM-DD

EMAIL_REMETENTE = "micflorencio@gmail.com"
# Pode colocar vários e-mails separados por vírgula
EMAIL_DESTINO = "cagido.carneiro@gmail.com, luiza.serta.padilha@gmail.com, micflorencio@gmail.com" 

# ==========================================
# INTEGRAÇÃO COM NUVEM (STREAMLIT SECRETS)
# ==========================================
try:
    SENHA_EMAIL = st.secrets["SENHA_EMAIL"]
    JSONBIN_ID = st.secrets["JSONBIN_ID"]
    JSONBIN_KEY = st.secrets["JSONBIN_KEY"]
except Exception:
    st.error("⚠️ Configurações de segurança não encontradas. Verifique a aba 'Secrets' no Streamlit Cloud.")
    st.stop()

URL_JSONBIN = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"

# ==========================================
# FUNÇÕES DE BANCO DE DADOS (JSONBIN)
# ==========================================
def carregar_dados():
    headers = {'X-Master-Key': JSONBIN_KEY}
    try:
        response = requests.get(URL_JSONBIN, headers=headers)
        if response.status_code == 200:
            return response.json()['record']
        else:
            return {"pagamentos": []}
    except Exception:
        st.error("Erro ao conectar ao banco de dados.")
        return {"pagamentos": []}

def salvar_dados(dados):
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': JSONBIN_KEY
    }
    try:
        requests.put(URL_JSONBIN, json=dados, headers=headers)
    except Exception:
        st.error("Erro ao salvar no banco de dados.")

# ==========================================
# FUNÇÕES UTILITÁRIAS E MATEMÁTICAS
# ==========================================
def formata_moeda(valor):
    """Formata número para o padrão de moeda do Brasil"""
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def obter_taxa_poupanca():
    """Busca a taxa do mês atual no Banco Central"""
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.195/dados/ultimos/1?formato=json"
        response = requests.get(url)
        dados = response.json()
        return float(dados[0]['valor']) / 100
    except:
        return 0.005 # Fallback de segurança (0.5%) caso a API do BCB caia

def calcular_saldo_devedor(dados):
    """Calcula a amortização cronológica perfeita (suporta retroativos)"""
    data_inicial_obj = datetime.strptime(DATA_INICIAL, "%Y-%m-%d")
    data_atual = datetime.now()
    taxa_mensal = obter_taxa_poupanca()
    
    saldo_atual = VALOR_INICIAL
    data_ultimo_evento = data_inicial_obj
    total_pago = 0
    
    # 1. Ordena os pagamentos do mais antigo para o mais novo
    if dados.get('pagamentos'):
        pagamentos_ordenados = sorted(dados['pagamentos'], key=lambda x: datetime.strptime(x['data'], "%Y-%m-%d"))
    else:
        pagamentos_ordenados = []

    # 2. Viaja no tempo calculando juros e abatendo pagamentos nas datas exatas
    for p in pagamentos_ordenados:
        data_pagamento = datetime.strptime(p['data'], "%Y-%m-%d")
        
        # Travas de segurança para datas fora do escopo
        if data_pagamento > data_atual:
            data_pagamento = data_atual
        data_pagamento = max(data_pagamento, data_inicial_obj)

        # Calcula dias passados entre o último evento e ESTE pagamento
        dias_juros = (data_pagamento - data_ultimo_evento).days
        
        if dias_juros > 0:
            fator_juros = (1 + taxa_mensal) ** (dias_juros / 30.0)
            saldo_atual = saldo_atual * fator_juros
        
        # Abate o pagamento do saldo corrigido até aquele dia
        saldo_atual -= p['valor']
        total_pago += p['valor']
        
        data_ultimo_evento = data_pagamento

    # 3. Calcula os juros do dia do último pagamento até HOJE
    dias_ate_hoje = (data_atual - data_ultimo_evento).days
    if dias_ate_hoje > 0:
        fator_juros = (1 + taxa_mensal) ** (dias_ate_hoje / 30.0)
        saldo_atual = saldo_atual * fator_juros

    # Evita saldo negativo se a dívida for super paga
    saldo_final = max(0, saldo_atual)

    # 4. Cálculo dos juros totais acumulados
    juros_acumulados = saldo_final - VALOR_INICIAL + total_pago

    # Dias passados totais para exibição
    dias_passados_total = max(0, (data_atual - data_inicial_obj).days)

    return saldo_final, total_pago, taxa_mensal, dias_passados_total, juros_acumulados

# ==========================================
# FUNÇÃO DE DISPARO DE E-MAIL
# ==========================================
def enviar_email_aviso(valor, data, comprovante_nome, comprovante_bytes):
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Aviso de Pagamento - {formata_moeda(valor)}"
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = EMAIL_DESTINO
        
        corpo = f"Olá,\n\nUm pagamento de {formata_moeda(valor)} foi registrado na plataforma em {data}.\n\nO comprovante segue em anexo."
        msg.set_content(corpo)
        
        if comprovante_bytes:
            msg.add_attachment(comprovante_bytes.read(), maintype='application', subtype='octet-stream', filename=comprovante_nome)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_REMETENTE, SENHA_EMAIL)
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        return False

# ==========================================
# INTERFACE DO USUÁRIO (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Gestão de Dívida", page_icon="💰", layout="wide")

st.title("💰 Gestão de Amortização")

# Carrega os dados direto da nuvem
dados = carregar_dados()

# Executa os cálculos
saldo_atual, total_pago, taxa_atual, dias_passados, juros_acumulados = calcular_saldo_devedor(dados)
data_inicial_br = datetime.strptime(DATA_INICIAL, "%Y-%m-%d").strftime("%d/%m/%Y")

# --- DASHBOARD DE RESUMO ---
st.markdown("### Resumo do Contrato")
col1, col2, col3 = st.columns(3)

with col1:
    st.info(f"**Saldo Devedor Atual:**\n## {formata_moeda(saldo_atual)}")
    st.markdown(f"**Valor Original:** {formata_moeda(VALOR_INICIAL)}")

with col2:
    st.warning(f"**Juros Acumulados:**\n## + {formata_moeda(juros_acumulados)}")
    st.success(f"**Total Amortizado:**\n## - {formata_moeda(total_pago)}")

with col3:
    st.error(f"**Início da Dívida:** {data_inicial_br}\n\n**Taxa Poupança Base:** {taxa_atual*100:.4f}% a.m.\n\n*Cobrança Pró-rata: {dias_passados} dias corridos*")

st.divider()

# --- FORMULÁRIO DE NOVO PAGAMENTO ---
st.subheader("Registrar Novo Pagamento")
with st.form("form_pagamento", clear_on_submit=True):
    col_a, col_b = st.columns(2)
    with col_a:
        valor_pago = st.number_input("Valor da Parcela (R$)", min_value=0.01, step=100.0)
    with col_b:
        # Formato de data forçado para padrão brasileiro no calendário
        data_pagamento = st.date_input("Data do Pagamento", datetime.today(), format="DD/MM/YYYY")
        
    comprovante = st.file_uploader("Anexar Comprovante (PDF, JPG, PNG)", type=['pdf', 'jpg', 'jpeg', 'png'])
    submit = st.form_submit_button("Registrar, Salvar e Enviar E-mail", use_container_width=True)
    
    if submit:
        if comprovante is not None:
            data_str_br = data_pagamento.strftime("%d/%m/%Y")
            
            # Envia email com o comprovante em anexo
            sucesso_email = enviar_email_aviso(valor_pago, data_str_br, comprovante.name, comprovante)
            
            if sucesso_email:
                novo_pagamento = {
                    "data": data_pagamento.strftime("%Y-%m-%d"), # Salva no BD em padrão universal
                    "valor": float(valor_pago),
                    "comprovante": comprovante.name
                }
                dados['pagamentos'].append(novo_pagamento)
                salvar_dados(dados) # Salva na nuvem do JSONBin
                
                st.success("Pagamento registrado com sucesso!")
                st.rerun()
        else:
            st.warning("Por favor, anexe o comprovante de pagamento antes de registrar.")

st.divider()

# --- TABELA DE HISTÓRICO ---
st.subheader("Histórico de Amortizações")
if dados.get('pagamentos'):
    # Ordena o DataFrame para mostrar do mais recente para o mais antigo na interface
    df = pd.DataFrame(dados['pagamentos'])
    df = df.sort_values(by='data', ascending=False)
    
    # Formatações visuais da tabela
    df['data'] = pd.to_datetime(df['data']).dt.strftime('%d/%m/%Y')
    df['valor'] = df['valor'].apply(formata_moeda)
    df.rename(columns={'data': 'Data do Pagamento', 'valor': 'Valor Amortizado', 'comprovante': 'Arquivo Anexado'}, inplace=True)
    
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Nenhum pagamento registrado ainda.")
