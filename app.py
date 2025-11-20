import streamlit as st
import sqlite3
import pandas as pd
import os
import subprocess
import shutil
import hashlib
import smtplib
import random
import string
import urllib.parse
# (Removemos o import socket pois não é mais necessário com o Pooler)
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime, timedelta
from fpdf import FPDF

# --- CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="Sistema Integrado Sonho Dourado", layout="wide", page_icon="🏫")

# --- CSS PERSONALIZADO ---
st.markdown("""
    <style>
    .stButton>button {width: 100%;}
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px; text-align: center;}
    /* Estilo para o link de esqueci a senha */
    .forgot-pass {text-align: center; font-size: 0.8em; color: #555; cursor: pointer;}
    .status-ok {color: green; font-weight: bold;}
    .status-warn {color: orange; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# CAMADA DE DADOS (HÍBRIDA: SQLITE + POSTGRESQL)
# ==============================================================================
# Verifica se existe configuração de banco na nuvem (Secrets do Streamlit)
DB_CONFIG = st.secrets.get("database")
IS_POSTGRES = DB_CONFIG is not None

def get_connection():
    """Retorna conexão SQLite ou PostgreSQL dependendo da configuração."""
    if IS_POSTGRES:
        import psycopg2
        try:
            # Conexão Limpa e Padrão para usar com o Pooler (Porta 6543)
            return psycopg2.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                port=DB_CONFIG["port"]
            )
        except Exception as e:
            st.error(f"Erro ao conectar no PostgreSQL: {e}")
            return None
    else:
        # Modo Local (SQLite) - Cria o arquivo se não existir
        return sqlite3.connect('escola.db', timeout=10)

def fix_query(query):
    """Adapta a query do padrão SQLite (?) para PostgreSQL (%s) se necessário."""
    if IS_POSTGRES:
        return query.replace('?', '%s')
    return query

def run_query(query, params=()):
    conn = get_connection()
    if not conn: return False
    
    c = conn.cursor()
    # Adaptação de sintaxe para o banco correto
    final_query = fix_query(query)
    
    try:
        # SQLite precisa ativar foreign keys manualmente
        if not IS_POSTGRES:
             c.execute("PRAGMA foreign_keys = ON;")
        
        c.execute(final_query, params)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Erro no Banco de Dados: {e}")
        return False
    finally:
        conn.close()

def get_data(query, params=()):
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    final_query = fix_query(query)
    
    try:
        # pandas read_sql usa a conexão nativa e entende os tipos
        df = pd.read_sql_query(final_query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Erro ao ler dados: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# --- MIGRAÇÃO E INICIALIZAÇÃO DE TABELAS ---
def verificar_e_atualizar_tabelas():
    conn = get_connection()
    if not conn: return
    c = conn.cursor()
    
    # Definição de Tipos para compatibilidade
    # SQLite usa AUTOINCREMENT, Postgres usa SERIAL
    pk_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    # Lista de Comandos de Criação
    tabelas = [
        f'''CREATE TABLE IF NOT EXISTS professores (id {pk_type}, nome TEXT, telefone TEXT, cargo TEXT DEFAULT 'Professor', cpf TEXT, rg TEXT, data_admissao TEXT, salario_base REAL, carga_horaria TEXT, endereco TEXT, status_rh TEXT DEFAULT 'Ativo')''',
        f'''CREATE TABLE IF NOT EXISTS turmas (id {pk_type}, nome_turma TEXT UNIQUE, professor_id INTEGER, ativa INTEGER DEFAULT 1, FOREIGN KEY(professor_id) REFERENCES professores(id))''',
        f'''CREATE TABLE IF NOT EXISTS alunos (id {pk_type}, nome TEXT, data_nascimento TEXT, naturalidade TEXT, cpf TEXT, rg TEXT, pai_nome TEXT, mae_nome TEXT, turma_id INTEGER, status TEXT DEFAULT 'Cursando', endereco TEXT, bairro TEXT, cep TEXT, cidade TEXT, telefone_contato TEXT, email_responsavel TEXT, saude_alergias TEXT, saude_problemas TEXT, saude_plano TEXT, seguranca_autorizados TEXT, seguranca_transporte TEXT, FOREIGN KEY(turma_id) REFERENCES turmas(id))''',
        f'''CREATE TABLE IF NOT EXISTS config_sistema (chave TEXT PRIMARY KEY, valor TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS historico_escolar (id {pk_type}, aluno_id INTEGER, ano_letivo INTEGER, turma_nome TEXT, dias_letivos INTEGER, frequencia_aluno INTEGER, nota_portugues REAL, nota_matematica REAL, nota_historia REAL, nota_geografia REAL, nota_ciencias REAL, nota_ingles REAL, nota_artes REAL, nota_ed_fisica REAL, nota_religiao REAL, resultado_final TEXT, obs TEXT, FOREIGN KEY(aluno_id) REFERENCES alunos(id))''',
        f'''CREATE TABLE IF NOT EXISTS financeiro (id {pk_type}, aluno_id INTEGER, descricao TEXT, valor REAL, vencimento TEXT, status TEXT DEFAULT 'Pendente', FOREIGN KEY(aluno_id) REFERENCES alunos(id))''',
        f'''CREATE TABLE IF NOT EXISTS modelos_relatorios (id {pk_type}, titulo TEXT, conteudo_tex TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS usuarios (id {pk_type}, username TEXT UNIQUE, password TEXT, setor TEXT, email TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS codigos_recuperacao (email TEXT PRIMARY KEY, codigo TEXT, criado_em TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS templates_email (id {pk_type}, nome_interno TEXT UNIQUE, assunto TEXT, corpo TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS templates_whatsapp (id {pk_type}, nome_interno TEXT UNIQUE, mensagem TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS log_envios (id {pk_type}, financeiro_id INTEGER, tipo_aviso TEXT, data_envio TEXT, canal TEXT, FOREIGN KEY(financeiro_id) REFERENCES financeiro(id))'''
    ]

    for create_cmd in tabelas:
        try:
            c.execute(create_cmd)
        except Exception as e:
            pass # Ignora erro se tabela já existe

    # Admin Padrão (Lógica Híbrida)
    try:
        # Verifica se existe usuário Admin
        q_check_admin = "SELECT * FROM usuarios"
        c.execute(q_check_admin)
        if not c.fetchall():
            from hashlib import sha256
            # Sintaxe compatível para Insert
            q_insert = fix_query("INSERT INTO usuarios (username, password, setor, email) VALUES (?, ?, ?, ?)")
            c.execute(q_insert, ("admin", sha256(str.encode("1234")).hexdigest(), "Administrador", "admin@escola.com"))
            conn.commit()
    except Exception as e:
        # Se for a primeira vez rodando, commitamos a criação das tabelas
        conn.commit()

    # Templates Padrão (Helper para inserir dados iniciais)
    def insert_ignore(table, col_check, val_check, cols_insert, vals_insert):
        q_check = fix_query(f"SELECT id FROM {table} WHERE {col_check} = ?")
        c.execute(q_check, (val_check,))
        if not c.fetchall():
            placeholders = ",".join(["?" for _ in vals_insert])
            q_ins = fix_query(f"INSERT INTO {table} ({cols_insert}) VALUES ({placeholders})")
            c.execute(q_ins, vals_insert)
            conn.commit()

    # 1. Cobrança Normal
    insert_ignore("templates_email", "nome_interno", "Nova Cobrança", "nome_interno, assunto, corpo", 
                  ("Nova Cobrança", "Aviso Financeiro - Escola Sonho Dourado", "Olá {responsavel},\n\nInformamos que uma nova cobrança foi gerada para o aluno(a) {aluno}.\n\nDescrição: {descricao}\nValor: R$ {valor}\nVencimento: {vencimento}\n\nAtenciosamente,\nSecretaria."))
    insert_ignore("templates_whatsapp", "nome_interno", "Nova Cobrança Zap", "nome_interno, mensagem",
                  ("Nova Cobrança Zap", "Olá {responsavel}! 👋\nNova cobrança gerada para *{aluno}*.\n\n📝 *Ref:* {descricao}\n💰 *Valor:* R$ {valor}\n📅 *Vencimento:* {vencimento}"))

    # 2. Aviso 5 Dias
    insert_ignore("templates_email", "nome_interno", "Aviso 5 Dias", "nome_interno, assunto, corpo",
                  ("Aviso 5 Dias", "Lembrete de Vencimento Próximo", "Olá {responsavel},\n\nLembramos que a fatura de {aluno} vencerá em 5 dias ({vencimento}).\n\nDescrição: {descricao}\nValor: R$ {valor}\n\nEvite juros pagando em dia."))
    insert_ignore("templates_whatsapp", "nome_interno", "Aviso 5 Dias Zap", "nome_interno, mensagem",
                  ("Aviso 5 Dias Zap", "Olá {responsavel}! 👋\nPassando para lembrar que a mensalidade de *{aluno}* vence em 5 dias ({vencimento}).\n\nValor: R$ {valor}\nDescrição: {descricao}"))

    # 3. Aviso Hoje
    insert_ignore("templates_email", "nome_interno", "Aviso Hoje", "nome_interno, assunto, corpo",
                  ("Aviso Hoje", "Fatura Vence Hoje!", "Olá {responsavel},\n\nA fatura referente a {descricao} vence HOJE ({vencimento}).\nAluno: {aluno}\nValor: R$ {valor}\n\nCaso já tenha pago, desconsidere."))
    insert_ignore("templates_whatsapp", "nome_interno", "Aviso Hoje Zap", "nome_interno, mensagem",
                  ("Aviso Hoje Zap", "🚨 Olá {responsavel}!\n\nHojé é o dia do vencimento da fatura de *{aluno}*.\n\n📅 *Vencimento:* HOJE\n💰 *Valor:* R$ {valor}\n📝 *Ref:* {descricao}\n\nEstamos à disposição!"))

    conn.close()

verificar_e_atualizar_tabelas()

# --- SEGURANÇA E UTILITÁRIOS ---
def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()

def gerar_codigo_recuperacao():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def processar_template_email(texto_template, dados_dict):
    """Substitui as variáveis {chave} pelos valores do dicionário."""
    texto_processado = texto_template
    for chave, valor in dados_dict.items():
        valor_str = str(valor) if valor is not None else ""
        texto_processado = texto_processado.replace(f"{{{chave}}}", valor_str)
    return texto_processado

def limpar_telefone(telefone):
    """Remove caracteres não numéricos do telefone para o link do WhatsApp."""
    if not telefone: return ""
    nums = ''.join(filter(str.isdigit, str(telefone)))
    return nums

def enviar_email_real(destinatario, assunto, corpo):
    cfg = get_data("SELECT * FROM config_sistema")
    email_escola = ""
    senha_app = ""
    
    if not cfg.empty:
        try:
            # Tenta buscar as chaves específicas
            df_mail = cfg[cfg['chave']=='email_envio']
            df_pass = cfg[cfg['chave']=='senha_app']
            
            if not df_mail.empty:
                email_escola = df_mail.iloc[0]['valor']
            if not df_pass.empty:
                senha_app = df_pass.iloc[0]['valor']
        except: pass

    if not email_escola or not senha_app:
        return False, "Configure o e-mail no menu Configurações."
    
    if not destinatario or "@" not in destinatario:
        return False, "E-mail do destinatário inválido ou vazio."

    try:
        msg = MIMEMultipart()
        msg['From'] = email_escola
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_escola, senha_app)
        server.sendmail(email_escola, destinatario, msg.as_string())
        server.quit()
        return True, "E-mail enviado!"
    except Exception as e:
        return False, str(e)

# --- PDF FUNÇÕES ---
def gerar_historico_pdf_completo(aluno_id, nome_aluno):
    hist = get_data("SELECT * FROM historico_escolar WHERE aluno_id = ? ORDER BY ano_letivo", (aluno_id,))
    dados_df = get_data("SELECT * FROM alunos WHERE id = ?", (aluno_id,))
    if dados_df.empty: return "erro.pdf"
    dados = dados_df.iloc[0]
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16); pdf.cell(0, 10, "HISTÓRICO ESCOLAR", ln=True, align="C")
    pdf.set_font("Arial", "", 12); pdf.cell(0, 6, "Educandário Sonho Dourado", ln=True, align="C")
    pdf.ln(10)
    
    pdf.set_font("Arial", "B", 10); pdf.cell(0, 6, f"Aluno: {dados['nome']}", 0, 1)
    pdf.set_font("Arial", "", 10); pdf.cell(0, 6, f"Nasc: {dados['data_nascimento']} | CPF: {dados['cpf']}", 0, 1)
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 7)
    cols = ["Ano", "Turma", "Port", "Mat", "Hist", "Geo", "Cien", "Ing", "Rel", "Art", "EF", "Res"]
    w = [12, 25, 12, 12, 12, 12, 12, 12, 12, 12, 12, 25]
    
    for i in range(len(cols)): pdf.cell(w[i], 8, cols[i], 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font("Arial", "", 7)
    if not hist.empty:
        for _, row in hist.iterrows():
            pdf.cell(w[0], 8, str(row['ano_letivo']), 1, 0, 'C')
            pdf.cell(w[1], 8, str(row['turma_nome'])[:12], 1, 0, 'C')
            def gn(key): return str(row.get(key, '-')) if pd.notna(row.get(key)) else '-'
            notas = ['nota_portugues', 'nota_matematica', 'nota_historia', 'nota_geografia', 'nota_ciencias', 'nota_ingles', 'nota_religiao', 'nota_artes', 'nota_ed_fisica']
            for n in notas: pdf.cell(12, 8, gn(n), 1, 0, 'C')
            pdf.cell(25, 8, str(row['resultado_final']), 1, 1, 'C')
    else:
        pdf.cell(0, 8, "Nenhum registro anterior.", 1, 1, 'C')

    nome = f"Historico_{nome_aluno.replace(' ','_')}.pdf"
    pdf.output(nome)
    return nome

def gerar_folha_ponto_funcionario(nome_func, cargo, mes, ano):
    pdf = FPDF(orientation='P', unit='mm', format='A4'); pdf.add_page()
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "FOLHA DE PONTO", ln=True, align='C')
    pdf.set_font("Arial", '', 10); pdf.cell(0, 10, f"Nome: {nome_func} | Cargo: {cargo} | Ref: {mes}/{ano}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8); 
    for h in ["Dia", "Entrada", "Almoço", "Volta", "Saída", "Assinatura"]: pdf.cell(30, 8, h, 1)
    pdf.ln()
    import calendar; _, nd = calendar.monthrange(ano, mes)
    pdf.set_font("Arial", '', 8)
    for d in range(1, nd+1):
        pdf.cell(30, 8, str(d), 1); pdf.cell(30, 8, "", 1); pdf.cell(30, 8, "", 1); pdf.cell(30, 8, "", 1); pdf.cell(30, 8, "", 1); pdf.cell(30, 8, "", 1); pdf.ln()
    n = f"Ponto_{nome_func.replace(' ','_')}.pdf"; pdf.output(n); return n

def gerar_lista_presenca(turma, m, a):
    df = get_data("SELECT a.nome FROM alunos a JOIN turmas t ON a.turma_id=t.id WHERE t.nome_turma=? AND a.status='Cursando' ORDER BY nome", (turma,))
    if df.empty: return None
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", "B", 14); pdf.cell(0, 10, f"CHAMADA - {turma}", ln=True)
    pdf.set_font("Arial", "", 10)
    for _,r in df.iterrows(): pdf.cell(80, 8, r['nome'], 1); pdf.cell(10, 8, "", 1); pdf.cell(10, 8, "", 1); pdf.cell(10, 8, "", 1); pdf.cell(10, 8, "", 1); pdf.cell(10, 8, "", 1); pdf.ln()
    n=f"Chamada_{turma.replace(' ','_')}.pdf"; pdf.output(n); return n

# ==============================================================================
# LÓGICA DA APLICAÇÃO
# ==============================================================================

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'recovery_mode' not in st.session_state: st.session_state['recovery_mode'] = False
if 'recovery_step' not in st.session_state: st.session_state['recovery_step'] = 0 
if 'recovery_email' not in st.session_state: st.session_state['recovery_email'] = ""

# MENSAGEM DE STATUS DO BANCO
if IS_POSTGRES:
    st.sidebar.success("☁️ Modo Nuvem Ativo (Seguro)")
else:
    st.sidebar.warning("💾 Modo Local (Temporário)")

if not st.session_state['logged_in']:
    
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🔒 Sistema Sonho Dourado</h1>", unsafe_allow_html=True)
        
        # --- FLUXO DE RECUPERAÇÃO DE SENHA ---
        if st.session_state['recovery_mode']:
            st.markdown("### 🔑 Recuperar Senha")
            
            if st.session_state['recovery_step'] == 0:
                email_rec = st.text_input("Digite seu e-mail cadastrado")
                if st.button("Enviar Código de Recuperação"):
                    # Verifica se o email existe
                    u_chk = get_data("SELECT * FROM usuarios WHERE email=?", (email_rec,))
                    if not u_chk.empty:
                        cod = gerar_codigo_recuperacao()
                        # Insert Híbrido
                        run_query("DELETE FROM codigos_recuperacao WHERE email=?", (email_rec,))
                        run_query("INSERT INTO codigos_recuperacao (email, codigo, criado_em) VALUES (?, ?, ?)", (email_rec, cod, str(datetime.now())))
                        
                        ok, msg = enviar_email_real(email_rec, "Código de Recuperação - Sonho Dourado", f"Seu código é: {cod}")
                        if ok:
                            st.session_state['recovery_email'] = email_rec
                            st.session_state['recovery_step'] = 1
                            st.success("Código enviado para o e-mail!")
                            st.rerun()
                        else:
                            st.error(f"Erro ao enviar e-mail: {msg}")
                    else:
                        st.error("E-mail não encontrado no sistema.")
                
                if st.button("Voltar ao Login"):
                    st.session_state['recovery_mode'] = False
                    st.rerun()

            elif st.session_state['recovery_step'] == 1:
                st.info(f"Código enviado para: {st.session_state['recovery_email']}")
                codigo_input = st.text_input("Informe o Código de 6 dígitos")
                if st.button("Validar Código"):
                    # Verifica código no banco
                    db_cod = get_data("SELECT * FROM codigos_recuperacao WHERE email=?", (st.session_state['recovery_email'],))
                    if not db_cod.empty and db_cod.iloc[0]['codigo'] == codigo_input:
                        st.session_state['recovery_step'] = 2
                        st.success("Código válido!")
                        st.rerun()
                    else:
                        st.error("Código inválido ou expirado.")
                        
                if st.button("Cancelar"):
                    st.session_state['recovery_mode'] = False
                    st.session_state['recovery_step'] = 0
                    st.rerun()

            elif st.session_state['recovery_step'] == 2:
                st.success("Identidade confirmada.")
                nova_senha = st.text_input("Nova Senha", type="password")
                conf_senha = st.text_input("Confirmar Nova Senha", type="password")
                
                if st.button("Redefinir Senha"):
                    if nova_senha == conf_senha and nova_senha:
                        h_nova = make_hashes(nova_senha)
                        run_query("UPDATE usuarios SET password=? WHERE email=?", (h_nova, st.session_state['recovery_email']))
                        # Limpa código usado
                        run_query("DELETE FROM codigos_recuperacao WHERE email=?", (st.session_state['recovery_email'],))
                        
                        st.success("Senha alterada com sucesso! Faça login.")
                        st.session_state['recovery_mode'] = False
                        st.session_state['recovery_step'] = 0
                        st.rerun()
                    else:
                        st.error("As senhas não coincidem ou estão vazias.")

        # --- TELA DE LOGIN PADRÃO ---
        else:
            with st.form("frm_login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"):
                    h = make_hashes(p)
                    res = get_data("SELECT * FROM usuarios WHERE username=? AND password=?", (u, h))
                    if not res.empty:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = u
                        st.session_state['user_setor'] = res['setor'].iloc[0]
                        st.rerun()
                    else: st.error("Usuário ou senha incorretos.")
            
            if st.button("Esqueci a senha / Primeiro Acesso", type="tertiary"):
                st.session_state['recovery_mode'] = True
                st.rerun()

else:
    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {st.session_state['username']}")
    st.sidebar.caption(f"Setor: {st.session_state['user_setor']}")
    
    menu_options = ["Dashboard"]
    if st.session_state['user_setor'] in ["Administrador", "Secretaria"]: menu_options.append("Secretaria")
    if st.session_state['user_setor'] in ["Administrador", "Financeiro"]: menu_options.append("Financeiro")
    if st.session_state['user_setor'] in ["Administrador", "RH"]: menu_options.append("RH")
    menu_options.append("Relatórios")
    # NOVO MENU: COMUNICAÇÃO
    if st.session_state['user_setor'] in ["Administrador", "Secretaria", "Financeiro"]: menu_options.append("Comunicação")
    if st.session_state['user_setor'] == "Administrador": menu_options.append("Configurações")
    
    menu = st.sidebar.radio("Módulo", menu_options)
    
    if st.sidebar.button("Sair"): 
        st.session_state['logged_in'] = False
        st.rerun()
    st.sidebar.divider()

    # --- DASHBOARD ---
    if menu == "Dashboard":
        st.title("📊 Visão Geral")
        c1, c2, c3 = st.columns(3)
        
        total_alunos = get_data("SELECT COUNT(*) as t FROM alunos WHERE status='Cursando'").iloc[0]['t']
        total_profs = get_data("SELECT COUNT(*) as t FROM professores WHERE status_rh='Ativo'").iloc[0]['t']
        pendencias = get_data("SELECT SUM(valor) as t FROM financeiro WHERE status='Pendente'")
        valor_pendente = pendencias.iloc[0]['t'] if not pd.isna(pendencias.iloc[0]['t']) else 0
        
        c1.metric("Alunos Ativos", total_alunos)
        c2.metric("Professores", total_profs)
        c3.metric("A Receber", f"R$ {valor_pendente:,.2f}")
        
        st.divider()
        st.subheader("Alunos por Turma")
        df_turmas = get_data("SELECT t.nome_turma, COUNT(a.id) as qtd FROM turmas t LEFT JOIN alunos a ON t.id = a.turma_id WHERE t.ativa=1 GROUP BY t.nome_turma")
        if not df_turmas.empty:
            st.bar_chart(df_turmas.set_index("nome_turma"))

    # --- SECRETARIA ---
    elif menu == "Secretaria":
        st.title("📚 Secretaria")
        aba1, aba2, aba3, aba4 = st.tabs(["Matrícula", "Editar/Buscar", "Lista", "Encerrar Ano"])
        
        with aba1:
            ts = get_data("SELECT * FROM turmas WHERE ativa=1")
            if not ts.empty:
                with st.form("matr"):
                    st.subheader("Ficha de Matrícula")
                    c1,c2 = st.columns(2); n = c1.text_input("Nome Completo*"); t = c2.selectbox("Turma", ts['nome_turma'])
                    c3,c4 = st.columns(2); nas = c3.date_input("Nascimento", min_value=date(1980,1,1)); cpf = c4.text_input("CPF")
                    c5,c6 = st.columns(2); pai = c5.text_input("Nome do Pai"); mae = c6.text_input("Nome da Mãe")
                    st.caption("Contato & Saúde")
                    k1, k2 = st.columns(2)
                    email = k1.text_input("E-mail do Responsável (para cobrança)")
                    tel = k2.text_input("Telefone de Contato")
                    end = st.text_input("Endereço")
                    sau = st.text_input("Alergias/Saúde"); seg = st.text_input("Autorizados a Buscar")
                    
                    if st.form_submit_button("Matricular"):
                        if n:
                            # CORREÇÃO: Converter numpy int para int nativo e verificar sucesso da query
                            tid = int(ts[ts['nome_turma']==t]['id'].values[0])
                            # Insert Híbrido Seguro
                            if run_query("INSERT INTO alunos (nome, data_nascimento, cpf, pai_nome, mae_nome, telefone_contato, email_responsavel, turma_id, endereco, saude_alergias, seguranca_autorizados) VALUES (?,?,?,?,?,?,?,?,?,?,?)", 
                                      (n, str(nas), cpf, pai, mae, tel, email, tid, end, sau, seg)):
                                st.success(f"Aluno {n} matriculado!")
                        else:
                            st.warning("Nome é obrigatório.")
            else: st.warning("Cadastre turmas primeiro (Pela gestão de banco ou peça ao admin).")

        with aba2:
            st.subheader("Editar Dados")
            search_term = st.text_input("🔍 Buscar Aluno (Digite o nome)")
            query_alunos = "SELECT nome FROM alunos WHERE status='Cursando'"
            params_alunos = ()
            
            if search_term:
                query_alunos += " AND nome LIKE ?"
                params_alunos = (f'%{search_term}%',)
            
            todos = get_data(query_alunos, params_alunos)
            
            if not todos.empty:
                sel = st.selectbox("Selecione o Aluno", todos['nome'])
                d = get_data("SELECT * FROM alunos WHERE nome=?", (sel,)).iloc[0]
                
                # Prepara turmas para o selectbox de edição
                ts = get_data("SELECT * FROM turmas WHERE ativa=1")
                idx_turma = 0
                if not ts.empty and d['turma_id']:
                    # Encontra o indice da turma atual do aluno na lista de turmas
                    turmas_list = ts['nome_turma'].tolist()
                    turma_atual_nome_df = ts[ts['id']==d['turma_id']]
                    if not turma_atual_nome_df.empty:
                         nome_t = turma_atual_nome_df.iloc[0]['nome_turma']
                         if nome_t in turmas_list:
                             idx_turma = turmas_list.index(nome_t)
                
                # Prepara data para o date_input
                dt_nasc = date(2010,1,1)
                try:
                    if d['data_nascimento']:
                        dt_nasc = datetime.strptime(d['data_nascimento'], '%Y-%m-%d').date()
                except: pass

                with st.form("edt"):
                    c1, c2 = st.columns(2)
                    nn = c1.text_input("Nome", value=d['nome'])
                    nt = c2.selectbox("Turma", ts['nome_turma'] if not ts.empty else [], index=idx_turma)
                    
                    c3, c4 = st.columns(2)
                    nnas = c3.date_input("Nascimento", value=dt_nasc)
                    ncpf = c4.text_input("CPF", value=d['cpf'] if d['cpf'] else "")
                    
                    c5, c6 = st.columns(2)
                    npai = c5.text_input("Pai", value=d['pai_nome'] if d['pai_nome'] else "")
                    nmae = c6.text_input("Mãe", value=d['mae_nome'] if d['mae_nome'] else "")
                    
                    st.divider()
                    
                    ne = st.text_input("Endereço", value=d['endereco'] if d['endereco'] else "")
                    
                    k1, k2 = st.columns(2)
                    ntel = k1.text_input("Telefone", value=d['telefone_contato'] if d['telefone_contato'] else "")
                    n_email = k2.text_input("E-mail Resp.", value=d['email_responsavel'] if 'email_responsavel' in d and d['email_responsavel'] else "")
                    
                    nsau = st.text_input("Alergias/Saúde", value=d['saude_alergias'] if d['saude_alergias'] else "")
                    nseg = st.text_input("Autorizados a Buscar", value=d['seguranca_autorizados'] if d['seguranca_autorizados'] else "")
                    
                    if st.form_submit_button("Salvar Alterações Completas"):
                        # Recupera ID da turma nova
                        ntid = int(ts[ts['nome_turma']==nt]['id'].values[0]) if not ts.empty else int(d['turma_id'])
                        
                        query_update = """
                            UPDATE alunos SET 
                            nome=?, turma_id=?, data_nascimento=?, cpf=?, pai_nome=?, mae_nome=?, 
                            endereco=?, telefone_contato=?, email_responsavel=?, saude_alergias=?, seguranca_autorizados=?
                            WHERE id=?
                        """
                        params_update = (nn, ntid, str(nnas), ncpf, npai, nmae, ne, ntel, n_email, nsau, nseg, int(d['id']))
                        
                        if run_query(query_update, params_update):
                            st.success("Cadastro atualizado com sucesso!")
                            st.rerun()
            else:
                st.info("Nenhum aluno encontrado.")

        with aba3:
            st.dataframe(get_data("SELECT a.nome, t.nome_turma, a.telefone_contato, a.status FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.status='Cursando'"), use_container_width=True)

        with aba4: # HISTORICO
            st.subheader("Lançamento de Notas Finais")
            search_hist = st.text_input("🔍 Buscar Aluno para Notas")
            q_h = "SELECT nome FROM alunos WHERE status='Cursando'"
            p_h = ()
            if search_hist:
                q_h += " AND nome LIKE ?"
                p_h = (f'%{search_hist}%',)
                
            als = get_data(q_h, p_h)
            
            if not als.empty:
                s_h = st.selectbox("Aluno", als['nome'], key="hist")
                d_h = get_data("SELECT * FROM alunos WHERE nome=?", (s_h,)).iloc[0]
                
                with st.form("lancar_notas"):
                    st.markdown(f"**Lançando notas para: {s_h}**")
                    c1,c2,c3 = st.columns(3)
                    ano = c1.number_input("Ano Letivo", value=datetime.now().year); dias = c2.number_input("Dias Letivos", value=200); freq = c3.number_input("Frequência (Dias)", value=180)
                    
                    st.markdown("---")
                    st.caption("Notas (Use ponto para decimais, ex: 7.5)")
                    k1,k2,k3,k4 = st.columns(4)
                    np = k1.number_input("Português", 0.0, 10.0); nm = k2.number_input("Matemática", 0.0, 10.0); nh = k3.number_input("História", 0.0, 10.0); ng = k4.number_input("Geografia", 0.0, 10.0)
                    k5,k6,k7,k8 = st.columns(4)
                    nc = k5.number_input("Ciências", 0.0, 10.0); ni = k6.number_input("Inglês", 0.0, 10.0); na = k7.number_input("Artes", 0.0, 10.0); ne = k8.number_input("Ed. Física", 0.0, 10.0)
                    nr = st.number_input("Ens. Religioso", 0.0, 10.0)
                    
                    res = st.selectbox("Resultado Final", ["Aprovado", "Reprovado", "Recuperação"])
                    acao = st.radio("Ação no Sistema:", ["Manter na Turma Atual", "Remover da Turma (Concluinte)", "Arquivar Aluno (Inativo)"])
                    
                    if st.form_submit_button("Processar Encerramento"):
                        # Salva histórico
                        sucesso_hist = run_query("""
                            INSERT INTO historico_escolar (aluno_id, ano_letivo, dias_letivos, frequencia_aluno, 
                            nota_portugues, nota_matematica, nota_historia, nota_geografia, nota_ciencias, nota_ingles, nota_artes, nota_ed_fisica, nota_religiao, resultado_final)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (int(d_h['id']), ano, dias, freq, np, nm, nh, ng, nc, ni, na, ne, nr, res))
                        
                        if sucesso_hist:
                            # Atualiza status do aluno
                            if "Remover" in acao: 
                                run_query("UPDATE alunos SET turma_id=NULL WHERE id=?", (int(d_h['id']),))
                            elif "Arquivar" in acao: 
                                run_query("UPDATE alunos SET status='Inativo', turma_id=NULL WHERE id=?", (int(d_h['id']),))
                            
                            st.success("Histórico gravado com sucesso!")

    # --- FINANCEIRO ---
    elif menu == "Financeiro":
        st.title("💰 Financeiro")
        f1, f2 = st.tabs(["Nova Cobrança", "Gerenciar Pagamentos"])
        with f1:
            search_fin = st.text_input("🔍 Buscar Aluno (Cobrança)")
            q_f = "SELECT nome FROM alunos WHERE status='Cursando'"
            p_f = ()
            if search_fin:
                 q_f += " AND nome LIKE ?"
                 p_f = (f'%{search_fin}%',)
            
            als = get_data(q_f, p_f)
            
            if not als.empty:
                with st.form("cob"):
                    sl = st.selectbox("Aluno", als['nome'])
                    ds = st.text_input("Descrição (ex: Mensalidade Outubro)")
                    vl = st.number_input("Valor (R$)", min_value=0.0, step=10.0)
                    dt_venc = st.date_input("Data de Vencimento", value=date.today())
                    c1, c2 = st.columns(2)
                    mail = c1.checkbox("📧 Notificar por E-mail")
                    zap = c2.checkbox("📱 Gerar Link WhatsApp")
                    
                    submitted = st.form_submit_button("Lançar Cobrança")

                    if submitted:
                        # Buscar dados mais completos (Nome da mãe/pai para usar de responsável)
                        dados_aluno = get_data("SELECT id, email_responsavel, telefone_contato, mae_nome, pai_nome FROM alunos WHERE nome=?", (sl,)).iloc[0]
                        aid = dados_aluno['id']
                        email_resp = dados_aluno['email_responsavel']
                        tel_resp = dados_aluno['telefone_contato']
                        nome_resp = dados_aluno['mae_nome'] if dados_aluno['mae_nome'] else (dados_aluno['pai_nome'] if dados_aluno['pai_nome'] else "Responsável")
                        
                        if run_query("INSERT INTO financeiro (aluno_id, descricao, valor, vencimento) VALUES (?,?,?,?)", (int(aid), ds, vl, str(dt_venc))):
                            st.success("Lançamento realizado no sistema.")
                            
                            # Dicionário de Variáveis Comuns
                            vars_msg = {
                                "aluno": sl,
                                "responsavel": nome_resp,
                                "descricao": ds,
                                "valor": f"{vl:.2f}",
                                "vencimento": dt_venc.strftime("%d/%m/%Y")
                            }

                            # ENVIO DE EMAIL
                            if mail:
                                if email_resp:
                                    # Buscar template
                                    tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Nova Cobrança'")
                                    if not tpl.empty:
                                        assunto_base = tpl.iloc[0]['assunto']
                                        corpo_base = tpl.iloc[0]['corpo']
                                        
                                        corpo_final = processar_template_email(corpo_base, vars_msg)
                                        ok, msg = enviar_email_real(email_resp, assunto_base, corpo_final)
                                    else:
                                        # Fallback
                                        ok, msg = enviar_email_real(email_resp, f"Escola: {ds}", f"Nova cobrança: {ds}\nValor: R$ {vl}")
                                        
                                    if ok: st.toast("📧 E-mail enviado com sucesso!")
                                    else: st.error(f"Erro no envio de e-mail: {msg}")
                                else:
                                    st.warning("Aluno sem e-mail cadastrado.")

                            # GERAÇÃO DE LINK WHATSAPP
                            if zap:
                                num_limpo = limpar_telefone(tel_resp)
                                if num_limpo:
                                    # Busca template
                                    tpl_zap = get_data("SELECT * FROM templates_whatsapp WHERE nome_interno='Nova Cobrança Zap'")
                                    msg_zap_final = ""
                                    if not tpl_zap.empty:
                                        base_zap = tpl_zap.iloc[0]['mensagem']
                                        msg_zap_final = processar_template_email(base_zap, vars_msg)
                                    else:
                                        msg_zap_final = f"Olá, nova cobrança para {sl}: {ds} - R$ {vl:.2f}"
                                    
                                    # Cria Link
                                    msg_encoded = urllib.parse.quote(msg_zap_final)
                                    # Assume Brasil (55) se não tiver
                                    if not num_limpo.startswith("55"): num_limpo = "55" + num_limpo
                                    
                                    link_zap = f"https://wa.me/{num_limpo}?text={msg_encoded}"
                                    st.markdown(f"""
                                    <a href="{link_zap}" target="_blank">
                                        <button style="background-color:#25D366; color:white; border:none; padding:10px; border-radius:5px; cursor:pointer; width:100%; font-weight:bold;">
                                            📲 Clique aqui para Enviar no WhatsApp
                                        </button>
                                    </a>
                                    """, unsafe_allow_html=True)
                                else:
                                    st.error("Aluno sem telefone cadastrado para WhatsApp.")

                                
        with f2:
            st.subheader("Contas em Aberto")
            df = get_data("SELECT f.id, a.nome, f.descricao, f.valor, f.vencimento, f.status FROM financeiro f JOIN alunos a ON f.aluno_id=a.id WHERE f.status='Pendente'")
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                
                c1, c2 = st.columns(2)
                id_baixa = c1.number_input("ID para Baixa/Pagamento", min_value=0, step=1)
                if c2.button("Confirmar Pagamento"):
                    if id_baixa > 0:
                        if run_query("UPDATE financeiro SET status='Pago' WHERE id=?", (id_baixa,)):
                            st.success(f"Pagamento do ID {id_baixa} confirmado!")
                            st.rerun()
            else:
                st.info("Nenhuma pendência encontrada.")

    # --- COMUNICAÇÃO AUTOMÁTICA ---
    elif menu == "Comunicação":
        st.title("📧 Comunicação Automática")
        
        tab_robo, tab_email, tab_zap = st.tabs(["🤖 Robô de Disparos", "Modelos de E-mail", "Modelos de WhatsApp"])
        
        # --- ROBÔ DE DISPAROS (AUTOMATIZAÇÃO) ---
        with tab_robo:
            st.markdown("### 🤖 Automação de Cobrança")
            st.info("Este painel identifica automaticamente quem precisa receber mensagem HOJE.")
            
            hoje = date.today()
            hoje_str = str(hoje)
            daqui_5_dias = str(hoje + timedelta(days=5))
            
            # 1. Buscar quem vence em 5 dias
            q_5 = """
                SELECT f.id, a.nome, a.email_responsavel, a.telefone_contato, a.mae_nome, a.pai_nome, f.descricao, f.valor, f.vencimento 
                FROM financeiro f JOIN alunos a ON f.aluno_id = a.id 
                WHERE f.vencimento = ? AND f.status = 'Pendente'
            """
            df_5 = get_data(q_5, (daqui_5_dias,))

            # 2. Buscar quem vence HOJE
            q_hj = """
                SELECT f.id, a.nome, a.email_responsavel, a.telefone_contato, a.mae_nome, a.pai_nome, f.descricao, f.valor, f.vencimento 
                FROM financeiro f JOIN alunos a ON f.aluno_id = a.id 
                WHERE f.vencimento = ? AND f.status = 'Pendente'
            """
            df_hj = get_data(q_hj, (hoje_str,))
            
            col_a, col_b = st.columns(2)
            
            # --- COLUNA 5 DIAS ---
            with col_a:
                st.warning(f"📅 Vencendo em 5 dias ({len(df_5)} encontrados)")
                if not df_5.empty:
                    # Botão Email em Massa
                    if st.button("📧 Enviar TODOS E-mails (5 dias)"):
                        tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Aviso 5 Dias'")
                        if not tpl.empty:
                            cont_env = 0
                            for _, row in df_5.iterrows():
                                # Verifica se já enviou hoje
                                ja_foi = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='5_dias' AND data_envio=?", (row['id'], hoje_str))
                                if ja_foi.empty and row['email_responsavel']:
                                    resp = row['mae_nome'] or row['pai_nome'] or "Responsável"
                                    vars_msg = {"aluno": row['nome'], "responsavel": resp, "descricao": row['descricao'], "valor": f"{row['valor']:.2f}", "vencimento": datetime.strptime(row['vencimento'], '%Y-%m-%d').strftime("%d/%m/%Y")}
                                    corpo = processar_template_email(tpl.iloc[0]['corpo'], vars_msg)
                                    
                                    ok, _ = enviar_email_real(row['email_responsavel'], tpl.iloc[0]['assunto'], corpo)
                                    if ok:
                                        run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (row['id'], '5_dias', hoje_str, 'email'))
                                        cont_env += 1
                            st.success(f"{cont_env} e-mails enviados!")
                            st.rerun()
                        else: st.error("Configure o modelo 'Aviso 5 Dias' na aba Modelos.")

                    st.markdown("---")
                    # Lista Individual para WhatsApp
                    for i, row in df_5.iterrows():
                        st.markdown(f"**{row['nome']}** - R$ {row['valor']:.2f}")
                        ja_foi_zap = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='5_dias' AND canal='whatsapp' AND data_envio=?", (row['id'], hoje_str))
                        
                        if not ja_foi_zap.empty:
                            st.caption("✅ Já enviado hoje")
                        else:
                            resp = row['mae_nome'] or row['pai_nome'] or "Responsável"
                            vars_msg = {"aluno": row['nome'], "responsavel": resp, "descricao": row['descricao'], "valor": f"{row['valor']:.2f}", "vencimento": datetime.strptime(row['vencimento'], '%Y-%m-%d').strftime("%d/%m/%Y")}
                            
                            tpl_zap = get_data("SELECT * FROM templates_whatsapp WHERE nome_interno='Aviso 5 Dias Zap'")
                            msg_base = tpl_zap.iloc[0]['mensagem'] if not tpl_zap.empty else "Olá, vencimento em 5 dias."
                            msg_final = processar_template_email(msg_base, vars_msg)
                            
                            num = limpar_telefone(row['telefone_contato'])
                            if num:
                                if not num.startswith("55"): num = "55" + num
                                link = f"https://wa.me/{num}?text={urllib.parse.quote(msg_final)}"
                                c_z1, c_z2 = st.columns([3,1])
                                c_z1.link_button(f"📲 Enviar WhatsApp ({row['telefone_contato']})", link)
                                if c_z2.button("Registrar", key=f"reg5_{row['id']}"):
                                    run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (row['id'], '5_dias', hoje_str, 'whatsapp'))
                                    st.rerun()
                            else: st.error("Sem telefone")
                        st.divider()

            # --- COLUNA HOJE ---
            with col_b:
                st.error(f"🚨 Vencendo HOJE ({len(df_hj)} encontrados)")
                if not df_hj.empty:
                    # Botão Email em Massa
                    if st.button("📧 Enviar TODOS E-mails (HOJE)"):
                        tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Aviso Hoje'")
                        if not tpl.empty:
                            cont_env = 0
                            for _, row in df_hj.iterrows():
                                ja_foi = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='hoje' AND data_envio=?", (row['id'], hoje_str))
                                if ja_foi.empty and row['email_responsavel']:
                                    resp = row['mae_nome'] or row['pai_nome'] or "Responsável"
                                    vars_msg = {"aluno": row['nome'], "responsavel": resp, "descricao": row['descricao'], "valor": f"{row['valor']:.2f}", "vencimento": datetime.strptime(row['vencimento'], '%Y-%m-%d').strftime("%d/%m/%Y")}
                                    corpo = processar_template_email(tpl.iloc[0]['corpo'], vars_msg)
                                    
                                    ok, _ = enviar_email_real(row['email_responsavel'], tpl.iloc[0]['assunto'], corpo)
                                    if ok:
                                        run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (row['id'], 'hoje', hoje_str, 'email'))
                                        cont_env += 1
                            st.success(f"{cont_env} e-mails enviados!")
                            st.rerun()
                        else: st.error("Configure o modelo 'Aviso Hoje' na aba Modelos.")

                    st.markdown("---")
                    # Lista Individual para WhatsApp
                    for i, row in df_hj.iterrows():
                        st.markdown(f"**{row['nome']}** - R$ {row['valor']:.2f}")
                        ja_foi_zap = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='hoje' AND canal='whatsapp' AND data_envio=?", (row['id'], hoje_str))
                        
                        if not ja_foi_zap.empty:
                            st.caption("✅ Já enviado hoje")
                        else:
                            resp = row['mae_nome'] or row['pai_nome'] or "Responsável"
                            vars_msg = {"aluno": row['nome'], "responsavel": resp, "descricao": row['descricao'], "valor": f"{row['valor']:.2f}", "vencimento": datetime.strptime(row['vencimento'], '%Y-%m-%d').strftime("%d/%m/%Y")}
                            
                            tpl_zap = get_data("SELECT * FROM templates_whatsapp WHERE nome_interno='Aviso Hoje Zap'")
                            msg_base = tpl_zap.iloc[0]['mensagem'] if not tpl_zap.empty else "Olá, vence hoje."
                            msg_final = processar_template_email(msg_base, vars_msg)
                            
                            num = limpar_telefone(row['telefone_contato'])
                            if num:
                                if not num.startswith("55"): num = "55" + num
                                link = f"https://wa.me/{num}?text={urllib.parse.quote(msg_final)}"
                                c_z1, c_z2 = st.columns([3,1])
                                c_z1.link_button(f"🚨 Cobrar Agora ({row['telefone_contato']})", link)
                                if c_z2.button("Registrar", key=f"reghj_{row['id']}"):
                                    run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (row['id'], 'hoje', hoje_str, 'whatsapp'))
                                    st.rerun()
                            else: st.error("Sem telefone")
                        st.divider()


        # --- TAB EMAIL ---
        with tab_email:
            tpls = get_data("SELECT * FROM templates_email")
            if not tpls.empty:
                opcoes_tpl = ["+ Criar Novo Modelo"] + tpls['nome_interno'].tolist()
                sel_tpl = st.selectbox("Selecione o Modelo (E-mail)", opcoes_tpl)
                
                ini_nome = ""; ini_assunto = ""; ini_corpo = ""; edit_id = None
                if sel_tpl != "+ Criar Novo Modelo":
                    dados_t = tpls[tpls['nome_interno']==sel_tpl].iloc[0]
                    ini_nome = dados_t['nome_interno']; ini_assunto = dados_t['assunto']; ini_corpo = dados_t['corpo']; edit_id = dados_t['id']
                
                c1, c2 = st.columns([2, 1])
                with c1:
                    with st.form("frm_tpl_email"):
                        nome_int = st.text_input("Nome Interno", value=ini_nome, disabled=(edit_id is not None and ini_nome in ['Nova Cobrança', 'Aviso 5 Dias', 'Aviso Hoje']))
                        assunto = st.text_input("Assunto", value=ini_assunto)
                        corpo = st.text_area("Mensagem", value=ini_corpo, height=300)
                        if st.form_submit_button("Salvar Modelo E-mail"):
                            if edit_id:
                                if run_query("UPDATE templates_email SET nome_interno=?, assunto=?, corpo=? WHERE id=?", (nome_int, assunto, corpo, int(edit_id))):
                                    st.success("Modelo atualizado!")
                                    st.rerun()
                            else:
                                if run_query("INSERT INTO templates_email (nome_interno, assunto, corpo) VALUES (?,?,?)", (nome_int, assunto, corpo)):
                                    st.success("Criado!")
                                    st.rerun()
                with c2:
                    st.markdown("### 🧩 Variáveis"); st.code("{aluno}, {responsavel}, {valor}, {vencimento}, {descricao}")

        # --- TAB WHATSAPP ---
        with tab_zap:
            tpls_z = get_data("SELECT * FROM templates_whatsapp")
            opcoes_tpl_z = ["+ Criar Novo Modelo Zap"] + (tpls_z['nome_interno'].tolist() if not tpls_z.empty else [])
            sel_tpl_z = st.selectbox("Selecione o Modelo (WhatsApp)", opcoes_tpl_z)
            
            ini_nome_z = ""; ini_msg_z = ""; edit_id_z = None
            if sel_tpl_z != "+ Criar Novo Modelo Zap":
                dados_tz = tpls_z[tpls_z['nome_interno']==sel_tpl_z].iloc[0]
                ini_nome_z = dados_tz['nome_interno']; ini_msg_z = dados_tz['mensagem']; edit_id_z = dados_tz['id']
            
            k1, k2 = st.columns([2, 1])
            with k1:
                with st.form("frm_tpl_zap"):
                    nome_int_z = st.text_input("Nome Interno", value=ini_nome_z, disabled=(edit_id_z is not None and ini_nome_z in ['Nova Cobrança Zap', 'Aviso 5 Dias Zap', 'Aviso Hoje Zap']))
                    msg_z = st.text_area("Mensagem WhatsApp (Use *bold* para negrito)", value=ini_msg_z, height=200)
                    if st.form_submit_button("Salvar Modelo WhatsApp"):
                        if edit_id_z:
                            if run_query("UPDATE templates_whatsapp SET nome_interno=?, mensagem=? WHERE id=?", (nome_int_z, msg_z, int(edit_id_z))):
                                st.success("Modelo WhatsApp atualizado!")
                                st.rerun()
                        else:
                            if run_query("INSERT INTO templates_whatsapp (nome_interno, mensagem) VALUES (?,?)", (nome_int_z, msg_z)):
                                st.success("Criado!")
                                st.rerun()
            with k2:
                st.markdown("### 🧩 Dicas"); st.caption("O WhatsApp suporta formatação simples:"); st.code("*negrito*, _italico_, ~riscado~"); st.code("Emojis: 💰, 📅, 👋")

    # --- RH ---
    elif menu == "RH":
        st.title("👥 Recursos Humanos")
        r1, r2, r3 = st.tabs(["Funcionários", "Ponto", "Gestão"])
        with r1:
            with st.form("add_func"):
                st.subheader("Admissão")
                n = st.text_input("Nome"); c = st.selectbox("Cargo", ["Professor", "Zelador", "Secretaria", "Coordenação"]); sal = st.number_input("Salário Base")
                if st.form_submit_button("Cadastrar"):
                    if run_query("INSERT INTO professores (nome, cargo, salario_base, status_rh) VALUES (?,?,?,'Ativo')", (n, c, sal)):
                        st.success("Funcionário cadastrado.")
            st.divider()
            st.dataframe(get_data("SELECT id, nome, cargo, status_rh FROM professores"), use_container_width=True)
        with r2:
            ats = get_data("SELECT nome, cargo FROM professores WHERE status_rh='Ativo'")
            if not ats.empty:
                c1, c2 = st.columns(2)
                sf = c1.selectbox("Funcionário", ats['nome'])
                mes_p = c2.selectbox("Mês", range(1,13), index=date.today().month-1)
                
                if st.button("Gerar Folha de Ponto (PDF)"):
                    cg = ats[ats['nome']==sf]['cargo'].values[0]
                    f = gerar_folha_ponto_funcionario(sf, cg, mes_p, date.today().year)
                    with open(f, "rb") as arq: 
                        st.download_button(f"Baixar Ponto - {sf}", arq, file_name=f)
        with r3:
            tds = get_data("SELECT nome, status_rh FROM professores")
            if not tds.empty:
                sfer = st.selectbox("Gerenciar Status", tds['nome'], key="fer")
                status_atual = tds[tds['nome']==sfer]['status_rh'].values[0]
                st.info(f"Status Atual: **{status_atual}**")
                
                nst = st.selectbox("Novo Status", ["Ativo", "Férias", "Atestado", "Demitido"])
                if st.button("Atualizar Status RH"):
                    if run_query("UPDATE professores SET status_rh=? WHERE nome=?", (nst, sfer)):
                        st.success("Status atualizado.")
                        st.rerun()

    # --- RELATÓRIOS ---
    elif menu == "Relatórios":
        st.title("🖨️ Central de Relatórios")
        mods = get_data("SELECT * FROM modelos_relatorios")
        titulos_mods = mods['titulo'].tolist() if not mods.empty else []
        
        tabs = st.tabs(["Histórico Escolar", "Lista de Chamada"] + titulos_mods + ["Configurar Modelos"])
        
        with tabs[0]:
            search_rel = st.text_input("Buscar Aluno", key="srel")
            qr = "SELECT id, nome FROM alunos"
            pr = ()
            if search_rel:
                qr += " WHERE nome LIKE ?"
                pr = (f'%{search_rel}%',)
            
            al = get_data(qr, pr)
            if not al.empty:
                sl = st.selectbox("Selecione o Aluno", al['nome'], key="hpdf")
                if st.button("Gerar PDF Histórico"):
                    aid = al[al['nome']==sl]['id'].values[0]
                    fp = gerar_historico_pdf_completo(aid, sl)
                    with open(fp, "rb") as r: st.download_button("Download PDF", r, file_name=fp)

        with tabs[1]:
             ts = get_data("SELECT nome_turma FROM turmas WHERE ativa=1")
             if not ts.empty:
                 stur = st.selectbox("Turma", ts['nome_turma'])
                 if st.button("Gerar Lista de Chamada"):
                     fc = gerar_lista_presenca(stur, date.today().month, date.today().year)
                     if fc:
                         with open(fc, "rb") as r: st.download_button("Download Lista", r, file_name=fc)
        
        if not mods.empty:
            for i, row in mods.iterrows():
                with tabs[i+2]:
                    st.markdown(f"### {row['titulo']}")
                    st.code(row['conteudo_tex'], language='latex')
                    st.info("Para gerar este PDF customizado, é necessário ter o compilador pdflatex instalado no servidor.")

        with tabs[-1]:
            st.info("Aqui você pode salvar trechos de código LaTeX para uso futuro.")
            with st.form("nmod"):
                tt = st.text_input("Título do Relatório"); cc = st.text_area("Código LaTeX")
                if st.form_submit_button("Salvar Modelo"):
                    if run_query("INSERT INTO modelos_relatorios (titulo, conteudo_tex) VALUES (?,?)", (tt, cc)):
                        st.rerun()

    # --- CONFIGURAÇÕES ---
    elif menu == "Configurações":
        st.title("⚙️ Administração do Sistema")
        t1, t2 = st.tabs(["Usuários", "Servidor de E-mail"])
        with t1:
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Criar Novo Usuário")
                with st.form("nu"):
                    u = st.text_input("Login")
                    p = st.text_input("Senha Temporária", type="password")
                    s = st.selectbox("Permissão/Setor", ["Administrador", "Secretaria", "RH", "Financeiro"])
                    e = st.text_input("E-mail (Para recuperação)")
                    if st.form_submit_button("Cadastrar Usuário"):
                        try:
                            if run_query("INSERT INTO usuarios (username, password, setor, email) VALUES (?,?,?,?)", (u, make_hashes(p), s, e)):
                                st.success("Usuário criado com sucesso.")
                        except:
                            st.error("Erro: Nome de usuário já existe.")
            
            with c2:
                st.subheader("Editar Usuários Existentes")
                df_users = get_data("SELECT id, username, setor, email FROM usuarios")
                if not df_users.empty:
                    u_sel = st.selectbox("Selecione Usuário para Editar", df_users['username'])
                    user_data = df_users[df_users['username']==u_sel].iloc[0]
                    
                    with st.form("edit_user"):
                        new_email = st.text_input("Atualizar E-mail", value=user_data['email'] if user_data['email'] else "")
                        if st.form_submit_button("Salvar E-mail"):
                            if run_query("UPDATE usuarios SET email=? WHERE username=?", (new_email, u_sel)):
                                st.success(f"E-mail de {u_sel} atualizado!")
                                st.rerun()
            
            st.divider()
            st.subheader("Lista Geral")
            st.dataframe(df_users, use_container_width=True)

        with t2:
            st.markdown("### Configuração SMTP (Gmail/Outlook)")
            st.warning("Para Gmail, use uma 'Senha de App' gerada nas configurações de segurança do Google, não sua senha normal.")
            
            cfg_mail = get_data("SELECT valor FROM config_sistema WHERE chave='email_envio'")
            cfg_pass = get_data("SELECT valor FROM config_sistema WHERE chave='senha_app'")
            val_m = cfg_mail.iloc[0]['valor'] if not cfg_mail.empty else ""
            val_p = cfg_pass.iloc[0]['valor'] if not cfg_pass.empty else ""

            with st.form("email_cfg"):
                em = st.text_input("E-mail da Escola", value=val_m)
                pw = st.text_input("Senha de App", value=val_p, type="password")
                if st.form_submit_button("Salvar Configurações"):
                    run_query("DELETE FROM config_sistema WHERE chave IN ('email_envio', 'senha_app')")
                    run_query("INSERT INTO config_sistema (chave, valor) VALUES (?,?)", ('email_envio', em))
                    run_query("INSERT INTO config_sistema (chave, valor) VALUES (?,?)", ('senha_app', pw))
                    st.success("Configuração salva! Teste enviando uma cobrança.")
# FINAL DO CODIGO AQUI
