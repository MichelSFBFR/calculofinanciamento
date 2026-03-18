import streamlit as st
import pandas as pd
import requests
import json
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime

# --- CONFIGURAÇÕES ---
ARQUIVO_DADOS = "dados_divida.json"
VALOR_INICIAL = 78600.00
DATA_INICIAL = "2026-04-01" # Formato para o sistema ler: AAAA-MM-DD

# Configurações de E-mail
EMAIL_REMETENTE = "micflorencio@gmail.com"
SENHA_EMAIL = "zole ausl ckpd zgkt" 
EMAIL_DESTINO = "cagido.carneiro@gmail.com, luiza.serta.padilha@gmail.com, micflorencio@gmail.com"

# --- FUNÇÕES UTILITÁRIAS ---
def formata_moeda(valor):
    """Transforma float em padrão moeda BR (ex: R$ 78.600,00)"""
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r") as f:
            return json.load(f)
    return {"pagamentos": []}

def salvar_dados(dados):
    with open(ARQUIVO_DADOS, "w") as f:
        json.dump(dados, f, indent=4)

def obter_taxa_poupanca():
    """Busca a taxa de rendimento mensal da poupança na API do Banco Central"""
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.195/dados/ultimos/1?formato=json"
        response = requests.get(url)
        dados = response.json()
        taxa_percentual = float(dados[0]['valor'])
        return taxa_percentual / 100
    except Exception as e:
        return 0.005 # Fallback para 0.5% se a API falhar

def calcular_saldo_devedor(dados):
    data_inicial_obj = datetime.strptime(DATA_INICIAL, "%Y-%m-%d")
    data_atual = datetime.now()
    
    dias_passados = (data_atual - data_inicial_obj).days
    dias_passados = max(0, dias_passados)
    
    taxa_mensal = obter_taxa_poupanca()
    
    # Cálculo Pró-rata e Juros
    fator_juros = (1 + taxa_mensal) ** (dias_passados / 30.0)
    saldo_com_juros = VALOR_INICIAL * fator_juros
    
    # NOVO: Isola apenas o valor dos juros gerados pelo tempo
    juros_acumulados = saldo_com_juros - VALOR_INICIAL
    
    # Total pago e Saldo Final
    total_pago = sum(p['valor'] for p in dados['pagamentos'])
    
    saldo_final = saldo_com_juros - total_pago
    saldo_final = max(0, saldo_final) # Evita saldo negativo
    
    return saldo_final, total_pago, taxa_mensal, dias_passados, juros_acumulados

# --- FUNÇÃO DE E-MAIL ---
def enviar_email_aviso(valor, data, comprovante_nome, comprovante_bytes):
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Aviso de Pagamento - {formata_moeda(valor)}"
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = EMAIL_DESTINO
        
        corpo = f"Olá,\n\nUm pagamento de {formata_moeda(valor)} foi registrado em {data}.\nComprovante em anexo."
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

# --- INTERFACE STREAMLIT ---
# Mudamos para layout="wide" para aproveitar melhor a tela com as 3 colunas
st.set_page_config(page_title="Gestão de Dívida", page_icon="💰", layout="wide")

st.title("💰 Gestão de Dívida")

dados = carregar_dados()
# Note que adicionamos a variável juros_acumulados aqui no retorno da função
saldo_atual, total_pago, taxa_atual, dias_passados, juros_acumulados = calcular_saldo_devedor(dados)

data_inicial_br = datetime.strptime(DATA_INICIAL, "%Y-%m-%d").strftime("%d/%m/%Y")

# --- DASHBOARD ATUALIZADO (3 Colunas) ---
st.markdown("### Resumo do Contrato")

col1, col2, col3 = st.columns(3)

with col1:
    st.info(f"**Saldo Devedor Atual:**\n## {formata_moeda(saldo_atual)}")
    st.markdown(f"**Valor Original:** {formata_moeda(VALOR_INICIAL)}")

with col2:
    st.warning(f"**Juros Acumulados:**\n## + {formata_moeda(juros_acumulados)}")
    st.success(f"**Total Amortizado:**\n## - {formata_moeda(total_pago)}")

with col3:
    st.error(f"**Início da Dívida:** {data_inicial_br}\n\n**Taxa Poupança:** {taxa_atual*100:.4f}% a.m.\n\n*Cobrança Pró-rata: {dias_passados} dias*")

st.divider()

# --- FORMULÁRIO DE PAGAMENTO ---
st.subheader("Registrar Novo Pagamento")
with st.form("form_pagamento", clear_on_submit=True):
    col_a, col_b = st.columns(2)
    with col_a:
        valor_pago = st.number_input("Valor da Parcela (R$)", min_value=0.01, step=100.0)
    with col_b:
        data_pagamento = st.date_input("Data do Pagamento", datetime.today(), format="DD/MM/YYYY")
        
    comprovante = st.file_uploader("Anexar Comprovante (PDF, JPG, PNG)", type=['pdf', 'jpg', 'jpeg', 'png'])
    
    submit = st.form_submit_button("Registrar e Enviar Aviso", use_container_width=True)
    
    if submit:
        if comprovante is not None:
            data_str_br = data_pagamento.strftime("%d/%m/%Y")
            sucesso_email = enviar_email_aviso(valor_pago, data_str_br, comprovante.name, comprovante)
            
            if sucesso_email:
                novo_pagamento = {
                    "data": data_pagamento.strftime("%Y-%m-%d"),
                    "valor": float(valor_pago),
                    "comprovante": comprovante.name
                }
                dados['pagamentos'].append(novo_pagamento)
                salvar_dados(dados)
                
                st.success("Pagamento registrado com sucesso!")
                st.rerun()
        else:
            st.warning("Por favor, anexe o comprovante de pagamento.")

st.divider()

# --- HISTÓRICO DE PAGAMENTOS ---
st.subheader("Histórico de Amortizações")
if dados['pagamentos']:
    df = pd.DataFrame(dados['pagamentos'])
    
    df['data'] = pd.to_datetime(df['data']).dt.strftime('%d/%m/%Y')
    df['valor'] = df['valor'].apply(formata_moeda)
    
    df.rename(columns={'data': 'Data do Pagamento', 'valor': 'Valor Amortizado', 'comprovante': 'Arquivo Anexado'}, inplace=True)
    
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Nenhum pagamento registrado ainda.")
