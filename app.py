# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import hashlib
import smtplib
import random
import string
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime, timedelta
from fpdf import FPDF
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import plotly.graph_objects as go

# ==============================================================================
# CONFIGURAÇÃO GERAL
# ==============================================================================
APP_TITLE = "Sistema ERP - Educandário Sonho Dourado"
st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="🏫")

# ==============================================================================
# CSS MODERNO - ESTILO RM FLUXUS
# ==============================================================================
def aplicar_css_profissional():
    st.markdown("""
    <style>
    :root {
        --primary-blue: #0066cc;
        --primary-dark: #004080;
        --success: #06d6a0;
        --warning: #ffd60a;
        --danger: #ef476f;
    }
    
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1d29 0%, #0d0f1a 100%);
    }
    
    [data-testid="stSidebar"] h1, h2, h3, p {
        color: white !important;
        text-align: center;
    }
    
    [data-testid="stSidebar"] .stRadio > label {
        background: rgba(255,255,255,0.05);
        border-left: 3px solid transparent;
        padding: 12px 16px;
        margin: 4px 0;
        border-radius: 8px;
        transition: all 0.3s ease;
        color: #cbd5e0 !important;
        font-weight: 500;
    }
    
    [data-testid="stSidebar"] .stRadio > label:hover {
        background: rgba(0, 102, 204, 0.2);
        border-left-color: #00b4d8;
        transform: translateX(5px);
    }
    
    [data-testid="stSidebar"] .stRadio [data-checked="true"] {
        background: linear-gradient(90deg, rgba(0,102,204,0.3), transparent);
        border-left-color: #00b4d8;
        color: white !important;
    }
    
    .metric-card {
        background: white;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border-top: 4px solid var(--primary-blue);
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.12);
    }
    
    .metric-title {
        font-size: 0.875rem;
        color: #64748b;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1a1d29;
        margin: 8px 0;
    }
    
    [data-testid="stDataFrame"] thead tr th {
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-dark)) !important;
        color: white !important;
        font-weight: 600 !important;
        padding: 16px !important;
    }
    
    .stButton button {
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-dark));
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(0, 102, 204, 0.3);
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 102, 204, 0.4);
    }
    
    h1 {
        color: var(--primary-dark) !important;
        font-weight: 700 !important;
        padding-bottom: 12px;
        border-bottom: 4px solid var(--primary-blue);
        margin-bottom: 2rem !important;
    }
    
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    
    .badge-success { background: #d1fae5; color: #065f46; }
    .badge-warning { background: #fef3c7; color: #92400e; }
    .badge-danger { background: #fee2e2; color: #991b1b; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# CONEXÃO COM BANCO - OTIMIZADA
# ==============================================================================

@st.cache_resource
def init_connection_pool():
    try:
        db_config = st.secrets["database"]
        return pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=db_config["host"],
            database=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            port=db_config["port"]
        )
    except Exception as e:
        st.error(f"⚠️ Erro ao conectar: {e}")
        return None

def get_db_connection():
    pool_obj = init_connection_pool()
    if pool_obj:
        return pool_obj.getconn()
    return None

def return_db_connection(conn):
    pool_obj = init_connection_pool()
    if pool_obj and conn:
        pool_obj.putconn(conn)

# ==============================================================================
# FUNÇÕES DE BANCO
# ==============================================================================

def run_query(query, params=(), return_id=False):
    conn = get_db_connection()
    if not conn:
        return False
    
    final_query = query.replace('?', '%s')
    
    try:
        with conn.cursor() as c:
            c.execute(final_query, params)
            conn.commit()
            
            if return_id:
                c.execute("SELECT lastval()")
                return c.fetchone()[0]
            return True
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Erro: {e}")
        return False
    finally:
        return_db_connection(conn)

@st.cache_data(ttl=60)
def get_data(query, params=(), limit=None):
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    final_query = query.replace('?', '%s')
    
    if limit and 'LIMIT' not in final_query.upper():
        final_query += f" LIMIT {limit}"
    
    try:
        df = pd.read_sql(final_query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Erro: {e}")
        return pd.DataFrame()
    finally:
        return_db_connection(conn)

@st.cache_data(ttl=300)
def get_config_sistema(chave):
    df = get_data("SELECT valor FROM config_sistema WHERE chave=%s", (chave,))
    return df.iloc[0]['valor'] if not df.empty else ""

# ==============================================================================
# INICIALIZAÇÃO DE TABELAS
# ==============================================================================

@st.cache_resource
def verificar_e_atualizar_tabelas():
    conn = get_db_connection()
    if not conn:
        return
    
    tabelas = [
        '''CREATE TABLE IF NOT EXISTS professores (id SERIAL PRIMARY KEY, nome TEXT, telefone TEXT, cargo TEXT DEFAULT 'Professor', cpf TEXT, rg TEXT, data_admissao TEXT, salario_base REAL, carga_horaria TEXT, endereco TEXT, status_rh TEXT DEFAULT 'Ativo')''',
        '''CREATE TABLE IF NOT EXISTS turmas (id SERIAL PRIMARY KEY, nome_turma TEXT UNIQUE, professor_id INTEGER, ativa INTEGER DEFAULT 1, FOREIGN KEY(professor_id) REFERENCES professores(id))''',
        '''CREATE TABLE IF NOT EXISTS alunos (id SERIAL PRIMARY KEY, nome TEXT, data_nascimento TEXT, naturalidade TEXT, cpf TEXT, rg TEXT, pai_nome TEXT, mae_nome TEXT, turma_id INTEGER, status TEXT DEFAULT 'Cursando', endereco TEXT, bairro TEXT, cep TEXT, cidade TEXT, telefone_contato TEXT, email_responsavel TEXT, saude_alergias TEXT, saude_problemas TEXT, saude_plano TEXT, seguranca_autorizados TEXT, seguranca_transporte TEXT, FOREIGN KEY(turma_id) REFERENCES turmas(id))''',
        '''CREATE TABLE IF NOT EXISTS config_sistema (chave TEXT PRIMARY KEY, valor TEXT)''',
        '''CREATE TABLE IF NOT EXISTS financeiro (id SERIAL PRIMARY KEY, aluno_id INTEGER, descricao TEXT, valor REAL, vencimento TEXT, status TEXT DEFAULT 'Pendente', FOREIGN KEY(aluno_id) REFERENCES alunos(id))''',
        '''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, setor TEXT, email TEXT)''',
        '''CREATE TABLE IF NOT EXISTS templates_email (id SERIAL PRIMARY KEY, nome_interno TEXT UNIQUE, assunto TEXT, corpo TEXT)''',
        '''CREATE TABLE IF NOT EXISTS templates_whatsapp (id SERIAL PRIMARY KEY, nome_interno TEXT UNIQUE, mensagem TEXT)''',
        '''CREATE TABLE IF NOT EXISTS log_envios (id SERIAL PRIMARY KEY, financeiro_id INTEGER, tipo_aviso TEXT, data_envio TEXT, canal TEXT, FOREIGN KEY(financeiro_id) REFERENCES financeiro(id))'''
    ]
    
    try:
        with conn.cursor() as c:
            for cmd in tabelas:
                c.execute(cmd)
            conn.commit()
            
            c.execute("SELECT * FROM usuarios WHERE username='admin'")
            if not c.fetchall():
                hash_pw = hashlib.sha256("1234".encode()).hexdigest()
                c.execute("INSERT INTO usuarios (username, password, setor, email) VALUES (%s, %s, %s, %s)", 
                          ("admin", hash_pw, "Administrador", "admin@escola.com"))
                conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Log: {e}")
    finally:
        return_db_connection(conn)

verificar_e_atualizar_tabelas()

# ==============================================================================
# COMPONENTES VISUAIS
# ==============================================================================

def render_metric_card(titulo, valor, delta=None, icone="📊"):
    delta_html = f'<div style="color: #06d6a0; font-size: 0.875rem;">▲ {delta}</div>' if delta else ''
    
    html = f"""
    <div class="metric-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div class="metric-title">{titulo}</div>
                <div class="metric-value">{valor}</div>
                {delta_html}
            </div>
            <div style="font-size: 3rem; opacity: 0.2;">{icone}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_status_badge(status):
    badges = {
        "Ativo": ("badge-success", "✓"),
        "Cursando": ("badge-success", "✓"),
        "Pago": ("badge-success", "✓"),
        "Pendente": ("badge-warning", "⏱"),
        "Inativo": ("badge-danger", "✗"),
    }
    classe, icone = badges.get(status, ("badge-success", "●"))
    return f'<span class="badge {classe}">{icone} {status}</span>'

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================

def make_hashes(p):
    return hashlib.sha256(str.encode(p)).hexdigest()

def check_login(username, password):
    hashed = make_hashes(password)
    df = get_data('SELECT * FROM usuarios WHERE username=%s AND password=%s', (username, hashed))
    return df.iloc[0] if not df.empty else None

def enviar_email_real(destinatario, assunto, corpo):
    email_escola = get_config_sistema('email_envio')
    senha_app = get_config_sistema('senha_app')
    
    if not email_escola or not senha_app:
        return False, "Configure o e-mail."
    
    if not destinatario or "@" not in destinatario:
        return False, "E-mail inválido."
    
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

def processar_template(texto, dados_dict):
    for chave, valor in dados_dict.items():
        valor_str = str(valor) if valor is not None else ""
        texto = texto.replace(f"{{{chave}}}", valor_str)
    return texto

def limpar_telefone(telefone):
    if not telefone: return ""
    return ''.join(filter(str.isdigit, str(telefone)))

# ==============================================================================
# LOGIN
# ==============================================================================

def login_page():
    aplicar_css_profissional()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align: center; color: #004080;'>{APP_TITLE}</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #64748b;'>Faça login para acessar</p>", unsafe_allow_html=True)
        
        username = st.text_input("👤 Usuário")
        password = st.text_input("🔒 Senha", type="password")
        
        if st.button("🚀 Entrar", use_container_width=True):
            user_data = check_login(username, password)
            if user_data is not None:
                st.session_state['logged_in'] = True
                st.session_state['user_data'] = user_data
                st.session_state['menu'] = "Dashboard"
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos.")

# ==============================================================================
# DASHBOARD
# ==============================================================================

@st.cache_data(ttl=120)
def get_dashboard_metrics():
    conn = get_db_connection()
    if not conn:
        return {}
    
    try:
        query = """
        SELECT 
            (SELECT COUNT(*) FROM alunos WHERE status='Cursando') as alunos_ativos,
            (SELECT COUNT(*) FROM turmas WHERE ativa=1) as turmas_ativas,
            (SELECT COALESCE(SUM(valor), 0) FROM financeiro WHERE status='Pendente') as pendencias_total,
            (SELECT COUNT(*) FROM professores WHERE status_rh='Ativo') as professores_ativos
        """
        
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(query)
            result = c.fetchone()
            return dict(result)
    finally:
        return_db_connection(conn)

def dashboard_page():
    st.title("📊 Dashboard")
    
    metrics = get_dashboard_metrics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        render_metric_card("Alunos Ativos", metrics.get('alunos_ativos', 0), None, "👥")
    
    with col2:
        render_metric_card("Turmas Ativas", metrics.get('turmas_ativas', 0), None, "📚")
    
    with col3:
        render_metric_card("Professores", metrics.get('professores_ativos', 0), None, "👨‍🏫")
    
    with col4:
        valor = metrics.get('pendencias_total', 0)
        render_metric_card("Pendências", f"R$ {valor:,.2f}", None, "💰")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.subheader("📈 Inadimplência nos Últimos 6 Meses")
    
    query_inadim = """
    SELECT 
        TO_CHAR(vencimento::date, 'YYYY-MM') as mes,
        COUNT(*) as quantidade,
        SUM(valor) as valor_total
    FROM financeiro
    WHERE status = 'Pendente'
    AND vencimento >= CURRENT_DATE - INTERVAL '6 months'
    GROUP BY TO_CHAR(vencimento::date, 'YYYY-MM')
    ORDER BY mes
    """
    
    df_inadim = get_data(query_inadim)
    
    if not df_inadim.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_inadim['mes'],
            y=df_inadim['valor_total'],
            marker_color='#ef476f',
            text=df_inadim['valor_total'].apply(lambda x: f'R$ {x:,.0f}'),
            textposition='outside'
        ))
        
        fig.update_layout(
            height=400,
            xaxis_title="Mês",
            yaxis_title="Valor Total (R$)",
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhuma inadimplência nos últimos 6 meses! 🎉")

# ==============================================================================
# PROFESSORES
# ==============================================================================

def professores_page():
    st.title("👨‍🏫 Gestão de Professores")
    
    aba1, aba2 = st.tabs(["➕ Cadastrar Novo", "📋 Consultar/Editar"])
    
    with aba1:
        with st.form("novo_prof"):
            st.subheader("Dados do Professor")
            
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome Completo *")
            cpf = c2.text_input("CPF *")
            
            c3, c4 = st.columns(2)
            tel = c3.text_input("Telefone")
            cargo = c4.text_input("Cargo", value="Professor")
            
            c5, c6 = st.columns(2)
            data_adm = c5.date_input("Data de Admissão")
            salario = c6.number_input("Salário Base (R$)", min_value=0.0, step=100.0)
            
            endereco = st.text_area("Endereço Completo")
            
            if st.form_submit_button("💾 Cadastrar", use_container_width=True):
                if nome and cpf:
                    q = "INSERT INTO professores (nome, telefone, cargo, cpf, data_admissao, salario_base, endereco) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    if run_query(q, (nome, tel, cargo, cpf, str(data_adm), salario, endereco)):
                        st.success(f"✅ Professor {nome} cadastrado!")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao cadastrar.")
                else:
                    st.error("⚠️ Nome e CPF são obrigatórios.")
    
    with aba2:
        search = st.text_input("🔍 Buscar Professor")
        
        q = "SELECT id, nome, cargo, telefone, cpf, status_rh FROM professores"
        p = ()
        
        if search:
            q += " WHERE nome ILIKE %s OR cpf LIKE %s"
            p = (f'%{search}%', f'%{search}%')
        
        q += " ORDER BY nome LIMIT 50"
        
        df = get_data(q, p)
        
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum professor encontrado.")

# ==============================================================================
# ALUNOS
# ==============================================================================

def alunos_page():
    st.title("👦👧 Gestão de Alunos")
    
    aba1, aba2 = st.tabs(["➕ Cadastrar Novo", "📋 Lista de Alunos"])
    
    with aba1:
        turmas = get_data("SELECT id, nome_turma FROM turmas WHERE ativa=1 ORDER BY nome_turma")
        turma_nomes = turmas['nome_turma'].tolist() if not turmas.empty else []
        
        with st.form("novo_aluno"):
            st.subheader("📝 Dados do Aluno")
            
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome Completo *")
            data_nasc = c2.date_input("Data de Nascimento *")
            naturalidade = c3.text_input("Naturalidade")
            
            st.subheader("👨‍👩‍👧 Filiação e Contato")
            
            c4, c5 = st.columns(2)
            mae_nome = c4.text_input("Nome da Mãe *")
            pai_nome = c5.text_input("Nome do Pai")
            
            c6, c7 = st.columns(2)
            tel = c6.text_input("Telefone (WhatsApp)")
            email = c7.text_input("E-mail do Responsável")
            
            st.subheader("🏫 Turma")
            turma_sel = st.selectbox("Selecione a Turma *", [""] + turma_nomes)
            
            if st.form_submit_button("💾 Cadastrar", use_container_width=True):
                if nome and turma_sel:
                    turma_id = turmas[turmas['nome_turma'] == turma_sel].iloc[0]['id']
                    
                    q = """
                    INSERT INTO alunos (nome, data_nascimento, naturalidade, mae_nome, pai_nome, 
                    turma_id, telefone_contato, email_responsavel) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    if run_query(q, (nome, str(data_nasc), naturalidade, mae_nome, pai_nome, 
                                   int(turma_id), tel, email)):
                        st.success(f"✅ Aluno {nome} cadastrado!")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao cadastrar.")
                else:
                    st.error("⚠️ Preencha os campos obrigatórios.")
    
    with aba2:
        st.subheader("Lista de Alunos Ativos")
        
        search = st.text_input("🔍 Buscar aluno")
        
        q = """
        SELECT a.id, a.nome, t.nome_turma, a.telefone_contato, a.status 
        FROM alunos a 
        LEFT JOIN turmas t ON a.turma_id = t.id 
        WHERE a.status='Cursando'
        """
        p = ()
        
        if search:
            q += " AND a.nome ILIKE %s"
            p = (f'%{search}%',)
        
        q += " ORDER BY a.nome LIMIT 50"
        
        df = get_data(q, p)
        
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum aluno encontrado.")

# ==============================================================================
# FINANCEIRO
# ==============================================================================

def financeiro_page():
    st.title("💰 Gestão Financeira")
    
    aba1, aba2 = st.tabs(["➕ Nova Cobrança", "📋 Gerenciar Pagamentos"])
    
    with aba1:
        search_aluno = st.text_input("🔍 Buscar aluno")
        
        q = "SELECT id, nome FROM alunos WHERE status='Cursando'"
        p = ()
        
        if search_aluno:
            q += " AND nome ILIKE %s"
            p = (f'%{search_aluno}%',)
        
        q += " ORDER BY nome LIMIT 20"
        
        alunos = get_data(q, p)
        
        if not alunos.empty:
            with st.form("nova_cobranca"):
                aluno_sel = st.selectbox("Aluno", alunos['nome'].tolist())
                
                c1, c2 = st.columns(2)
                descricao = c1.text_input("Descrição")
                valor = c2.number_input("Valor (R$)", min_value=0.0, step=10.0)
                
                vencimento = st.date_input("Vencimento")
                
                enviar_email = st.checkbox("📧 Notificar por e-mail")
                gerar_zap = st.checkbox("📱 Gerar link WhatsApp")
                
                if st.form_submit_button("💾 Lançar", use_container_width=True):
                    aluno_id = alunos[alunos['nome'] == aluno_sel].iloc[0]['id']
                    
                    q = "INSERT INTO financeiro (aluno_id, descricao, valor, vencimento) VALUES (%s, %s, %s, %s)"
                    
                    if run_query(q, (int(aluno_id), descricao, valor, str(vencimento))):
                        st.success(f"✅ Cobrança lançada!")
                        
                        aluno_data = get_data("SELECT email_responsavel, telefone_contato, mae_nome FROM alunos WHERE id=%s", (int(aluno_id),))
                        
                        if not aluno_data.empty:
                            if enviar_email and aluno_data.iloc[0]['email_responsavel']:
                                email_resp = aluno_data.iloc[0]['email_responsavel']
                                
                                corpo = f"""
Olá!

Nova cobrança para {aluno_sel}.

Descrição: {descricao}
Valor: R$ {valor:.2f}
Vencimento: {vencimento.strftime('%d/%m/%Y')}

Atenciosamente,
Secretaria
                                """
                                
                                ok, msg = enviar_email_real(email_resp, "Aviso de Cobrança", corpo)
                                
                                if ok:
                                    st.success("📧 E-mail enviado!")
                                else:
                                    st.warning(f"⚠️ Erro: {msg}")
                            
                            if gerar_zap and aluno_data.iloc[0]['telefone_contato']:
                                tel = limpar_telefone(aluno_data.iloc[0]['telefone_contato'])
                                
                                if tel:
                                    if not tel.startswith("55"):
                                        tel = "55" + tel
                                    
                                    msg_zap = f"Olá! Nova cobrança para {aluno_sel}.\n\nDescrição: {descricao}\nValor: R$ {valor:.2f}\nVencimento: {vencimento.strftime('%d/%m/%Y')}"
                                    
                                    link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg_zap)}"
                                    
                                    st.markdown(f'<a href="{link}" target="_blank"><button style="background:#25D366; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-weight:600;">📱 Enviar WhatsApp</button></a>', unsafe_allow_html=True)
    
    with aba2:
        st.subheader("Contas em Aberto")
        
        q = """
        SELECT f.id, a.nome, f.descricao, f.valor, f.vencimento, f.status 
        FROM financeiro f 
        JOIN alunos a ON f.aluno_id = a.id 
        WHERE f.status = 'Pendente'
        ORDER BY f.vencimento
        LIMIT 50
        """
        
        df = get_data(q)
        
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            col1, col2 = st.columns([3, 1])
            
            id_baixa = col1.number_input("ID para Confirmar", min_value=0, step=1)
            
            if col2.button("✅ Confirmar", use_container_width=True):
                if id_baixa > 0 and id_baixa in df['id'].values:
                    if run_query("UPDATE financeiro SET status='Pago' WHERE id=%s", (id_baixa,)):
                        st.success(f"✅ Pagamento ID {id_baixa} confirmado!")
                        get_data.clear()
                        st.rerun()
        else:
            st.info("✅ Nenhuma pendência no momento!")

# ==============================================================================
# TURMAS
# ==============================================================================

def turmas_page():
    st.title("📚 Gestão de Turmas")
    
    aba1, aba2 = st.tabs(["➕ Cadastrar Nova", "📋 Consultar/Editar"])
    
    with aba1:
        with st.form("nova_turma"):
            nome_turma = st.text_input("Nome da Turma (ex: 1º Ano A)")
            
            professores = get_data("SELECT id, nome FROM professores WHERE status_rh='Ativo' ORDER BY nome")
            prof_nomes = professores['nome'].tolist() if not professores.empty else []
            
            prof_sel = st.selectbox("Professor Responsável", [""] + prof_nomes)
            
            if st.form_submit_button("💾 Cadastrar Turma", use_container_width=True):
                if nome_turma and prof_sel:
                    prof_id = professores[professores['nome'] == prof_sel].iloc[0]['id']
                    q = "INSERT INTO turmas (nome_turma, professor_id) VALUES (%s, %s)"
                    if run_query(q, (nome_turma, int(prof_id))):
                        st.success(f"✅ Turma {nome_turma} cadastrada!")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao cadastrar.")
                else:
                    st.error("⚠️ Preencha todos os campos.")
    
    with aba2:
        q = """
        SELECT t.id, t.nome_turma, p.nome as professor, t.ativa 
        FROM turmas t 
        LEFT JOIN professores p ON t.professor_id = p.id
        ORDER BY t.nome_turma
        """
        df = get_data(q)
        
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma turma cadastrada.")

# ==============================================================================
# COMUNICAÇÃO
# ==============================================================================

def comunicacao_page():
    st.title("📧 Comunicação Automática")
    
    tab1, tab2 = st.tabs(["🤖 Robô de Disparos", "📝 Templates"])
    
    with tab1:
        st.subheader("Avisos Automáticos de Cobrança")
        
        hoje = date.today()
        hoje_str = str(hoje)
        daqui_5 = str(hoje + timedelta(days=5))
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.warning(f"📅 Vencendo em 5 dias")
            
            q = """
            SELECT f.id, a.nome, a.email_responsavel, a.telefone_contato, a.mae_nome, 
            f.descricao, f.valor, f.vencimento 
            FROM financeiro f 
            JOIN alunos a ON f.aluno_id = a.id 
            WHERE f.vencimento = %s AND f.status = 'Pendente'
            ORDER BY a.nome
            """
            df_5 = get_data(q, (daqui_5,))
            
            if not df_5.empty:
                st.caption(f"{len(df_5)} cobranças encontradas")
                
                for _, row in df_5.iterrows():
                    with st.container():
                        st.markdown(f"**{row['nome']}** - R$ {row['valor']:.2f}")
                        
                        if row['email_responsavel']:
                            if st.button(f"📧 Enviar E-mail", key=f"email5_{row['id']}"):
                                corpo = f"""
Olá!

A cobrança de {row['nome']} vence em 5 dias ({datetime.strptime(row['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')}).

Descrição: {row['descricao']}
Valor: R$ {row['valor']:.2f}

Atenciosamente,
Secretaria
                                """
                                ok, msg = enviar_email_real(row['email_responsavel'], "Lembrete de Vencimento", corpo)
                                if ok:
                                    st.success("✅ Enviado!")
                                else:
                                    st.error(f"❌ {msg}")
                        
                        tel = limpar_telefone(row['telefone_contato'])
                        if tel:
                            if not tel.startswith("55"):
                                tel = "55" + tel
                            
                            msg = f"Olá! A mensalidade de {row['nome']} vence em 5 dias. Valor: R$ {row['valor']:.2f}"
                            link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                            
                            st.markdown(f'<a href="{link}" target="_blank"><button style="background:#25D366; color:white; border:none; padding:8px 16px; border-radius:6px; cursor:pointer;">📱 WhatsApp</button></a>', unsafe_allow_html=True)
                        
                        st.divider()
            else:
                st.info("Nenhuma cobrança vencendo em 5 dias.")
        
        with col_b:
            st.error(f"🚨 Vencendo HOJE")
            
            q = """
            SELECT f.id, a.nome, a.email_responsavel, a.telefone_contato, a.mae_nome, 
            f.descricao, f.valor, f.vencimento 
            FROM financeiro f 
            JOIN alunos a ON f.aluno_id = a.id 
            WHERE f.vencimento = %s AND f.status = 'Pendente'
            ORDER BY a.nome
            """
            df_hj = get_data(q, (hoje_str,))
            
            if not df_hj.empty:
                st.caption(f"{len(df_hj)} cobranças encontradas")
                
                for _, row in df_hj.iterrows():
                    with st.container():
                        st.markdown(f"**{row['nome']}** - R$ {row['valor']:.2f}")
                        
                        if row['email_responsavel']:
                            if st.button(f"📧 Enviar E-mail", key=f"emailhj_{row['id']}"):
                                corpo = f"""
Olá!

A cobrança de {row['nome']} VENCE HOJE!

Descrição: {row['descricao']}
Valor: R$ {row['valor']:.2f}

Atenciosamente,
Secretaria
                                """
                                ok, msg = enviar_email_real(row['email_responsavel'], "Fatura Vence Hoje!", corpo)
                                if ok:
                                    st.success("✅ Enviado!")
                                else:
                                    st.error(f"❌ {msg}")
                        
                        tel = limpar_telefone(row['telefone_contato'])
                        if tel:
                            if not tel.startswith("55"):
                                tel = "55" + tel
                            
                            msg = f"🚨 Atenção! A mensalidade de {row['nome']} vence HOJE. Valor: R$ {row['valor']:.2f}"
                            link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}"
                            
                            st.markdown(f'<a href="{link}" target="_blank"><button style="background:#ef476f; color:white; border:none; padding:8px 16px; border-radius:6px; cursor:pointer;">🚨 WhatsApp</button></a>', unsafe_allow_html=True)
                        
                        st.divider()
            else:
                st.info("Nenhuma cobrança vencendo hoje.")
    
    with tab2:
        st.subheader("📝 Gerenciar Templates de Mensagem")
        st.info("Em desenvolvimento. Em breve você poderá criar templates personalizados!")

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================

def configuracoes_page():
    st.title("⚙️ Configurações do Sistema")
    
    st.subheader("📧 Configurações de E-mail")
    
    email_atual = get_config_sistema('email_envio')
    senha_atual = get_config_sistema('senha_app')
    
    with st.form("config_email"):
        st.info("💡 Use uma senha de app do Gmail. Veja como gerar em: https://support.google.com/accounts/answer/185833")
        
        c1, c2 = st.columns(2)
        email = c1.text_input("📧 E-mail (Gmail)", value=email_atual)
        senha = c2.text_input("🔑 Senha de App", value=senha_atual, type="password")
        
        if st.form_submit_button("💾 Salvar", use_container_width=True):
            run_query("INSERT INTO config_sistema (chave, valor) VALUES ('email_envio', %s) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor", (email,))
            run_query("INSERT INTO config_sistema (chave, valor) VALUES ('senha_app', %s) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor", (senha,))
            
            get_config_sistema.clear()
            
            st.success("✅ Configurações salvas!")
            st.balloons()
    
    st.markdown("---")
    
    st.subheader("👥 Gerenciamento de Usuários")
    
    usuarios = get_data("SELECT id, username, setor, email FROM usuarios ORDER BY username")
    
    if not usuarios.empty:
        st.dataframe(usuarios, use_container_width=True, hide_index=True)
    
    with st.expander("➕ Criar Novo Usuário"):
        with st.form("novo_usuario"):
            c1, c2 = st.columns(2)
            novo_user = c1.text_input("Nome de Usuário")
            novo_email = c2.text_input("E-mail")
            
            c3, c4 = st.columns(2)
            nova_senha = c3.text_input("Senha", type="password")
            setor = c4.selectbox("Setor", ["Administrador", "Secretaria", "Financeiro", "Professor"])
            
            if st.form_submit_button("✅ Criar", use_container_width=True):
                if novo_user and nova_senha:
                    hash_pw = make_hashes(nova_senha)
                    q = "INSERT INTO usuarios (username, password, setor, email) VALUES (%s, %s, %s, %s)"
                    
                    if run_query(q, (novo_user, hash_pw, setor, novo_email)):
                        st.success(f"✅ Usuário {novo_user} criado!")
                        get_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Erro ao criar usuário.")
                else:
                    st.error("⚠️ Preencha usuário e senha.")
    
    st.markdown("---")
    
    st.subheader("🗄️ Manutenção do Sistema")
    
    col1, col2 = st.columns(2)
    
    if col1.button("🔄 Limpar Cache", use_container_width=True):
        get_data.clear()
        get_config_sistema.clear()
        get_dashboard_metrics.clear()
        st.success("✅ Cache limpo!")
        st.rerun()
    
    if col2.button("📊 Ver Estatísticas", use_container_width=True):
        st.info("Total de registros no sistema:")
        
        stats = get_dashboard_metrics()
        
        st.write(f"- **Alunos:** {stats.get('alunos_ativos', 0)}")
        st.write(f"- **Professores:** {stats.get('professores_ativos', 0)}")
        st.write(f"- **Turmas:** {stats.get('turmas_ativas', 0)}")

# ==============================================================================
# APLICAÇÃO PRINCIPAL
# ==============================================================================

def main_app():
    aplicar_css_profissional()
    
    user_data = st.session_state['user_data']
    
    # SIDEBAR
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"<h3>{APP_TITLE}</h3>", unsafe_allow_html=True)
        
        st.markdown(f"""
        <div style='background: rgba(255,255,255,0.1); padding: 15px; border-radius: 10px; margin: 20px 0;'>
            <p style='margin: 5px 0;'><strong>👤 Usuário:</strong> {user_data['username']}</p>
            <p style='margin: 5px 0;'><strong>🏢 Setor:</strong> {user_data['setor']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        menu = st.radio(
            "📋 Menu Principal",
            ["Dashboard", "Professores", "Turmas", "Alunos", "Financeiro", "Comunicação", "Configurações"],
            key="main_menu"
        )
        
        st.session_state['menu'] = menu
        
        st.markdown("---")
        
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['user_data'] = None
            st.rerun()
    
    # CONTEÚDO
    menu = st.session_state['menu']
    
    if menu == "Dashboard":
        dashboard_page()
    elif menu == "Professores":
        professores_page()
    elif menu == "Turmas":
        turmas_page()
    elif menu == "Alunos":
        alunos_page()
    elif menu == "Financeiro":
        financeiro_page()
    elif menu == "Comunicação":
        comunicacao_page()
    elif menu == "Configurações":
        configuracoes_page()

# ==============================================================================
# FLUXO PRINCIPAL
# ==============================================================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if st.session_state['logged_in']:
    main_app()
else:
    login_page()
