# -*- coding: utf-8 -*-
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
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime, timedelta
from fpdf import FPDF

# ==============================================================================
# CONFIGURAÇÃO GERAL (DEVE SER A PRIMEIRA LINHA DE COMANDO STREAMLIT)
# ==============================================================================
APP_TITLE = "Sistema ERP - Educandário Sonho Dourado"
st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="🏫")

# ==============================================================================
# ESTILO VISUAL (RM FLUXUS-LIKE)
# ==============================================================================
# Cores: Azul (primário), Branco/Cinza Claro (fundo/cartões)
st.markdown("""
    <style>
    /* Estilo Geral - Fundo Claro */
    .stApp {
        background-color: #f0f2f6; /* Cor de fundo suave */
    }
    
    /* Sidebar - Fundo Azul Escuro (Estilo RM Fluxus) */
    [data-testid="stSidebar"] {
        background-color: #004d99; /* Azul escuro */
        color: white;
    }
    
    /* Títulos na Sidebar */
    [data-testid="stSidebar"] .stMarkdown h1, 
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: white;
    }
    
    /* Botões na Sidebar */
    [data-testid="stSidebar"] .stButton>button {
        background-color: #007bff; /* Azul primário */
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px;
        margin-top: 5px;
        width: 100%;
    }
    
    /* Botões na Sidebar (Hover) */
    [data-testid="stSidebar"] .stButton>button:hover {
        background-color: #0056b3;
    }
    
    /* Botões no Corpo Principal */
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
    
    /* Cartões de Métrica (metric-card) */
    .metric-card {
        background-color: white; 
        border-left: 5px solid #007bff; /* Borda azul para destaque */
        border-radius: 8px; 
        padding: 15px; 
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Títulos e Subtítulos */
    h1, h2, h3, h4 {
        color: #004d99; /* Azul escuro para títulos */
    }
    
    /* Outros estilos originais */
    .forgot-pass {text-align: center; font-size: 0.8em; color: #555; cursor: pointer;}
    .status-ok {color: green; font-weight: bold;}
    .status-warn {color: orange; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# CAMADA DE DADOS (HÍBRIDA: SQLITE + POSTGRESQL) - SEM ALTERAÇÃO DE LÓGICA
# ==============================================================================
DB_CONFIG = st.secrets.get("database")
IS_POSTGRES = DB_CONFIG is not None

def get_connection():
    """Retorna conexão SQLite ou PostgreSQL dependendo da configuração."""
    if IS_POSTGRES:
        try:
            return psycopg2.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                port=DB_CONFIG["port"]
            )
        except Exception as e:
            st.error(f"ERRO CRÍTICO DE CONEXÃO COM O BANCO DE DADOS (Supabase): {e}")
            return None
    else:
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
    final_query = fix_query(query)
    
    try:
        # Início da transação (commit/rollback implícito no try/except)
        if not IS_POSTGRES:
             c.execute("PRAGMA foreign_keys = ON;")
        
        c.execute(final_query, params)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Erro no Banco de Dados: {e}")
        conn.rollback() # Adicionado rollback para melhor integridade
        return False
    finally:
        conn.close()

def get_data(query, params=()):
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    final_query = fix_query(query)
    
    try:
        df = pd.read_sql_query(final_query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Erro ao ler dados: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# --- CACHE PARA CONFIGURAÇÕES (OTIMIZAÇÃO) ---
@st.cache_data(ttl=300) # Cache por 5 minutos
def get_config_sistema(chave):
    """Busca configurações com cache para evitar hits excessivos no banco."""
    df = get_data("SELECT valor FROM config_sistema WHERE chave=?", (chave,))
    if not df.empty:
        return df.iloc[0]['valor']
    return ""

# --- MIGRAÇÃO E INICIALIZAÇÃO DE TABELAS (OTIMIZAÇÃO CRÍTICA) ---
@st.cache_resource
def verificar_e_atualizar_tabelas():
    """Esta função agora roda apenas UMA vez ao iniciar o servidor, tornando o sistema muito mais rápido."""
    conn = get_connection()
    if not conn: return
    c = conn.cursor()
    
    pk_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
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
            pass # Ignora erros de tabela já existente ou outros

    try:
        q_check_admin = "SELECT * FROM usuarios"
        c.execute(q_check_admin)
        if not c.fetchall():
            # Mantido hashlib.sha256 devido à restrição de instalação
            from hashlib import sha256
            q_insert = fix_query("INSERT INTO usuarios (username, password, setor, email) VALUES (?, ?, ?, ?)")
            c.execute(q_insert, ("admin", sha256(str.encode("1234")).hexdigest(), "Administrador", "admin@escola.com"))
            conn.commit()
    except Exception as e:
        conn.commit()

    def insert_ignore(table, col_check, val_check, cols_insert, vals_insert):
        q_check = fix_query(f"SELECT id FROM {table} WHERE {col_check} = ?")
        c.execute(q_check, (val_check,))
        if not c.fetchall():
            placeholders = ",".join(["?" for _ in vals_insert])
            q_ins = fix_query(f"INSERT INTO {table} ({cols_insert}) VALUES ({placeholders})")
            c.execute(q_ins, vals_insert)
            conn.commit()

    # Inserção de templates padrão (mantido o original)
    insert_ignore("templates_email", "nome_interno", "Nova Cobrança", "nome_interno, assunto, corpo", 
                  ("Nova Cobrança", "Aviso Financeiro - Educandário Sonho Dourado", "Olá {responsavel},\n\nInformamos que uma nova cobrança foi gerada para o aluno(a) {aluno}.\n\nDescrição: {descricao}\nValor: R$ {valor}\nVencimento: {vencimento}\n\nAtenciosamente,\nSecretaria."))
    insert_ignore("templates_whatsapp", "nome_interno", "Nova Cobrança Zap", "nome_interno, mensagem",
                  ("Nova Cobrança Zap", "Olá {responsavel}! 👋\nNova cobrança gerada para *{aluno}*.\n\n📝 *Ref:* {descricao}\n💰 *Valor:* R$ {valor}\n📅 *Vencimento:* {vencimento}"))

    insert_ignore("templates_email", "nome_interno", "Aviso 5 Dias", "nome_interno, assunto, corpo",
                  ("Aviso 5 Dias", "Lembrete de Vencimento Próximo", "Olá {responsavel},\n\nLembramos que a fatura de {aluno} vencerá em 5 dias ({vencimento}).\n\nDescrição: {descricao}\nValor: R$ {valor}\n\nEvite juros pagando em dia."))
    insert_ignore("templates_whatsapp", "nome_interno", "Aviso 5 Dias Zap", "nome_interno, mensagem",
                  ("Aviso 5 Dias Zap", "Olá {responsavel}! 👋\nPassando para lembrar que a mensalidade de *{aluno}* vence em 5 dias ({vencimento}).\n\nValor: R$ {valor}\nDescrição: {descricao}"))

    insert_ignore("templates_email", "nome_interno", "Aviso Hoje", "nome_interno, assunto, corpo",
                  ("Aviso Hoje", "Fatura Vence Hoje!", "Olá {responsavel},\n\nA fatura referente a {descricao} vence HOJE ({vencimento}).\nAluno: {aluno}\nValor: R$ {valor}\n\nCaso já tenha pago, desconsidere."))
    insert_ignore("templates_whatsapp", "nome_interno", "Aviso Hoje Zap", "nome_interno, mensagem",
                  ("Aviso Hoje Zap", "🚨 Olá {responsavel}!\n\nHojé é o dia do vencimento da fatura de *{aluno}*.\n\n📅 *Vencimento:* HOJE\n💰 *Valor:* R$ {valor}\n📝 *Ref:* {descricao}\n\nEstamos à disposição!"))

    conn.close()

# Executa a inicialização (com cache)
verificar_e_atualizar_tabelas()

# ==============================================================================
# SEGURANÇA E UTILITÁRIOS - SEM ALTERAÇÃO DE LÓGICA
# ==============================================================================
def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()

def gerar_codigo_recuperacao():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def processar_template_email(texto_template, dados_dict):
    texto_processado = texto_template
    for chave, valor in dados_dict.items():
        valor_str = str(valor) if valor is not None else ""
        texto_processado = texto_processado.replace(f"{{{chave}}}", valor_str)
    return texto_processado

def limpar_telefone(telefone):
    if not telefone: return ""
    nums = ''.join(filter(str.isdigit, str(telefone)))
    return nums

def enviar_email_real(destinatario, assunto, corpo):
    email_escola = get_config_sistema('email_envio')
    senha_app = get_config_sistema('senha_app')
    
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

# ==============================================================================
# GERAÇÃO DE PDF (HISTÓRICO ESCOLAR) - SEM ALTERAÇÃO DE LÓGICA
# ==============================================================================
def gerar_historico_pdf(dados_aluno, dados_historico):
    pdf = FPDF('P', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    
    # Título do PDF
    pdf.cell(0, 10, APP_TITLE, 0, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, 'Histórico Escolar do Aluno', 0, 1, 'C')
    pdf.ln(5)
    
    # Dados do Aluno
    pdf.set_fill_color(200, 220, 255) # Azul claro
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'DADOS DO ALUNO', 1, 1, 'L', 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f"Nome: {dados_aluno['nome']}", 0, 1)
    pdf.cell(0, 6, f"Nascimento: {dados_aluno['data_nascimento']}", 0, 1)
    pdf.cell(0, 6, f"Responsável: {dados_aluno['mae_nome'] or dados_aluno['pai_nome'] or 'N/A'}", 0, 1)
    pdf.ln(3)
    
    # Histórico
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'HISTÓRICO DE NOTAS', 1, 1, 'L', 1)
    
    for _, row in dados_historico.iterrows():
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"Ano Letivo: {row['ano_letivo']} - Turma: {row['turma_nome']}", 0, 1)
        pdf.set_font('Arial', '', 9)
        
        # Cabeçalho da tabela de notas
        pdf.cell(30, 5, 'Disciplina', 1, 0, 'C')
        pdf.cell(20, 5, 'Nota', 1, 0, 'C')
        pdf.cell(30, 5, 'Frequência', 1, 1, 'C')
        
        # Linhas de notas
        disciplinas = {
            'Português': row['nota_portugues'], 'Matemática': row['nota_matematica'],
            'História': row['nota_historia'], 'Geografia': row['nota_geografia'],
            'Ciências': row['nota_ciencias'], 'Inglês': row['nota_ingles'],
            'Artes': row['nota_artes'], 'Ed. Física': row['nota_ed_fisica'],
            'Ens. Religioso': row['nota_religiao']
        }
        
        for disc, nota in disciplinas.items():
            pdf.cell(30, 5, disc, 1, 0)
            pdf.cell(20, 5, f"{nota:.1f}", 1, 0, 'C')
            if disc == 'Português':
                pdf.cell(30, 5, f"{row['frequencia_aluno']} / {row['dias_letivos']} dias", 1, 1, 'C')
            else:
                pdf.cell(30, 5, '', 1, 1, 'C')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"Resultado Final: {row['resultado_final']}", 0, 1)
        pdf.ln(3)
        
    # Salva o PDF
    pdf_file = f"historico_{dados_aluno['nome'].replace(' ', '_')}.pdf"
    pdf.output(pdf_file)
    return pdf_file

# ==============================================================================
# FUNÇÕES DE AUTENTICAÇÃO - SEM ALTERAÇÃO DE LÓGICA
# ==============================================================================
def check_login(username, password):
    hashed_password = make_hashes(password)
    # st.sidebar.info(f"Hash da Senha: {hashed_password}") # Linha de diagnóstico temporária. Descomente para debug.
    
    q = 'SELECT * FROM usuarios WHERE username = ? AND "password" = ?'
    df = get_data(q, (username, hashed_password))
    if not df.empty:
        return df.iloc[0]
    return None

def create_user(username, password, setor, email):
    hashed_password = make_hashes(password)
    # st.sidebar.info(f"Hash da Senha: {hashed_password}") # Linha de diagnóstico temporária. Descomente para debug.
    q = "INSERT INTO usuarios (username, password, setor, email) VALUES (?, ?, ?, ?)"
    return run_query(q, (username, hashed_password, setor, email))

def reset_password(email, new_password):
    hashed_password = make_hashes(new_password)
    q = "UPDATE usuarios SET password = ? WHERE email = ?"
    return run_query(q, (hashed_password, email))

# ==============================================================================
# INTERFACE DE LOGIN
# ==============================================================================
def login_page():
    st.title("Acesso ao Sistema")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.image("logoesd.png", width=80) # Logo ajustado
        st.markdown(f"<h3 style='text-align: center; color: #004d99;'>{APP_TITLE}</h3>", unsafe_allow_html=True)
        
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        
        if st.button("Entrar no Sistema", key="login_btn"):
            user_data = check_login(username, password)
            if user_data is not None:
                st.session_state['logged_in'] = True
                st.session_state['user_data'] = user_data
                st.session_state['menu'] = "Dashboard"
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        
        if st.button("Esqueci minha senha", key="forgot_btn"):
            st.session_state['page'] = 'forgot_password'
            st.rerun()

# ==============================================================================
# INTERFACE DE RECUPERAÇÃO DE SENHA
# ==============================================================================
def forgot_password_page():
    st.title("Recuperação de Senha")
    
    email = st.text_input("E-mail cadastrado")
    
    if 'code_sent' not in st.session_state:
        st.session_state['code_sent'] = False
        st.session_state['recovery_email'] = None
        st.session_state['recovery_code'] = None
        
    if st.session_state['code_sent']:
        code = st.text_input("Código de Recuperação")
        new_password = st.text_input("Nova Senha", type="password")
        confirm_password = st.text_input("Confirme a Nova Senha", type="password")
        
        if st.button("Redefinir Senha"):
            q = "SELECT codigo, criado_em FROM codigos_recuperacao WHERE email = ?"
            df = get_data(q, (st.session_state['recovery_email'],))
            
            if df.empty:
                st.error("Erro: E-mail não encontrado ou código expirado.")
            elif df.iloc[0]['codigo'] != code:
                st.error("Código de recuperação incorreto.")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                # Verifica validade do código (ex: 1 hora)
                criado_em = datetime.strptime(df.iloc[0]['criado_em'], '%Y-%m-%d %H:%M:%S.%f')
                if datetime.now() - criado_em > timedelta(hours=1):
                    st.error("Código expirado. Solicite um novo.")
                elif reset_password(st.session_state['recovery_email'], new_password):
                    run_query("DELETE FROM codigos_recuperacao WHERE email = ?", (st.session_state['recovery_email'],))
                    st.success("Senha redefinida com sucesso! Faça login.")
                    st.session_state['page'] = 'login'
                    st.session_state['code_sent'] = False
                    st.rerun()
                else:
                    st.error("Erro ao redefinir a senha no banco de dados.")
    else:
        if st.button("Solicitar Código de Recuperação"):
            q = "SELECT email FROM usuarios WHERE email = ?"
            df = get_data(q, (email,))
            
            if df.empty:
                st.error("E-mail não cadastrado no sistema.")
            else:
                codigo = gerar_codigo_recuperacao()
                
                # Salva o código no banco
                run_query("DELETE FROM codigos_recuperacao WHERE email = ?", (email,))
                run_query("INSERT INTO codigos_recuperacao (email, codigo, criado_em) VALUES (?, ?, ?)", (email, codigo, str(datetime.now())))
                
                # Envia o e-mail
                assunto = "Código de Recuperação de Senha"
                corpo = f"Seu código de recuperação de senha é: {codigo}. Ele é válido por 1 hora."
                ok, msg = enviar_email_real(email, assunto, corpo)
                
                if ok:
                    st.success("Código enviado para o seu e-mail!")
                    st.session_state['code_sent'] = True
                    st.session_state['recovery_email'] = email
                    st.rerun()
                else:
                    st.error(f"Erro ao enviar e-mail: {msg}")
    
    st.markdown("---")
    if st.button("Voltar para o Login", key="back_to_login"):
        st.session_state['page'] = 'login'
        st.rerun()

# ==============================================================================
# INTERFACE PRINCIPAL (APÓS LOGIN)
# ==============================================================================
def main_app():
    user_data = st.session_state['user_data']
    
    # --- SIDEBAR (Menu) ---
    with st.sidebar:
        st.image("logoesd.png", width=80) # Logo ajustado
        st.markdown(f"<h3 style='text-align: center; color: white;'>{APP_TITLE}</h3>", unsafe_allow_html=True)
        st.markdown(f"**Usuário:** {user_data['username']}")
        st.markdown(f"**Setor:** {user_data['setor']}")
        st.markdown("---")
        
        menu = st.radio("Menu Principal", ["Dashboard", "Professores", "Turmas", "Alunos", "Financeiro", "Comunicação", "Configurações"], key="main_menu")
        st.session_state['menu'] = menu
        
        st.markdown("---")
        if st.button("Sair", key="logout_btn"):
            st.session_state['logged_in'] = False
            st.session_state['user_data'] = None
            st.session_state['page'] = 'login'
            st.rerun()

    # --- CONTEÚDO PRINCIPAL ---
    menu = st.session_state['menu']
    
    if menu == "Dashboard":
        st.title("📊 Dashboard")
        
        # Exemplo de Métricas
        df_alunos = get_data("SELECT COUNT(id) as total FROM alunos WHERE status='Cursando'")
        df_turmas = get_data("SELECT COUNT(id) as total FROM turmas WHERE ativa=1")
        df_pendencias = get_data("SELECT SUM(valor) as total FROM financeiro WHERE status='Pendente'")
        
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Alunos Ativos", df_alunos.iloc[0]['total'] if not df_alunos.empty else 0)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with c2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Turmas Ativas", df_turmas.iloc[0]['total'] if not df_turmas.empty else 0)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with c3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            df_total = df_pendencias.iloc[0]['total'] if not df_pendencias.empty and df_pendencias.iloc[0]['total'] else 0.0
            st.metric("Pendências Financeiras", f"R$ {df_total:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown("---")
        st.subheader("Atividades Recentes")
        # Adicionar aqui um dataframe de atividades recentes (ex: últimos 5 lançamentos financeiros)
        
    # --- PROFESSORES ---
    elif menu == "Professores":
        st.title("🧑‍🏫 Gestão de Professores")
        
        aba1, aba2 = st.tabs(["Cadastrar Novo", "Consultar/Editar"])
        
        with aba1:
            with st.form("novo_prof"):
                st.subheader("Dados Pessoais")
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome Completo")
                cpf = c2.text_input("CPF")
                
                c3, c4 = st.columns(2)
                tel = c3.text_input("Telefone")
                cargo = c4.text_input("Cargo", value="Professor")
                
                st.subheader("Dados Contratuais")
                c5, c6 = st.columns(2)
                data_adm = c5.date_input("Data de Admissão", value="today")
                salario = c6.number_input("Salário Base (R$)", min_value=0.0, step=100.0)
                
                endereco = st.text_area("Endereço Completo")
                
                if st.form_submit_button("Cadastrar Professor"):
                    if nome and cpf:
                        q = "INSERT INTO professores (nome, telefone, cargo, cpf, data_admissao, salario_base, endereco) VALUES (?, ?, ?, ?, ?, ?, ?)"
                        if run_query(q, (nome, tel, cargo, cpf, str(data_adm), salario, endereco)):
                            st.success(f"Professor {nome} cadastrado com sucesso!")
                        else:
                            st.error("Erro ao cadastrar. Verifique se o CPF já existe.")
                    else:
                        st.error("Nome e CPF são obrigatórios.")
                        
        with aba2:
            search = st.text_input("🔍 Buscar Professor (Nome ou CPF)")
            q = "SELECT id, nome, cargo, telefone, cpf, data_admissao, status_rh FROM professores"
            p = ()
            if search:
                q += " WHERE nome LIKE ? OR cpf LIKE ?"
                p = (f'%{search}%', f'%{search}%')
            
            df = get_data(q, p)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                
                edit_id = st.number_input("ID do Professor para Editar", min_value=0, step=1)
                
                if edit_id > 0 and edit_id in df['id'].values:
                    d = get_data("SELECT * FROM professores WHERE id=?", (edit_id,)).iloc[0]
                    
                    with st.form("edit_prof"):
                        st.subheader(f"Editando: {d['nome']}")
                        c1, c2 = st.columns(2)
                        n_nome = c1.text_input("Nome Completo", value=d['nome'])
                        n_cpf = c2.text_input("CPF", value=d['cpf'])
                        
                        c3, c4 = st.columns(2)
                        n_tel = c3.text_input("Telefone", value=d['telefone'])
                        n_cargo = c4.text_input("Cargo", value=d['cargo'])
                        
                        c5, c6 = st.columns(2)
                        n_salario = c5.number_input("Salário Base (R$)", value=d['salario_base'], min_value=0.0, step=100.0)
                        n_status = c6.selectbox("Status RH", ["Ativo", "Inativo", "Férias"], index=["Ativo", "Inativo", "Férias"].index(d['status_rh']))
                        
                        n_endereco = st.text_area("Endereço Completo", value=d['endereco'])
                        
                        if st.form_submit_button("Salvar Alterações"):
                            query_update = """
                                UPDATE professores SET 
                                nome=?, cpf=?, telefone=?, cargo=?, salario_base=?, endereco=?, status_rh=?
                                WHERE id=?
                            """
                            params_update = (n_nome, n_cpf, n_tel, n_cargo, n_salario, n_endereco, n_status, int(edit_id))
                            
                            if run_query(query_update, params_update):
                                st.success("Cadastro atualizado com sucesso!")
                                st.rerun()
            else:
                st.info("Nenhum professor encontrado.")

    # --- TURMAS ---
    elif menu == "Turmas":
        st.title("📚 Gestão de Turmas")
        
        aba1, aba2 = st.tabs(["Cadastrar Nova", "Consultar/Editar"])
        
        with aba1:
            with st.form("nova_turma"):
                nome_turma = st.text_input("Nome da Turma (ex: 1º Ano A)")
                
                professores = get_data("SELECT id, nome FROM professores WHERE status_rh='Ativo'")
                prof_nomes = professores['nome'].tolist() if not professores.empty else []
                
                prof_selecionado = st.selectbox("Professor Responsável", [""] + prof_nomes)
                
                if st.form_submit_button("Cadastrar Turma"):
                    if nome_turma and prof_selecionado:
                        prof_id = professores[professores['nome'] == prof_selecionado].iloc[0]['id']
                        q = "INSERT INTO turmas (nome_turma, professor_id) VALUES (?, ?)"
                        if run_query(q, (nome_turma, int(prof_id))):
                            st.success(f"Turma {nome_turma} cadastrada com sucesso!")
                        else:
                            st.error("Erro ao cadastrar. Verifique se o nome da turma já existe.")
                    else:
                        st.error("Nome da turma e Professor são obrigatórios.")
                        
        with aba2:
            q = "SELECT t.id, t.nome_turma, p.nome as professor, t.ativa FROM turmas t LEFT JOIN professores p ON t.professor_id = p.id"
            df = get_data(q)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                
                edit_id = st.number_input("ID da Turma para Editar", min_value=0, step=1, key="edit_turma_id")
                
                if edit_id > 0 and edit_id in df['id'].values:
                    d = get_data("SELECT * FROM turmas WHERE id=?", (edit_id,)).iloc[0]
                    
                    with st.form("edit_turma"):
                        st.subheader(f"Editando: {d['nome_turma']}")
                        
                        n_nome = st.text_input("Nome da Turma", value=d['nome_turma'])
                        
                        professores = get_data("SELECT id, nome FROM professores WHERE status_rh='Ativo'")
                        prof_nomes = professores['nome'].tolist() if not professores.empty else []
                        
                        # Determinar o professor atual
                        prof_atual = get_data("SELECT nome FROM professores WHERE id=?", (d['professor_id'],)).iloc[0]['nome'] if d['professor_id'] else ""
                        
                        prof_selecionado = st.selectbox("Professor Responsável", [""] + prof_nomes, index=(prof_nomes.index(prof_atual) + 1) if prof_atual in prof_nomes else 0)
                        
                        n_ativa = st.checkbox("Turma Ativa", value=bool(d['ativa']))
                        
                        if st.form_submit_button("Salvar Alterações da Turma"):
                            prof_id = professores[professores['nome'] == prof_selecionado].iloc[0]['id'] if prof_selecionado else None
                            
                            query_update = "UPDATE turmas SET nome_turma=?, professor_id=?, ativa=? WHERE id=?"
                            params_update = (n_nome, prof_id, int(n_ativa), int(edit_id))
                            
                            if run_query(query_update, params_update):
                                st.success("Turma atualizada com sucesso!")
                                st.rerun()
            else:
                st.info("Nenhuma turma cadastrada.")

    # --- ALUNOS ---
    elif menu == "Alunos":
        st.title("👧👦 Gestão de Alunos")
        
        aba1, aba2, aba3, aba4 = st.tabs(["Cadastrar Novo", "Consultar/Editar", "Lista de Alunos", "Histórico Escolar"])
        
        turmas = get_data("SELECT id, nome_turma FROM turmas WHERE ativa=1")
        turma_nomes = turmas['nome_turma'].tolist() if not turmas.empty else []
        
        with aba1:
            with st.form("novo_aluno"):
                st.subheader("Dados Pessoais")
                c1, c2, c3 = st.columns(3)
                nome = c1.text_input("Nome Completo")
                data_nasc = c2.date_input("Data de Nascimento", value=date.today())
                naturalidade = c3.text_input("Naturalidade")
                
                c4, c5 = st.columns(2)
                cpf = c4.text_input("CPF (Opcional)")
                rg = c5.text_input("RG (Opcional)")
                
                st.subheader("Filiação e Contato")
                c6, c7 = st.columns(2)
                pai_nome = c6.text_input("Nome do Pai")
                mae_nome = c7.text_input("Nome da Mãe")
                
                c8, c9 = st.columns(2)
                tel_contato = c8.text_input("Telefone de Contato (WhatsApp)")
                email_resp = c9.text_input("E-mail do Responsável")
                
                st.subheader("Endereço")
                c10, c11, c12 = st.columns(3)
                endereco = c10.text_input("Endereço (Rua, Número)")
                bairro = c11.text_input("Bairro")
                cep = c12.text_input("CEP")
                cidade = st.text_input("Cidade")
                
                st.subheader("Saúde e Segurança")
                saude_alergias = st.text_area("Alergias / Problemas de Saúde")
                seguranca_autorizados = st.text_area("Pessoas Autorizadas a Buscar o Aluno")
                
                st.subheader("Turma")
                turma_selecionada = st.selectbox("Turma", [""] + turma_nomes)
                
                if st.form_submit_button("Cadastrar Aluno"):
                    if nome and turma_selecionada:
                        turma_id = turmas[turmas['nome_turma'] == turma_selecionada].iloc[0]['id']
                        
                        query = """
                            INSERT INTO alunos (nome, data_nascimento, naturalidade, cpf, rg, pai_nome, mae_nome, turma_id, 
                            endereco, bairro, cep, cidade, telefone_contato, email_responsavel, saude_alergias, seguranca_autorizados) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                        params = (nome, str(data_nasc), naturalidade, cpf, rg, pai_nome, mae_nome, int(turma_id), 
                                  endereco, bairro, cep, cidade, tel_contato, email_resp, saude_alergias, seguranca_autorizados)
                        
                        if run_query(query, params):
                            st.success(f"Aluno {nome} cadastrado na turma {turma_selecionada}!")
                        else:
                            st.error("Erro ao cadastrar o aluno.")
                    else:
                        st.error("Nome do aluno e Turma são obrigatórios.")

        with aba2:
            search_aluno = st.text_input("🔍 Buscar Aluno para Edição (Nome ou CPF)")
            q = "SELECT id, nome, cpf, status FROM alunos"
            p = ()
            if search_aluno:
                q += " WHERE nome LIKE ? OR cpf LIKE ?"
                p = (f'%{search_aluno}%', f'%{search_aluno}%')
            
            df = get_data(q, p)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                
                edit_id = st.number_input("ID do Aluno para Editar", min_value=0, step=1, key="edit_aluno_id")
                
                if edit_id > 0 and edit_id in df['id'].values:
                    d = get_data("SELECT * FROM alunos WHERE id=?", (edit_id,)).iloc[0]
                    
                    with st.form("edit_aluno"):
                        st.subheader(f"Editando: {d['nome']}")
                        
                        ts = get_data("SELECT id, nome_turma FROM turmas WHERE ativa=1")
                        t_nomes = ts['nome_turma'].tolist() if not ts.empty else []
                        
                        # Determinar a turma atual
                        turma_atual = get_data("SELECT nome_turma FROM turmas WHERE id=?", (d['turma_id'],)).iloc[0]['nome_turma'] if d['turma_id'] else ""
                        
                        c1, c2 = st.columns(2)
                        nn = c1.text_input("Nome Completo", value=d['nome'])
                        nt = c2.selectbox("Turma", [""] + t_nomes, index=(t_nomes.index(turma_atual) + 1) if turma_atual in t_nomes else 0)
                        
                        c3, c4, c5 = st.columns(3)
                        nnas = c3.date_input("Data de Nascimento", value=datetime.strptime(d['data_nascimento'], '%Y-%m-%d').date())
                        ncpf = c4.text_input("CPF", value=d['cpf'] if d['cpf'] else "")
                        nmae = c5.text_input("Nome da Mãe", value=d['mae_nome'] if d['mae_nome'] else "")
                        
                        npai = st.text_input("Nome do Pai", value=d['pai_nome'] if d['pai_nome'] else "")
                        ne = st.text_input("Endereço", value=d['endereco'] if d['endereco'] else "")
                        
                        k1, k2 = st.columns(2)
                        ntel = k1.text_input("Telefone", value=d['telefone_contato'] if d['telefone_contato'] else "")
                        n_email = k2.text_input("E-mail Resp.", value=d['email_responsavel'] if 'email_responsavel' in d and d['email_responsavel'] else "")
                        
                        nsau = st.text_input("Alergias/Saúde", value=d['saude_alergias'] if d['saude_alergias'] else "")
                        nseg = st.text_input("Autorizados a Buscar", value=d['seguranca_autorizados'] if d['seguranca_autorizados'] else "")
                        
                        if st.form_submit_button("Salvar Alterações Completas"):
                            ntid = int(ts[ts['nome_turma']==nt]['id'].values[0]) if not ts.empty and nt else None
                            
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
            st.dataframe(get_data("SELECT a.id, a.nome, t.nome_turma, a.telefone_contato, a.status FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.status='Cursando'"), use_container_width=True)

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
                        turma_nome_atual = get_data("SELECT nome_turma FROM turmas WHERE id=?", (d_h['turma_id'],)).iloc[0]['nome_turma'] if d_h['turma_id'] else "N/A"
                        
                        sucesso_hist = run_query("""
                            INSERT INTO historico_escolar (aluno_id, ano_letivo, turma_nome, dias_letivos, frequencia_aluno, 
                            nota_portugues, nota_matematica, nota_historia, nota_geografia, nota_ciencias, nota_ingles, nota_artes, nota_ed_fisica, nota_religiao, resultado_final)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (int(d_h['id']), ano, turma_nome_atual, dias, freq, np, nm, nh, ng, nc, ni, na, ne, nr, res))
                        
                        if sucesso_hist:
                            if "Remover" in acao: 
                                run_query("UPDATE alunos SET turma_id=NULL WHERE id=?", (int(d_h['id']),))
                            elif "Arquivar" in acao: 
                                run_query("UPDATE alunos SET status='Inativo', turma_id=NULL WHERE id=?", (int(d_h['id']),))
                            
                            st.success("Histórico gravado com sucesso!")
                            
                            # Geração do PDF
                            historico_recente = get_data("SELECT * FROM historico_escolar WHERE aluno_id=? ORDER BY ano_letivo DESC", (int(d_h['id']),))
                            pdf_path = gerar_historico_pdf(d_h, historico_recente)
                            
                            with open(pdf_path, "rb") as file:
                                st.download_button(
                                    label="Baixar Histórico Escolar (PDF)",
                                    data=file,
                                    file_name=pdf_path,
                                    mime="application/pdf"
                                )

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
                        dados_aluno = get_data("SELECT id, email_responsavel, telefone_contato, mae_nome, pai_nome FROM alunos WHERE nome=?", (sl,)).iloc[0]
                        aid = dados_aluno['id']
                        email_resp = dados_aluno['email_responsavel']
                        tel_resp = dados_aluno['telefone_contato']
                        nome_resp = dados_aluno['mae_nome'] if dados_aluno['mae_nome'] else (dados_aluno['pai_nome'] if dados_aluno['pai_nome'] else "Responsável")
                        
                        if run_query("INSERT INTO financeiro (aluno_id, descricao, valor, vencimento) VALUES (?,?,?,?)", (int(aid), ds, vl, str(dt_venc))):
                            st.success("Lançamento realizado no sistema.")
                            
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
                                    tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Nova Cobrança'")
                                    if not tpl.empty:
                                        assunto_base = tpl.iloc[0]['assunto']
                                        corpo_base = tpl.iloc[0]['corpo']
                                        
                                        corpo_final = processar_template_email(corpo_base, vars_msg)
                                        ok, msg = enviar_email_real(email_resp, assunto_base, corpo_final)
                                    else:
                                        ok, msg = enviar_email_real(email_resp, f"Escola: {ds}", f"Nova cobrança: {ds}\nValor: R$ {vl}")
                                    
                                    if ok: st.toast("📧 E-mail enviado com sucesso!")
                                    else: st.error(f"Erro no envio de e-mail: {msg}")
                                    
                                    # Log do envio
                                    if ok:
                                        id_cobranca = get_data("SELECT id FROM financeiro WHERE aluno_id=? AND descricao=? AND valor=? ORDER BY id DESC LIMIT 1", (int(aid), ds, vl)).iloc[0]['id']
                                        run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (id_cobranca, 'nova_cobranca', str(date.today()), 'email'))
                                else:
                                    st.warning("Aluno sem e-mail cadastrado.")

                            # GERAÇÃO DE LINK WHATSAPP
                            if zap:
                                num_limpo = limpar_telefone(tel_resp)
                                if num_limpo:
                                    tpl_zap = get_data("SELECT * FROM templates_whatsapp WHERE nome_interno='Nova Cobrança Zap'")
                                    msg_zap_final = ""
                                    if not tpl_zap.empty:
                                        base_zap = tpl_zap.iloc[0]['mensagem']
                                        msg_zap_final = processar_template_email(base_zap, vars_msg)
                                    else:
                                        msg_zap_final = f"Olá, nova cobrança para {sl}: {ds} - R$ {vl:.2f}"
                                    
                                    msg_encoded = urllib.parse.quote(msg_zap_final)
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
                    if id_baixa > 0 and id_baixa in df['id'].values:
                        if run_query("UPDATE financeiro SET status='Pago' WHERE id=?", (id_baixa,)):
                            st.success(f"Pagamento do ID {id_baixa} confirmado!")
                            st.rerun()
                        else:
                            st.error("Erro ao dar baixa no pagamento.")
                    else:
                        st.warning("Selecione um ID válido.")
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
            
            q_5 = """
                SELECT f.id, a.nome, a.email_responsavel, a.telefone_contato, a.mae_nome, a.pai_nome, f.descricao, f.valor, f.vencimento 
                FROM financeiro f JOIN alunos a ON f.aluno_id = a.id 
                WHERE f.vencimento = ? AND f.status = 'Pendente'
            """
            df_5 = get_data(q_5, (daqui_5_dias,))

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
                    if st.button("📧 Enviar TODOS E-mails (5 dias)"):
                        tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Aviso 5 Dias'")
                        if not tpl.empty:
                            cont_env = 0
                            for _, row in df_5.iterrows():
                                ja_foi = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='5_dias' AND data_envio=? AND canal='email'", (row['id'], hoje_str))
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
                                c_z1.link_button(f"📲 Enviar WhatsApp ({row['telefone_contato']})", link, key=f"link5_{row['id']}")
                                if c_z2.button("Registrar", key=f"reg5_{row['id']}"):
                                    run_query("INSERT INTO log_envios (financeiro_id, tipo_aviso, data_envio, canal) VALUES (?, ?, ?, ?)", (row['id'], '5_dias', hoje_str, 'whatsapp'))
                                    st.rerun()
                            else: st.error("Sem telefone")
                        st.divider()

            # --- COLUNA HOJE ---
            with col_b:
                st.error(f"🚨 Vencendo HOJE ({len(df_hj)} encontrados)")
                if not df_hj.empty:
                    if st.button("📧 Enviar TODOS E-mails (HOJE)"):
                        tpl = get_data("SELECT * FROM templates_email WHERE nome_interno='Aviso Hoje'")
                        if not tpl.empty:
                            cont_env = 0
                            for _, row in df_hj.iterrows():
                                ja_foi = get_data("SELECT id FROM log_envios WHERE financeiro_id=? AND tipo_aviso='hoje' AND data_envio=? AND canal='email'", (row['id'], hoje_str))
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
                                c_z1.link_button(f"🚨 Cobrar Agora ({row['telefone_contato']})", link, key=f"linkhj_{row['id']}")
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
                        # Bloqueia edição de nome para templates padrão
                        is_default = ini_nome in ['Nova Cobrança', 'Aviso 5 Dias', 'Aviso Hoje']
                        nome_int = st.text_input("Nome Interno", value=ini_nome, disabled=is_default)
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
                    # Bloqueia edição de nome para templates padrão
                    is_default_z = ini_nome_z in ['Nova Cobrança Zap', 'Aviso 5 Dias Zap', 'Aviso Hoje Zap']
                    nome_int_z = st.text_input("Nome Interno", value=ini_nome_z, disabled=is_default_z)
                    mensagem_z = st.text_area("Mensagem", value=ini_msg_z, height=300)
                    if st.form_submit_button("Salvar Modelo WhatsApp"):
                        if edit_id_z:
                            if run_query("UPDATE templates_whatsapp SET nome_interno=?, mensagem=? WHERE id=?", (nome_int_z, mensagem_z, int(edit_id_z))):
                                st.success("Modelo atualizado!")
                                st.rerun()
                        else:
                            if run_query("INSERT INTO templates_whatsapp (nome_interno, mensagem) VALUES (?,?)", (nome_int_z, mensagem_z)):
                                st.success("Criado!")
                                st.rerun()
            with k2:
                st.markdown("### 🧩 Variáveis"); st.code("{aluno}, {responsavel}, {valor}, {vencimento}, {descricao}")

    # --- CONFIGURAÇÕES ---
    elif menu == "Configurações":
        st.title("⚙️ Configurações do Sistema")
        
        st.subheader("Configurações de E-mail (Envio)")
        
        email_atual = get_config_sistema('email_envio')
        senha_atual = get_config_sistema('senha_app')
        
        with st.form("config_email"):
            email_envio = st.text_input("E-mail de Envio (Gmail)", value=email_atual)
            senha_app = st.text_input("Senha de App (Gmail)", value=senha_atual, type="password")
            
            if st.form_submit_button("Salvar Configurações de E-mail"):
                # Salva ou atualiza as configurações
                run_query("INSERT OR REPLACE INTO config_sistema (chave, valor) VALUES (?, ?)", ('email_envio', email_envio))
                run_query("INSERT OR REPLACE INTO config_sistema (chave, valor) VALUES (?, ?)", ('senha_app', senha_app))
                
                # Invalida o cache para recarregar
                get_config_sistema.clear()
                
                st.success("Configurações de e-mail salvas com sucesso!")
                st.rerun()
        
        st.markdown("---")
        st.subheader("Gerenciamento de Usuários")
        
        with st.form("novo_usuario"):
            st.markdown("#### Cadastrar Novo Usuário")
            c1, c2 = st.columns(2)
            novo_user = c1.text_input("Nome de Usuário")
            novo_email = c2.text_input("E-mail")
            
            c3, c4 = st.columns(2)
            nova_senha = c3.text_input("Senha", type="password")
            setor = c4.selectbox("Setor", ["Administrador", "Secretaria", "Financeiro", "Professor"])
            
            if st.form_submit_button("Criar Usuário"):
                if novo_user and nova_senha and setor:
                    if create_user(novo_user, nova_senha, setor, novo_email):
                        st.success(f"Usuário {novo_user} criado com sucesso!")
                    else:
                        st.error("Erro ao criar usuário. O nome de usuário pode já existir.")
                else:
                    st.error("Preencha todos os campos obrigatórios.")
        
        st.markdown("---")
        st.subheader("Usuários Atuais")
        df_users = get_data("SELECT id, username, setor, email FROM usuarios")
        st.dataframe(df_users, use_container_width=True)
        
        with st.form("remover_usuario"):
            st.markdown("#### Remover Usuário")
            id_remover = st.number_input("ID do Usuário para Remover", min_value=0, step=1)
            if st.form_submit_button("Remover Usuário"):
                if id_remover > 0 and id_remover != user_data['id']: # Não permite remover o próprio usuário
                    if run_query("DELETE FROM usuarios WHERE id=?", (id_remover,)):
                        st.success(f"Usuário ID {id_remover} removido.")
                        st.rerun()
                    else:
                        st.error("Erro ao remover usuário.")
                else:
                    st.error("ID inválido ou você não pode remover seu próprio usuário.")
        
# ==============================================================================
# FLUXO PRINCIPAL
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['page'] = 'login'

if st.session_state['page'] == 'login':
    login_page()
elif st.session_state['page'] == 'forgot_password':
    forgot_password_page()
elif st.session_state['logged_in']:
    main_app()
else:
    login_page() # Fallback
