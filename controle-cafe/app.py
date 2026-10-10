from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file
import sqlite3, csv, io, shutil, urllib.parse, os, math, re, tempfile, unicodedata
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
from calendar import monthrange

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'controle-cafe-pro')
DB_DIR = Path(os.environ.get('DATA_DIR', str(Path(__file__).resolve().parent / 'data')))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "controle_cafe.sqlite3"

TIPOS_CAFE = ["Duro", "Duro riado", "Duro riado Rio", "Riado rio", "Rio", "Escolha"]


def normalizar_cata(valor):
    """Transforma cata digitada como 30 em 30%, mantendo textos como Cata 01."""
    valor = (valor or '').strip()
    if not valor:
        return ''
    limpo = valor.replace('%', '').replace(',', '.').strip()
    try:
        numero = float(limpo)
        if numero.is_integer():
            return f"{int(numero)}%"
        return (f"{numero:.2f}".replace('.', ',').rstrip('0').rstrip(',') + '%')
    except Exception:
        return valor


def br_money(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def br_num(value):
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"

app.jinja_env.filters["money"] = br_money
app.jinja_env.filters["num"] = br_num

def br_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return value or '—'

app.jinja_env.filters['brdate'] = br_date

def br_datetime(value):
    try:
        return datetime.fromisoformat(str(value)).strftime('%d/%m/%Y %H:%M')
    except (ValueError,TypeError):
        return value or '—'

app.jinja_env.filters['brdatetime'] = br_datetime

@app.context_processor
def interface_context():
    titles = {'index': 'Visão geral', 'pessoas': 'Cadastros', 'clientes': 'Clientes e produtores',
              'compras': 'Compras', 'provas': 'Provas de café', 'vendas': 'Vendas',
              'lotes': 'Estoque', 'financeiro': 'Financeiro', 'relatorios': 'Relatórios',
              'simulador': 'Simulador', 'busca_geral': 'Busca geral', 'backup': 'Backup',
              'historico': 'Histórico', 'painel_cliente': 'Painel do cliente',
              'editar_compra': 'Editar lote', 'editar_venda': 'Editar venda',
              'editar_prova': 'Editar prova', 'editar_pessoa': 'Editar cadastro',
              'editar_financeiro': 'Editar lançamento', 'cafes_analise': 'Cafés em análise'}
    return dict(fim_mes=today()[:7]+'-'+str(monthrange(int(today()[:4]),int(today()[5:7]))[1]), page_title=titles.get(request.endpoint, 'Café Boa Vista'), app_version='2.0',
                data_atual=today(), tipos_cafe_global=TIPOS_CAFE)


def normalizar_texto(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(c)).casefold()

def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.create_function('normalizar', 1, normalizar_texto, deterministic=True)
    return con


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_column(cur, table, column, definition):
    if not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    con = db(); cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS pessoas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        documento TEXT,
        telefone TEXT,
        whatsapp TEXT,
        cidade TEXT,
        endereco TEXT,
        fazenda TEXT,
        observacao TEXT,
        criado_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER,
        data TEXT NOT NULL,
        lote TEXT,
        tipo_cafe TEXT,
        quantidade_sacas REAL NOT NULL DEFAULT 0,
        peso_kg REAL NOT NULL DEFAULT 0,
        divisor_saca REAL DEFAULT 60,
        ajuste_sacas REAL DEFAULT 0,
        valor_saca REAL NOT NULL DEFAULT 0,
        valor_total REAL NOT NULL DEFAULT 0,
        status_pagamento TEXT DEFAULT 'Pendente',
        forma_pagamento TEXT,
        frete REAL DEFAULT 0,
        outras_despesas REAL DEFAULT 0,
        origem_cafe TEXT,
        status_lote TEXT DEFAULT 'Em estoque',
        observacao TEXT,
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id)
    );
    CREATE TABLE IF NOT EXISTS provas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER,
        compra_id INTEGER,
        data TEXT NOT NULL,
        cata TEXT,
        nome_cliente TEXT,
        nome_avulso TEXT,
        quantidade REAL DEFAULT 0,
        quantidade_sacas REAL DEFAULT 0,
        bebida TEXT,
        peneira TEXT,
        umidade TEXT,
        defeitos TEXT,
        aroma TEXT,
        corpo TEXT,
        acidez TEXT,
        docura TEXT,
        nota TEXT,
        classificacao TEXT,
        aprovado TEXT DEFAULT 'Em análise',
        observacao TEXT,
        FOREIGN KEY(compra_id) REFERENCES compras(id),
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id)
    );
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER,
        compra_id INTEGER,
        data TEXT NOT NULL,
        lote TEXT,
        tipo_cafe TEXT,
        quantidade_sacas REAL NOT NULL DEFAULT 0,
        valor_saca REAL NOT NULL DEFAULT 0,
        subtotal_cafe REAL DEFAULT 0,
        juros_percentual REAL DEFAULT 0,
        meses_atraso REAL DEFAULT 0,
        valor_juros REAL DEFAULT 0,
        valor_total REAL NOT NULL DEFAULT 0,
        custo_saca REAL DEFAULT 0,
        lucro_total REAL DEFAULT 0,
        status_recebimento TEXT DEFAULT 'Pendente',
        forma_pagamento TEXT,
        observacao TEXT,
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id),
        FOREIGN KEY(compra_id) REFERENCES compras(id)
    );
    CREATE TABLE IF NOT EXISTS financeiro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        tipo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        categoria TEXT,
        valor REAL NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'Pendente',
        origem TEXT
    );
    CREATE TABLE IF NOT EXISTS adiantamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER NOT NULL,
        data TEXT NOT NULL,
        valor REAL NOT NULL DEFAULT 0,
        taxa_juros REAL DEFAULT 0,
        meses_atraso REAL DEFAULT 0,
        valor_juros REAL DEFAULT 0,
        valor_total REAL DEFAULT 0,
        observacao TEXT,
        status TEXT DEFAULT 'Aberto',
        criado_em TEXT NOT NULL,
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id)
    );
    CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_hora TEXT NOT NULL,
        entidade TEXT,
        entidade_id INTEGER,
        acao TEXT NOT NULL,
        detalhe TEXT
    );
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        nome TEXT,
        tipo TEXT DEFAULT 'Administrador',
        criado_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS contas_cliente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER NOT NULL,
        banco TEXT,
        agencia TEXT,
        conta TEXT,
        tipo_conta TEXT,
        pix TEXT,
        titular TEXT,
        cpf TEXT,
        observacao TEXT,
        criado_em TEXT NOT NULL,
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id)
    );
    """)
    for table, cols in {
        'pessoas': [('documento','TEXT'),('whatsapp','TEXT'),('endereco','TEXT'),('fazenda','TEXT')],
        'compras': [('forma_pagamento','TEXT'),('frete','REAL DEFAULT 0'),('outras_despesas','REAL DEFAULT 0'),('origem_cafe','TEXT'),('status_lote',"TEXT DEFAULT 'Em estoque'"),('divisor_saca','REAL DEFAULT 60'),('ajuste_sacas','REAL DEFAULT 0')],
        'provas': [('pessoa_id','INTEGER'),('cata','TEXT'),('nome_cliente','TEXT'),('nome_avulso','TEXT'),('quantidade','REAL DEFAULT 0'),('quantidade_sacas','REAL DEFAULT 0'),('aroma','TEXT'),('corpo','TEXT'),('acidez','TEXT'),('docura','TEXT'),('aprovado',"TEXT DEFAULT 'Em análise'")],
        'vendas': [('compra_id','INTEGER'),('custo_saca','REAL DEFAULT 0'),('lucro_total','REAL DEFAULT 0'),('forma_pagamento','TEXT'),('subtotal_cafe','REAL DEFAULT 0'),('juros_percentual','REAL DEFAULT 0'),('meses_atraso','REAL DEFAULT 0'),('valor_juros','REAL DEFAULT 0')],
        'financeiro': [('categoria','TEXT')],
        'adiantamentos': [('taxa_juros','REAL DEFAULT 0'),('meses_atraso','REAL DEFAULT 0'),('valor_juros','REAL DEFAULT 0'),('valor_total','REAL DEFAULT 0'),('observacao','TEXT'),('status',"TEXT DEFAULT 'Aberto'"),('criado_em','TEXT')],
        'historico': [('entidade','TEXT'),('entidade_id','INTEGER'),('detalhe','TEXT')],
        'usuarios': [('nome','TEXT'),('tipo',"TEXT DEFAULT 'Administrador'")],
        'contas_cliente': [('banco','TEXT'),('agencia','TEXT'),('conta','TEXT'),('tipo_conta','TEXT'),('pix','TEXT'),('titular','TEXT'),('cpf','TEXT'),('observacao','TEXT'),('criado_em','TEXT')]
    }.items():
        for column, definition in cols:
            add_column(cur, table, column, definition)
    cur.execute("UPDATE provas SET aprovado='Em análise' WHERE aprovado IS NULL OR TRIM(aprovado)=''")
    cur.execute("UPDATE vendas SET subtotal_cafe=quantidade_sacas * valor_saca WHERE subtotal_cafe IS NULL OR subtotal_cafe=0")
    for table, column in [('compras', 'pessoa_id'), ('vendas', 'pessoa_id'), ('vendas', 'compra_id'),
                          ('provas', 'pessoa_id'), ('provas', 'compra_id'), ('adiantamentos', 'pessoa_id'),
                          ('financeiro', 'origem'), ('financeiro', 'data')]:
        cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column})')
    con.commit(); con.close()


def fetchall(query, params=()):
    con = db(); rows = con.execute(query, params).fetchall(); con.close(); return rows


def fetchone(query, params=()):
    con = db(); row = con.execute(query, params).fetchone(); con.close(); return row




def get_pessoas_choices(query=""):
    """Lista clientes/produtores para selects com busca, sem derrubar telas quando não há cadastro."""
    q = (query or '').strip()
    if q:
        like = f"%{q}%"
        return fetchall("""
            SELECT id, nome, tipo, documento, telefone, whatsapp, cidade, fazenda
            FROM pessoas
            WHERE normalizar(nome) LIKE normalizar(?) OR normalizar(documento) LIKE normalizar(?) OR normalizar(telefone) LIKE normalizar(?) OR normalizar(whatsapp) LIKE normalizar(?) OR normalizar(cidade) LIKE normalizar(?) OR normalizar(fazenda) LIKE normalizar(?)
            ORDER BY nome COLLATE NOCASE
            LIMIT 300
        """, (like, like, like, like, like, like))
    return fetchall("""
        SELECT id, nome, tipo, documento, telefone, whatsapp, cidade, fazenda
        FROM pessoas
        ORDER BY nome COLLATE NOCASE
        LIMIT 500
    """)

def log_acao(acao, entidade='', entidade_id=None, detalhe=''):
    try:
        con = db()
        con.execute("INSERT INTO historico (data_hora,entidade,entidade_id,acao,detalhe) VALUES (?,?,?,?,?)",
                    (datetime.now().isoformat(timespec='seconds'), entidade, entidade_id, acao, detalhe))
        con.commit(); con.close()
    except Exception:
        pass


def whatsapp_link(texto):
    return "https://wa.me/?text=" + urllib.parse.quote(texto or '')

app.jinja_env.globals['whatsapp_link'] = whatsapp_link


def safe_return_url(default_endpoint='vendas', **default_values):
    """Retorna para uma tela interna depois de editar/excluir, sem abrir redirecionamento externo."""
    destino = request.form.get('return_to') or request.args.get('return_to') or ''
    if destino.startswith('/') and not destino.startswith('//'):
        return destino
    return url_for(default_endpoint, **default_values)


def get_acerto_data(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        return None
    atualizar_adiantamentos_abertos(pessoa_id)
    vendas_rows = fetchall("SELECT * FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente') ORDER BY data DESC, id DESC", (pessoa_id,))
    adiantamentos_rows = [adiantamento_com_juros_atual(a) for a in fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? AND UPPER(TRIM(COALESCE(status,'Aberto'))) NOT IN ('PAGO','PAGA','QUITADO','QUITADA') ORDER BY data DESC, id DESC", (pessoa_id,))]
    estoque_tipo = fetchall(f"""SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas, SUM(({lote_estoque_expr()}) * c.valor_saca) valor
        FROM compras c WHERE c.pessoa_id=? GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_vendas = sum(float(v['valor_total'] or 0) for v in vendas_rows)
    adiant_sem = sum(float(a['valor'] or 0) for a in adiantamentos_rows)
    adiant_juros = sum(float(a['valor_juros'] or 0) for a in adiantamentos_rows)
    adiant_total = sum(float(a['valor_total'] or 0) for a in adiantamentos_rows)
    total = round(saldo_vendas - adiant_total, 2)
    texto = f"""Café Boa Vista\nAcerto do cliente\n\nCliente: {pessoa['nome']}\nVendas pendentes: {br_money(saldo_vendas)}\nValores que pegou: {br_money(adiant_sem)}\nJuros dos valores: {br_money(adiant_juros)}\nTotal para acerto: {br_money(total)}"""
    return dict(pessoa=pessoa, vendas=vendas_rows, adiantamentos=adiantamentos_rows, estoque_tipo=estoque_tipo,
                saldo_vendas=saldo_vendas, adiant_sem=adiant_sem, adiant_juros=adiant_juros,
                adiant_total=adiant_total, total=total, texto_whatsapp=texto, hoje=today())


def fnum(name):
    raw = str(request.form.get(name) or '0').strip().replace('R$', '').replace(' ', '')
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError('Número inválido.')
    return number


def today(): return datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()


def meses_juros_automatico(data_inicio, data_base=None):
    """Calcula meses completos entre a data que pegou e hoje.
    Ex.: 02/03 até 02/04 = 1 mês. Antes de virar o dia, não conta o novo mês.
    """
    try:
        inicio = datetime.strptime((data_inicio or today())[:10], '%Y-%m-%d').date()
    except Exception:
        inicio = date.today()
    base = data_base or date.fromisoformat(today())
    meses = (base.year - inicio.year) * 12 + (base.month - inicio.month)
    # Uma data como 31/01 completa um mês em 28/02 (ou 29/02).
    if base.day < min(inicio.day, monthrange(base.year, base.month)[1]):
        meses -= 1
    return max(0, meses)


def calcular_juros_simples(valor, taxa, meses):
    valor = float(valor or 0)
    taxa = float(taxa or 0)
    meses = float(meses or 0)
    juros = round(valor * (taxa / 100) * meses, 2)
    return juros, round(valor + juros, 2)


def adiantamento_em_aberto(row):
    status = str(row['status'] or 'Aberto').strip().lower()
    return status not in ('pago', 'paga', 'quitado', 'quitada')


def adiantamento_com_juros_atual(row):
    """Retorna o adiantamento recalculado pela data de hoje.
    Isso evita mostrar juros antigo mesmo quando o banco ainda guardou meses=0.
    """
    item = dict(row)
    if adiantamento_em_aberto(row):
        meses = meses_juros_automatico(item.get('data'))
        juros, total = calcular_juros_simples(item.get('valor'), item.get('taxa_juros'), meses)
        item['meses_atraso'] = meses
        item['valor_juros'] = juros
        item['valor_total'] = total
    return item


def atualizar_adiantamentos_abertos(pessoa_id=None):
    """Atualiza juros dos valores pegos em aberto conforme a data atual.
    Assim o total muda sozinho quando vira o mês, sem o cliente editar nada.
    """
    try:
        if pessoa_id:
            rows = fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? AND UPPER(TRIM(COALESCE(status,'Aberto'))) NOT IN ('PAGO','PAGA','QUITADO','QUITADA')", (pessoa_id,))
        else:
            rows = fetchall("SELECT * FROM adiantamentos WHERE UPPER(TRIM(COALESCE(status,'Aberto'))) NOT IN ('PAGO','PAGA','QUITADO','QUITADA')")
        if not rows:
            return
        con = db()
        for a in rows:
            meses = meses_juros_automatico(a['data'])
            juros, total = calcular_juros_simples(a['valor'], a['taxa_juros'], meses)
            con.execute("UPDATE adiantamentos SET meses_atraso=?, valor_juros=?, valor_total=? WHERE id=?",
                        (meses, juros, total, a['id']))
        con.commit(); con.close()
    except Exception as exc:
        try:
            print('Erro ao atualizar juros dos valores pegos:', exc)
        except Exception:
            pass




def get_lote_historico(compra_id):
    """Resumo completo de um lote/compra com vendas parciais e saldo restante."""
    compra = fetchone(f"""SELECT c.*, p.nome pessoa_nome, p.documento, p.telefone, p.whatsapp, p.cidade, p.fazenda,
        ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido,
        COALESCE((SELECT SUM(v.valor_total) FROM vendas v WHERE v.compra_id=c.id),0) valor_vendido,
        COALESCE((SELECT SUM(v.lucro_total) FROM vendas v WHERE v.compra_id=c.id),0) lucro_total_lote
        FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE c.id=?""", (compra_id,))
    if not compra:
        return None
    vendas_lote = fetchall("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, p.nome pessoa_nome
        FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id
        WHERE v.compra_id=? ORDER BY v.data ASC, v.id ASC""", (compra_id,))
    qtd_original = float(compra['quantidade_sacas'] or 0)
    vendido = float(compra['vendido'] or 0)
    restante = float(compra['estoque_lote'] or 0)
    valor_vendido = float(compra['valor_vendido'] or 0)
    texto = f"""Café Boa Vista\nHistórico de venda parcial do cliente\n\nCliente/fornecedor: {compra['pessoa_nome'] or 'Sem cadastro'}\nLote: {compra['lote'] or ('Lote ' + str(compra['id']))}\nTipo: {compra['tipo_cafe'] or '-'}\nComprado: {br_num(qtd_original)} sacas\nVendido pelo cliente: {br_num(vendido)} sacas\nRestante: {br_num(restante)} sacas\nTotal vendido pelo cliente: {br_money(valor_vendido)}"""
    return dict(compra=compra, vendas=vendas_lote, qtd_original=qtd_original, vendido=vendido,
                restante=restante, valor_vendido=valor_vendido, texto_whatsapp=texto, hoje=today())

def lote_estoque_expr():
    return """c.quantidade_sacas - COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0)"""


def calc_sacas(peso, divisor, ajuste, informada=0):
    if informada:
        return informada
    divisor = divisor or 60
    return (peso / divisor) + ajuste if peso else ajuste


def update_financeiro(origem, data, tipo, descricao, categoria, valor, status):
    con = db(); cur = con.cursor()
    cur.execute("DELETE FROM financeiro WHERE origem=?", (origem,))
    cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)", (data, tipo, descricao, categoria, valor, status, origem))
    con.commit(); con.close()


def update_compra_status(compra_id):
    con = db()
    try:
        atualizar_status_na_transacao(con, compra_id)
        con.commit()
    finally:
        con.close()


def update_all_status():
    con = db()
    try:
        for row in con.execute('SELECT id FROM compras').fetchall():
            atualizar_status_na_transacao(con, row['id'])
        con.commit()
    finally:
        con.close()


NUMERIC_FIELDS = {'peso_kg', 'divisor_saca', 'ajuste_sacas', 'quantidade_sacas', 'valor_saca',
    'frete', 'outras_despesas', 'quantidade', 'custo_saca', 'juros_percentual', 'meses_atraso',
    'valor', 'taxa_juros', 'venda_quantidade_sacas', 'venda_valor_saca', 'preco_compra',
    'preco_venda', 'despesas'}

@app.before_request
def validate_form():
    if request.method != 'POST':
        return
    try:
        for name in NUMERIC_FIELDS.intersection(request.form.keys()):
            number = fnum(name)
            if name != 'ajuste_sacas' and number < 0:
                raise ValueError('Valor negativo.')
        for name in ('data', 'venda_data'):
            if request.form.get(name):
                date.fromisoformat(request.form[name])
        if request.form.get('divisor_saca') and fnum('divisor_saca') <= 0:
            raise ValueError('Peso por saca inválido.')
        for field, table in [('pessoa_id', 'pessoas'), ('compra_id', 'compras')]:
            if request.form.get(field) and not fetchone(f'SELECT id FROM {table} WHERE id=?', (request.form[field],)):
                raise ValueError('Cadastro não encontrado.')
        if request.endpoint in ('pessoas', 'editar_pessoa') and not request.form.get('nome', '').strip():
            raise ValueError('Nome não informado.')
    except (ValueError, TypeError):
        flash('Confira os dados: use números válidos, valores positivos, uma data válida e um cadastro existente.', 'error')
        endpoint = request.endpoint or ''
        if endpoint in ('pessoas', 'compras', 'vendas', 'provas', 'financeiro', 'simulador'):
            return redirect(url_for(endpoint))
        if endpoint.startswith('editar_'):
            return redirect(url_for(endpoint, **request.view_args))
        return redirect(url_for({'adicionar_adiantamento':'clientes','prova_para_compra':'provas'}.get(endpoint,'index')))

def filtrar_operacoes(rows):
    q = normalizar_texto(request.args.get('q', '').strip())
    tipo = request.args.get('tipo_cafe', '')
    status = request.args.get('status', '')
    desde, ate = request.args.get('desde', ''), request.args.get('ate', '')
    return [r for r in rows
            if (not q or q in normalizar_texto(' '.join(str(r[k] or '') for k in ('pessoa_nome','lote','tipo_cafe','observacao') if k in r.keys())))
            and (not tipo or r['tipo_cafe'] == tipo)
            and (not desde or r['data'] >= desde) and (not ate or r['data'] <= ate)
            and (not status or any(({'Pendente':'A pagar ao cliente','Recebido':'Pago ao cliente'}.get(r[k],r[k]) if k=='status_recebimento' else r[k]) == status for k in ('status_lote','status_pagamento','status_recebimento') if k in r.keys()))]

def atualizar_status_na_transacao(con, compra_id):
    if not compra_id:
        return
    row = con.execute(f'SELECT c.*, ({lote_estoque_expr()}) estoque FROM compras c WHERE c.id=?', (compra_id,)).fetchone()
    if not row:
        return
    saldo = float(row['estoque'] or 0)
    status = 'Vendido' if saldo <= 0.0001 else 'Vendido parcial' if saldo < row['quantidade_sacas'] - 0.0001 else row['status_lote'] if row['status_lote'] in ('Em análise','Reservado') else 'Em estoque'
    con.execute('UPDATE compras SET status_lote=? WHERE id=?', (status, compra_id))

def gravar_venda(con, dados, venda_id=None):
    # A verificação do saldo e a gravação usam a mesma transação de escrita.
    qtd, preco = float(dados['quantidade_sacas']), float(dados['valor_saca'])
    if qtd <= 0 or preco <= 0:
        raise ValueError('Informe quantidade e valor por saca maiores que zero.')
    antiga = con.execute('SELECT * FROM vendas WHERE id=?', (venda_id,)).fetchone() if venda_id else None
    if venda_id and con.execute("SELECT id FROM financeiro WHERE origem=? AND status='Compensado'", (f'venda:{venda_id}',)).fetchone():
        raise ValueError('Esta venda já participou de um acerto. Preserve o registro para manter o caixa correto.')
    compra_id = dados.get('compra_id') or None
    compra = con.execute(f'SELECT c.*, ({lote_estoque_expr()}) estoque FROM compras c WHERE c.id=?', (compra_id,)).fetchone() if compra_id else None
    if compra_id and not compra:
        raise ValueError('Lote não encontrado.')
    pessoa_id = dados.get('pessoa_id') or (compra['pessoa_id'] if compra else None)
    if compra and compra['pessoa_id'] and str(pessoa_id) != str(compra['pessoa_id']):
        raise ValueError('O cliente da venda deve ser o proprietário do lote selecionado.')
    if compra:
        disponivel = float(compra['estoque'] or 0)
        if antiga and str(antiga['compra_id']) == str(compra_id):
            disponivel += float(antiga['quantidade_sacas'] or 0)
        if qtd > disponivel + 0.0001:
            raise ValueError(f'Esse lote tem apenas {br_num(disponivel)} sacas disponíveis.')
        custo = float(compra['valor_total'] or 0) / float(compra['quantidade_sacas'] or 1)
    else:
        custo = float(dados.get('custo_saca') or 0)
    lote = compra['lote'] if compra else dados.get('lote', '')
    tipo = compra['tipo_cafe'] if compra else dados.get('tipo_cafe', '')
    subtotal = round(qtd * preco, 2)
    taxa, meses = float(dados.get('juros_percentual') or 0), float(dados.get('meses_atraso') or 0)
    juros, total = calcular_juros_simples(subtotal, taxa, meses)
    lucro = round((preco - custo) * qtd, 2)
    status = dados.get('status_recebimento') or 'A pagar ao cliente'
    status = 'Pago ao cliente' if status in ('Recebido', 'Pago ao cliente') else 'A pagar ao cliente'
    valores = (pessoa_id, compra_id, dados['data'], lote, tipo, qtd, preco, subtotal, taxa, meses, juros, total, custo, lucro, status, dados.get('forma_pagamento'), dados.get('observacao'))
    campos = 'pessoa_id,compra_id,data,lote,tipo_cafe,quantidade_sacas,valor_saca,subtotal_cafe,juros_percentual,meses_atraso,valor_juros,valor_total,custo_saca,lucro_total,status_recebimento,forma_pagamento,observacao'
    if venda_id:
        con.execute('UPDATE vendas SET ' + ','.join(k + '=?' for k in campos.split(',')) + ' WHERE id=?', valores + (venda_id,))
    else:
        venda_id = con.execute('INSERT INTO vendas (' + campos + ') VALUES (' + ','.join('?' for _ in valores) + ')', valores).lastrowid
    origem = f'venda:{venda_id}'
    con.execute('DELETE FROM financeiro WHERE origem=?', (origem,))
    con.execute('INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)',
                (dados['data'], 'Saída', f'Pagamento de venda ao cliente - {lote or venda_id}', 'Pagamento ao cliente', total, 'Pago' if status == 'Pago ao cliente' else 'Pendente', origem))
    if antiga:
        atualizar_status_na_transacao(con, antiga['compra_id'])
    atualizar_status_na_transacao(con, compra_id)
    return venda_id

def venda_do_form():
    dados = request.form.to_dict()
    for campo in ('quantidade_sacas','valor_saca','custo_saca','juros_percentual','meses_atraso'):
        dados[campo] = fnum(campo)
    dados['data'] = dados.get('data') or today()
    return dados

def gravar_compra(con, compra_id=None):
    peso, divisor, ajuste = fnum('peso_kg'), fnum('divisor_saca') or 60, fnum('ajuste_sacas')
    qtd = round(calc_sacas(peso, divisor, ajuste, fnum('quantidade_sacas')), 2)
    if qtd <= 0:
        raise ValueError('Informe um peso ou uma quantidade de sacas maior que zero.')
    valor_saca, frete, despesas = fnum('valor_saca'), fnum('frete'), fnum('outras_despesas')
    total = round(qtd * valor_saca + frete + despesas, 2)
    if compra_id:
        vendido = con.execute('SELECT COALESCE(SUM(quantidade_sacas),0) FROM vendas WHERE compra_id=?', (compra_id,)).fetchone()[0]
        if qtd + 0.0001 < vendido:
            raise ValueError(f'Este lote já vendeu {br_num(vendido)} sacas. A quantidade do lote não pode ser menor.')
        antiga = con.execute('SELECT pessoa_id FROM compras WHERE id=?', (compra_id,)).fetchone()
        if vendido > 0 and str(antiga['pessoa_id'] or '') != str(request.form.get('pessoa_id') or ''):
            raise ValueError('Este lote já tem vendas. Mantenha o proprietário para preservar os acertos.')
    campos = 'pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,divisor_saca,ajuste_sacas,valor_saca,valor_total,status_pagamento,forma_pagamento,frete,outras_despesas,origem_cafe,status_lote,observacao'
    valores = (request.form.get('pessoa_id') or None, request.form.get('data') or today(), request.form.get('lote'), request.form.get('tipo_cafe'), qtd, peso, divisor, ajuste, valor_saca, total, request.form.get('status_pagamento') or 'Pendente', request.form.get('forma_pagamento'), frete, despesas, request.form.get('origem_cafe'), request.form.get('status_lote') or 'Em estoque', request.form.get('observacao'))
    if compra_id:
        con.execute('UPDATE compras SET ' + ','.join(k + '=?' for k in campos.split(',')) + ' WHERE id=?', valores + (compra_id,))
        # O custo dos lotes inclui frete e despesas. Juros ficam separados do lucro do café.
        con.execute('UPDATE vendas SET custo_saca=?, lucro_total=ROUND((valor_saca-?)*quantidade_sacas,2) WHERE compra_id=?', (total/qtd, total/qtd, compra_id))
    else:
        compra_id = con.execute('INSERT INTO compras (' + campos + ') VALUES (' + ','.join('?' for _ in valores) + ')', valores).lastrowid
    con.execute('DELETE FROM financeiro WHERE origem=?', (f'compra:{compra_id}',))
    con.execute('INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)',
                (valores[1], 'Saída', f'Compra de café - {request.form.get("lote") or compra_id}', 'Compra de café', total, valores[10], f'compra:{compra_id}'))
    atualizar_status_na_transacao(con, compra_id)
    return compra_id

def indicadores_caixa(rows):
    entrada = sum(r['valor'] for r in rows if r['tipo'] == 'Entrada' and r['status'] in ('Pago','Recebido'))
    saida = sum(r['valor'] for r in rows if r['tipo'] == 'Saída' and r['status'] in ('Pago','Recebido'))
    receber = sum(r['valor'] for r in rows if r['tipo'] == 'Entrada' and r['status'] == 'Pendente')
    pagar = sum(r['valor'] for r in rows if r['tipo'] == 'Saída' and r['status'] == 'Pendente')
    return dict(entrada=entrada, saida=saida, saldo=entrada-saida, receber=receber, pagar=pagar)

def financeiro_rows():
    sql, params = 'SELECT * FROM financeiro WHERE 1=1', []
    mes = request.args.get('mes', '')
    if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', mes):
        sql += ' AND substr(data,1,7)=?'; params.append(mes)
    for campo in ('tipo','status'):
        if request.args.get(campo):
            sql += f' AND {campo}=?'; params.append(request.args[campo])
    q = request.args.get('q', '').strip()
    if q:
        sql += ' AND (normalizar(descricao) LIKE normalizar(?) OR normalizar(categoria) LIKE normalizar(?))'; params.extend([f'%{q}%']*2)
    return fetchall(sql + ' ORDER BY data DESC, id DESC', params)

def dashboard_charts():
    atual = date.fromisoformat(today())
    labels = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    dados = []
    for offset in range(5,-1,-1):
        pos = atual.year*12 + atual.month-1 - offset
        ano, month = divmod(pos,12)
        mes = f'{ano:04d}-{month+1:02d}'
        valor = fetchone('SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE substr(data,1,7)=?', (mes,))['v']
        dados.append(dict(label=labels[month], periodo=mes, valor=valor))
    return dados


# Login removido temporariamente: o sistema entra direto enquanto finalizamos as regras de uso.
# A tabela usuarios pode continuar no banco sem atrapalhar, para recolocar login depois sem perder histórico.

def usuario_logado():
    return None

app.jinja_env.globals['usuario_logado'] = usuario_logado

@app.route('/')
def index():
    update_all_status()
    atualizar_adiantamentos_abertos()
    caixa = indicadores_caixa(fetchall('SELECT * FROM financeiro'))
    estoque_tipo = fetchall(f"SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas FROM compras c GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') HAVING sacas>0.0001 ORDER BY sacas DESC")
    estoque = sum(float(r['sacas']) for r in estoque_tipo)
    valor_estoque = fetchone(f'SELECT COALESCE(SUM(({lote_estoque_expr()}) * c.valor_saca),0) v FROM compras c')['v']
    total_vendas = fetchone('SELECT COALESCE(SUM(valor_total),0) v FROM vendas')['v']
    lucro = fetchone('SELECT COALESCE(SUM(lucro_total),0) v FROM vendas')['v']
    adiantamentos = [adiantamento_com_juros_atual(r) for r in fetchall('SELECT * FROM adiantamentos') if adiantamento_em_aberto(r)]
    principal = sum(a['valor'] or 0 for a in adiantamentos)
    juros = sum(a['valor_juros'] or 0 for a in adiantamentos)
    # Compensar por cliente impede o adiantamento de um produtor de reduzir o saldo de outro.
    saldos = fetchall("SELECT p.id, COALESCE((SELECT SUM(valor_total) FROM vendas WHERE pessoa_id=p.id AND status_recebimento IN ('Pendente','A pagar ao cliente')),0) vendas FROM pessoas p")
    dividas = {}
    for a in adiantamentos:
        dividas[a['pessoa_id']] = dividas.get(a['pessoa_id'], 0) + (a['valor_total'] or 0)
    sem_cadastro = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id IS NULL AND status_recebimento IN ('Pendente','A pagar ao cliente')")['v']
    liquido = sum(max(0, r['vendas']-dividas.get(r['id'],0)) for r in saldos) + sem_cadastro
    recuperar = sum(max(0, dividas.get(r['id'],0)-r['vendas']) for r in saldos)
    ultimas_compras = fetchall('SELECT c.*, p.nome pessoa_nome FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id ORDER BY c.data DESC,c.id DESC LIMIT 5')
    ultimas_vendas = fetchall("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, p.nome pessoa_nome FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id ORDER BY v.data DESC,v.id DESC LIMIT 5""")
    serie = dashboard_charts()
    anterior, atual = serie[-2]['valor'], serie[-1]['valor']
    variacao = ((atual-anterior)/anterior*100) if anterior else None
    return render_template('index.html', estoque=estoque, valor_estoque=valor_estoque, total_vendas=total_vendas,
        lucro=lucro, liquido_a_pagar_clientes=liquido, saldo_recuperar=recuperar,
        valores_clientes_pegaram=principal, juros_clientes_pegaram=juros,
        receber=caixa['receber'], pagar=caixa['pagar'], resultado_caixa=caixa['saldo'],
        ultimas_compras=ultimas_compras, ultimas_vendas=ultimas_vendas, estoque_tipo=estoque_tipo,
        serie_vendas=serie, vendas_mes=atual, variacao=variacao,
        qtd_clientes=fetchone('SELECT COUNT(*) n FROM pessoas')['n'],
        provas_analise=fetchone("SELECT COUNT(*) n FROM provas WHERE aprovado='Em análise'")['n'],
        qtd_lotes=fetchone(f'SELECT COUNT(*) n FROM compras c WHERE ({lote_estoque_expr()})>0.0001')['n'])


@app.route('/pessoas', methods=['GET','POST'])
def pessoas():
    if request.method == 'POST':
        con = db()
        con.execute("""INSERT INTO pessoas (tipo,nome,documento,telefone,whatsapp,cidade,endereco,fazenda,observacao,criado_em)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (request.form['tipo'], request.form['nome'].strip(), request.form.get('documento'), request.form.get('telefone'), request.form.get('whatsapp'), request.form.get('cidade'), request.form.get('endereco'), request.form.get('fazenda'), request.form.get('observacao'), datetime.now().isoformat()))
        con.commit(); con.close(); log_acao('Cadastro de pessoa criado', 'pessoa', None, request.form.get('nome')); flash('Cadastro salvo com sucesso.')
        return redirect(url_for('pessoas'))
    q = request.args.get('q','').strip()
    sql = "SELECT * FROM pessoas"
    params = ()
    if q:
        sql += " WHERE normalizar(nome) LIKE normalizar(?) OR normalizar(telefone) LIKE normalizar(?) OR normalizar(whatsapp) LIKE normalizar(?) OR normalizar(cidade) LIKE normalizar(?) OR normalizar(documento) LIKE normalizar(?)"
        params = tuple([f'%{q}%']*5)
    rows = fetchall(sql + " ORDER BY id DESC", params)
    return render_template('pessoas.html', pessoas=rows, q=q)


@app.route('/pessoas/<int:pessoa_id>/editar', methods=['GET','POST'])
def editar_pessoa(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('pessoas'))
    if request.method == 'POST':
        con = db()
        con.execute("""UPDATE pessoas SET tipo=?, nome=?, documento=?, telefone=?, whatsapp=?, cidade=?, endereco=?, fazenda=?, observacao=? WHERE id=?""",
                    (request.form['tipo'], request.form['nome'].strip(), request.form.get('documento'), request.form.get('telefone'), request.form.get('whatsapp'), request.form.get('cidade'), request.form.get('endereco'), request.form.get('fazenda'), request.form.get('observacao'), pessoa_id))
        con.commit(); con.close(); log_acao('Cadastro de pessoa editado', 'pessoa', pessoa_id, pessoa['nome']); flash('Cadastro atualizado.')
        return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))
    return render_template('editar_pessoa.html', pessoa=pessoa)


@app.route('/pessoas/<int:pessoa_id>/excluir', methods=['POST'])
def excluir_pessoa(pessoa_id):
    con = db()
    if any(con.execute(f'SELECT id FROM {table} WHERE pessoa_id=? LIMIT 1', (pessoa_id,)).fetchone() for table in ('compras','vendas','adiantamentos')):
        con.close()
        flash('Este cadastro possui movimentações. Mantenha-o para preservar o estoque e os acertos.', 'error')
        return redirect(url_for('pessoas'))
    con.execute("UPDATE compras SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("UPDATE vendas SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("UPDATE provas SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("DELETE FROM contas_cliente WHERE pessoa_id=?", (pessoa_id,))
    con.execute("DELETE FROM pessoas WHERE id=?", (pessoa_id,))
    con.commit(); con.close(); log_acao('Cliente excluído', 'pessoa', pessoa_id, 'Históricos mantidos sem vínculo'); flash('Cliente removido. Históricos foram mantidos sem vínculo.')
    return redirect(url_for('pessoas'))



@app.route('/clientes')
def clientes():
    q = request.args.get('q','').strip()
    sql = "SELECT * FROM pessoas WHERE 1=1"
    params = []
    if q:
        sql += " AND (normalizar(nome) LIKE normalizar(?) OR normalizar(documento) LIKE normalizar(?) OR normalizar(telefone) LIKE normalizar(?) OR normalizar(whatsapp) LIKE normalizar(?) OR normalizar(cidade) LIKE normalizar(?) OR normalizar(fazenda) LIKE normalizar(?))"
        like = f"%{q}%"
        params = [like, like, like, like, like, like]
    sql += " ORDER BY nome"
    rows = fetchall(sql, params)
    return render_template('clientes.html', clientes=rows, q=q)


def calcular_adiantamento(valor, taxa, data_inicio=None, meses=None):
    # Agora os meses são calculados automaticamente pela data que o cliente pegou.
    # Mantém o parâmetro meses por compatibilidade, mas a regra principal é pela data.
    meses_calc = meses_juros_automatico(data_inicio) if data_inicio else float(meses or 0)
    juros, total = calcular_juros_simples(valor, taxa, meses_calc)
    return meses_calc, juros, total


@app.route('/clientes/<int:pessoa_id>/adiantamentos', methods=['POST'])
def adicionar_adiantamento(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    valor = fnum('valor')
    taxa = fnum('taxa_juros')
    data = request.form.get('data') or today()
    obs = request.form.get('observacao') or ''
    meses, juros, total = calcular_adiantamento(valor, taxa, data_inicio=data)
    if valor <= 0:
        flash('Informe o valor que o cliente pegou.')
        return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))
    con = db(); cur = con.cursor()
    cur.execute("""INSERT INTO adiantamentos (pessoa_id,data,valor,taxa_juros,meses_atraso,valor_juros,valor_total,observacao,status,criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""", (pessoa_id, data, valor, taxa, meses, juros, total, obs, request.form.get('status') or 'Aberto', datetime.now().isoformat(timespec='seconds')))
    aid = cur.lastrowid
    if request.form.get('lancar_financeiro') == '1':
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (data, 'Saída', f"Valor pego por {pessoa['nome']} - adiantamento #{aid}", 'Adiantamento ao cliente', valor, 'Pago', f"adiantamento:{aid}"))
    con.commit(); con.close()
    log_acao('Valor pego lançado', 'adiantamento', aid, f"Pessoa #{pessoa_id} - {br_money(valor)}")
    flash('Valor pego salvo no painel do cliente.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))


@app.route('/adiantamentos/<int:adiantamento_id>/excluir', methods=['POST'])
def excluir_adiantamento(adiantamento_id):
    row = fetchone("SELECT * FROM adiantamentos WHERE id=?", (adiantamento_id,))
    if not row:
        flash('Registro não encontrado.'); return redirect(url_for('clientes'))
    con = db()
    con.execute("DELETE FROM financeiro WHERE origem=?", (f"adiantamento:{adiantamento_id}",))
    con.execute("DELETE FROM adiantamentos WHERE id=?", (adiantamento_id,))
    con.commit(); con.close()
    flash('Valor pego excluído do painel.')
    return redirect(url_for('painel_cliente', pessoa_id=row['pessoa_id']))


@app.route('/adiantamentos/<int:adiantamento_id>/baixar', methods=['POST'])
def baixar_adiantamento(adiantamento_id):
    row = fetchone("SELECT * FROM adiantamentos WHERE id=?", (adiantamento_id,))
    if not row:
        flash('Registro não encontrado.'); return redirect(url_for('clientes'))
    con = db()
    con.execute("UPDATE adiantamentos SET status='Pago' WHERE id=?", (adiantamento_id,))
    con.commit(); con.close()
    log_acao('Adiantamento marcado como pago', 'adiantamento', adiantamento_id, '')
    flash('Adiantamento marcado como pago.')
    return redirect(url_for('painel_cliente', pessoa_id=row['pessoa_id']))


@app.route('/clientes/<int:pessoa_id>')
def painel_cliente(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('pessoas'))
    atualizar_adiantamentos_abertos(pessoa_id)
    taxa = max(0, request.args.get('taxa_juros', 0, type=float) or 0)
    meses = max(0, request.args.get('meses_atraso', 0, type=float) or 0)
    if not math.isfinite(taxa): taxa = 0
    if not math.isfinite(meses): meses = 0
    vendas_rows = fetchall("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, c.lote lote_compra FROM vendas v LEFT JOIN compras c ON c.id=v.compra_id WHERE v.pessoa_id=? ORDER BY v.id DESC""", (pessoa_id,))
    compras_rows = fetchall(f"""SELECT c.*, ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido
        FROM compras c WHERE c.pessoa_id=? ORDER BY c.id DESC""", (pessoa_id,))
    provas_rows = fetchall("""SELECT pr.*, c.lote FROM provas pr LEFT JOIN compras c ON c.id=pr.compra_id WHERE pr.pessoa_id=? ORDER BY pr.id DESC""", (pessoa_id,))
    estoque_tipo = fetchall(f"""SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas, SUM(({lote_estoque_expr()}) * c.valor_saca) valor
        FROM compras c WHERE c.pessoa_id=? GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_tipo = fetchall("""SELECT COALESCE(tipo_cafe,'Sem tipo') tipo, SUM(valor_total) valor, SUM(quantidade_sacas) sacas
        FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente') GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_pendente = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente')", (pessoa_id,))['v']
    adiantamentos = [adiantamento_com_juros_atual(a) for a in fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? ORDER BY data DESC, id DESC", (pessoa_id,))]
    adiantamentos_abertos = [a for a in adiantamentos if adiantamento_em_aberto(a)]
    total_adiantamentos = sum(float(a.get('valor') or 0) for a in adiantamentos_abertos)
    juros_adiantamentos = sum(float(a.get('valor_juros') or 0) for a in adiantamentos_abertos)
    total_adiantamentos_juros = sum(float(a.get('valor_total') or 0) for a in adiantamentos_abertos)
    juros = saldo_pendente * (taxa/100) * meses
    contas = fetchall("SELECT * FROM contas_cliente WHERE pessoa_id=? ORDER BY id DESC", (pessoa_id,))
    return render_template('cliente_painel.html', pessoa=pessoa, vendas=vendas_rows, compras=compras_rows, provas=provas_rows,
                           estoque_tipo=estoque_tipo, saldo_tipo=saldo_tipo, saldo_pendente=saldo_pendente,
                           taxa=taxa, meses=meses, juros=juros, total_com_juros=saldo_pendente+juros, tipos_cafe=TIPOS_CAFE,
                           adiantamentos=adiantamentos, total_adiantamentos=total_adiantamentos,
                           juros_adiantamentos=juros_adiantamentos, total_adiantamentos_juros=total_adiantamentos_juros, contas=contas, hoje=today())


@app.route('/clientes/<int:pessoa_id>/aplicar-juros', methods=['POST'])
def aplicar_juros_cliente(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    taxa = fnum('taxa_juros')
    meses = fnum('meses_atraso')
    saldo = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente')", (pessoa_id,))['v']
    juros = float(saldo or 0) * (taxa/100) * meses
    if juros <= 0:
        flash('Nenhum juros para aplicar. Confira taxa, meses e saldo pendente.')
        return redirect(url_for('painel_cliente', pessoa_id=pessoa_id, taxa_juros=taxa, meses_atraso=meses))
    con = db()
    con.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                (today(), 'Entrada', f"Juros de atraso - {pessoa['nome']} ({taxa}% x {meses} mês(es))", 'Juros de atraso', juros, 'Pendente', f"juros:{pessoa_id}:{datetime.now().timestamp()}"))
    con.commit(); con.close()
    flash('Juros lançado no financeiro como entrada pendente.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id, taxa_juros=taxa, meses_atraso=meses))


@app.route('/clientes/<int:pessoa_id>/contas', methods=['POST'])
def adicionar_conta_cliente(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('pessoas'))
    banco = request.form.get('banco') or ''
    agencia = request.form.get('agencia') or ''
    conta = request.form.get('conta') or ''
    pix = request.form.get('pix') or ''
    titular = request.form.get('titular') or pessoa['nome']
    cpf = request.form.get('cpf') or pessoa['documento'] or ''
    obs = request.form.get('observacao') or ''
    if not any([banco, agencia, conta, pix, obs]):
        flash('Conta/Pix não salva: preencha banco, conta ou Pix.')
        return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))
    con = db(); cur = con.cursor()
    cur.execute("""INSERT INTO contas_cliente (pessoa_id,banco,agencia,conta,tipo_conta,pix,titular,cpf,observacao,criado_em)
                 VALUES (?,?,?,?,?,?,?,?,?,?)""", (pessoa_id,banco,agencia,conta,request.form.get('tipo_conta') or '',pix,titular,cpf,obs,datetime.now().isoformat()))
    cid = cur.lastrowid
    con.commit(); con.close()
    log_acao('Conta/Pix do cliente cadastrada', 'conta_cliente', cid, f"{pessoa['nome']} - {banco or pix}")
    flash('Conta/Pix salvo no cadastro do cliente.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))


@app.route('/contas-cliente/<int:conta_id>/excluir', methods=['POST'])
def excluir_conta_cliente(conta_id):
    conta = fetchone("SELECT * FROM contas_cliente WHERE id=?", (conta_id,))
    if not conta:
        flash('Conta/Pix não encontrada.'); return redirect(url_for('clientes'))
    pessoa_id = conta['pessoa_id']
    con = db(); con.execute("DELETE FROM contas_cliente WHERE id=?", (conta_id,)); con.commit(); con.close()
    log_acao('Conta/Pix do cliente excluída', 'conta_cliente', conta_id, '')
    flash('Conta/Pix excluída.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))


@app.route('/compras', methods=['GET','POST'])
def compras():
    if request.method == 'POST':
        con = db()
        try:
            con.execute('BEGIN IMMEDIATE')
            compra_id = gravar_compra(con)
            con.commit()
            log_acao('Compra lançada', 'compra', compra_id, request.form.get('lote'))
            flash('Compra salva. Estoque e financeiro atualizados.', 'success')
        except ValueError as exc:
            con.rollback(); flash(str(exc), 'error')
        finally:
            con.close()
        return redirect(url_for('compras'))
    rows = fetchall(f"SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote, COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id ORDER BY c.data DESC,c.id DESC")
    return render_template('compras.html', compras=filtrar_operacoes(rows), pessoas=get_pessoas_choices(), hoje=today(), tipos_cafe=TIPOS_CAFE)


@app.route('/compras/<int:compra_id>/editar', methods=['GET','POST'])
def editar_compra(compra_id):
    compra = fetchone('SELECT * FROM compras WHERE id=?', (compra_id,))
    if not compra:
        flash('Compra não encontrada.'); return redirect(url_for('compras'))
    if request.method == 'POST':
        con = db()
        try:
            con.execute('BEGIN IMMEDIATE')
            gravar_compra(con, compra_id)
            venda_id = None
            if request.form.get('venda_quantidade_sacas') or request.form.get('venda_valor_saca'):
                dados = dict(compra_id=compra_id, pessoa_id=request.form.get('pessoa_id'),
                    data=request.form.get('venda_data') or today(), quantidade_sacas=fnum('venda_quantidade_sacas'),
                    valor_saca=fnum('venda_valor_saca'), status_recebimento=request.form.get('venda_status_recebimento'),
                    forma_pagamento=request.form.get('venda_forma_pagamento'), observacao=request.form.get('venda_observacao'))
                venda_id = gravar_venda(con, dados)
            con.commit()
            log_acao('Compra editada', 'compra', compra_id, 'Estoque e custos recalculados')
            if venda_id:
                log_acao('Venda parcial lançada pela compra', 'venda', venda_id, f'Lote #{compra_id}')
            flash('Lote atualizado.' + (' Venda parcial registrada e saldo recalculado.' if venda_id else ''), 'success')
        except ValueError as exc:
            con.rollback(); flash(str(exc) + ' Nenhuma alteração foi salva.', 'error')
        finally:
            con.close()
        return redirect(url_for('editar_compra', compra_id=compra_id))
    return render_template('editar_compra.html', compra=compra, pessoas=get_pessoas_choices(), tipos_cafe=TIPOS_CAFE, historico=get_lote_historico(compra_id), hoje=today())


@app.route('/compras/<int:compra_id>/excluir', methods=['POST'])
def excluir_compra(compra_id):
    con = db()
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT id FROM vendas WHERE compra_id=? LIMIT 1', (compra_id,)).fetchone():
            flash('Este lote tem vendas. Remova ou transfira as vendas antes de excluir o lote.', 'error')
            return redirect(url_for('compras'))
        con.execute('DELETE FROM financeiro WHERE origem=?', (f'compra:{compra_id}',))
        con.execute('UPDATE provas SET compra_id=NULL WHERE compra_id=?', (compra_id,))
        con.execute('DELETE FROM compras WHERE id=?', (compra_id,))
        con.commit()
    finally:
        con.close()
    log_acao('Compra excluída', 'compra', compra_id, 'Provas preservadas sem vínculo')
    flash('Compra excluída. As provas foram preservadas.', 'success')
    return redirect(url_for('compras'))


@app.route('/provas', methods=['GET','POST'])
def provas():
    compras_rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    pessoas_rows = get_pessoas_choices("")
    if request.method == 'POST':
        pessoa_id = request.form.get('pessoa_id') or None
        compra_id = request.form.get('compra_id') or None
        if compra_id and not pessoa_id:
            compra = fetchone("SELECT pessoa_id FROM compras WHERE id=?", (compra_id,))
            pessoa_id = compra['pessoa_id'] if compra else None
        quantidade = fnum('quantidade_sacas') or fnum('quantidade')
        cata = normalizar_cata(request.form.get('cata'))
        nome_avulso = (request.form.get('nome_avulso') or '').strip()
        bebida = (request.form.get('bebida') or '').strip()
        observacao = (request.form.get('observacao') or '').strip()
        # Evita salvar prova em branco quando o usuário aperta Enter em campo de busca.
        if not any([pessoa_id, compra_id, cata, nome_avulso, quantidade, bebida, observacao, request.form.get('nota'), request.form.get('classificacao')]):
            flash('Nenhuma prova foi salva: preencha cliente/nome avulso, cata, quantidade ou bebida antes de salvar.')
            return redirect(url_for('provas'))
        con = db()
        con.execute("""INSERT INTO provas (pessoa_id,compra_id,data,cata,nome_cliente,nome_avulso,quantidade,quantidade_sacas,bebida,peneira,umidade,defeitos,aroma,corpo,acidez,docura,nota,classificacao,aprovado,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pessoa_id, compra_id, (request.form.get('data') or today()), cata, request.form.get('nome_cliente'), nome_avulso, quantidade, quantidade, bebida, request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('aroma'), request.form.get('corpo'), request.form.get('acidez'), request.form.get('docura'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('aprovado') or 'Em análise', observacao))
        pid = con.execute('SELECT last_insert_rowid()').fetchone()[0]
        con.commit(); con.close(); log_acao('Prova registrada', 'prova', pid, f"{nome_avulso or pessoa_id or ''} - {bebida}"); flash('Prova registrada e salva no painel do cliente quando tiver cadastro selecionado.')
        return redirect(url_for('provas'))
    rows = fetchall("""SELECT provas.*, compras.lote, compras.tipo_cafe, pessoas.nome pessoa_nome FROM provas LEFT JOIN compras ON compras.id = provas.compra_id LEFT JOIN pessoas ON pessoas.id = COALESCE(provas.pessoa_id, compras.pessoa_id) ORDER BY provas.id DESC""")
    return render_template('provas.html', provas=rows, compras=compras_rows, pessoas=pessoas_rows, hoje=today(), tipos_cafe=TIPOS_CAFE)


@app.route('/provas/<int:prova_id>/editar', methods=['GET','POST'])
def editar_prova(prova_id):
    prova = fetchone("SELECT * FROM provas WHERE id=?", (prova_id,))
    if not prova:
        flash('Prova não encontrada.')
        return redirect(url_for('provas'))
    compras_rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    pessoas_rows = get_pessoas_choices("")
    if request.method == 'POST':
        pessoa_id = request.form.get('pessoa_id') or None
        compra_id = request.form.get('compra_id') or None
        if compra_id and not pessoa_id:
            compra = fetchone("SELECT pessoa_id FROM compras WHERE id=?", (compra_id,))
            pessoa_id = compra['pessoa_id'] if compra else None
        quantidade = fnum('quantidade_sacas') or fnum('quantidade')
        cata = normalizar_cata(request.form.get('cata'))
        con = db()
        con.execute("""UPDATE provas SET pessoa_id=?, compra_id=?, data=?, cata=?, nome_cliente=?, nome_avulso=?, quantidade=?, quantidade_sacas=?, bebida=?, peneira=?, umidade=?, defeitos=?, aroma=?, corpo=?, acidez=?, docura=?, nota=?, classificacao=?, aprovado=?, observacao=? WHERE id=?""",
                    (pessoa_id, compra_id, (request.form.get('data') or today()), cata, request.form.get('nome_cliente'), request.form.get('nome_avulso'), quantidade, quantidade, request.form.get('bebida'), request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('aroma'), request.form.get('corpo'), request.form.get('acidez'), request.form.get('docura'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('aprovado') or 'Em análise', request.form.get('observacao'), prova_id))
        con.commit(); con.close()
        log_acao('Prova editada', 'prova', prova_id, '')
        flash('Prova atualizada com sucesso.')
        return redirect(url_for('provas'))
    return render_template('editar_prova.html', prova=prova, compras=compras_rows, pessoas=pessoas_rows, tipos_cafe=TIPOS_CAFE)


@app.route('/provas/<int:prova_id>/excluir', methods=['POST'])
def excluir_prova(prova_id):
    prova = fetchone("SELECT * FROM provas WHERE id=?", (prova_id,))
    if not prova:
        flash('Prova não encontrada.')
        return redirect(url_for('provas'))
    if prova['compra_id']:
        flash('Essa prova já virou compra. Para evitar bagunça no estoque, exclua ou edite a compra vinculada primeiro.')
        return redirect(url_for('provas'))
    con = db()
    con.execute("DELETE FROM provas WHERE id=?", (prova_id,))
    con.commit(); con.close()
    log_acao('Prova excluída', 'prova', prova_id, '')
    flash('Prova excluída com sucesso.')
    return redirect(url_for('provas'))


@app.route('/provas/<int:prova_id>/transformar-compra', methods=['POST'])
def prova_para_compra(prova_id):
    con = db()
    try:
        con.execute('BEGIN IMMEDIATE')
        prova = con.execute('SELECT * FROM provas WHERE id=?', (prova_id,)).fetchone()
        if not prova:
            flash('Prova não encontrada.', 'error')
            return redirect(url_for('provas'))
        if prova['compra_id']:
            flash('Esta prova já está vinculada a uma compra.', 'error')
            return redirect(url_for('provas'))
        preco = fnum('valor_saca')
        qtd = float(prova['quantidade_sacas'] or prova['quantidade'] or 0)
        if qtd<=0 or preco<=0:
            flash('Informe quantidade na prova e preço por saca antes de transformar em compra.', 'error')
            return redirect(url_for('provas'))
        pessoa_id = prova['pessoa_id']
        if not pessoa_id:
            nome = prova['nome_avulso'] or prova['nome_cliente'] or 'Cliente avulso'
            pessoa_id = con.execute('INSERT INTO pessoas (tipo,nome,criado_em) VALUES (?,?,?)', ('Cliente e Fornecedor',nome,datetime.now().isoformat())).lastrowid
        lote = request.form.get('lote') or f'Prova {prova_id}'
        tipo = prova['bebida'] or request.form.get('tipo_cafe')
        total = round(qtd*preco,2)
        status = request.form.get('status_pagamento') or 'Pendente'
        compra_id = con.execute('INSERT INTO compras (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,divisor_saca,ajuste_sacas,valor_saca,valor_total,status_pagamento,forma_pagamento,status_lote,observacao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (pessoa_id,today(),lote,tipo,qtd,0,60,0,preco,total,status,request.form.get('forma_pagamento'),'Em estoque',f'Compra gerada pela prova #{prova_id}')).lastrowid
        con.execute("UPDATE provas SET pessoa_id=?,compra_id=?,aprovado='Aprovado' WHERE id=?", (pessoa_id,compra_id,prova_id))
        con.execute('INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)',(today(),'Saída',f'Compra de café - {lote}','Compra de café',total,status,f'compra:{compra_id}'))
        con.commit()
    finally:
        con.close()
    log_acao('Prova transformada em compra','prova',prova_id,f'Compra #{compra_id}')
    flash('Prova aprovada e compra criada no estoque do cliente.', 'success')
    return redirect(url_for('painel_cliente',pessoa_id=pessoa_id))


@app.route('/vendas', methods=['GET','POST'])
def vendas():
    if request.method == 'POST':
        con = db()
        try:
            con.execute('BEGIN IMMEDIATE')
            venda_id = gravar_venda(con, venda_do_form())
            con.commit()
            log_acao('Venda lançada', 'venda', venda_id, f"{br_num(fnum('quantidade_sacas'))} sacas")
            flash('Venda salva. Saldo do lote e financeiro atualizados.', 'success')
        except ValueError as exc:
            con.rollback(); flash(str(exc), 'error')
        finally:
            con.close()
        return redirect(url_for('vendas'))
    lotes_rows = fetchall(f'SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE ({lote_estoque_expr()})>0.0001 ORDER BY c.id DESC')
    rows = fetchall("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, p.nome pessoa_nome FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id ORDER BY v.data DESC,v.id DESC""")
    return render_template('vendas.html', vendas=filtrar_operacoes(rows), pessoas=get_pessoas_choices(), lotes=lotes_rows, hoje=today(), tipos_cafe=TIPOS_CAFE)


@app.route('/vendas/<int:venda_id>/editar', methods=['GET','POST'])
def editar_venda(venda_id):
    venda = fetchone('SELECT * FROM vendas WHERE id=?', (venda_id,))
    if not venda:
        flash('Venda não encontrada.'); return redirect(url_for('vendas'))
    if fetchone("SELECT id FROM financeiro WHERE origem=? AND status='Compensado'", (f'venda:{venda_id}',)):
        flash('Esta venda já participou de um acerto. Consulte o recibo para conferir o histórico.', 'error')
        return redirect(safe_return_url('vendas'))
    if request.method == 'POST':
        con = db()
        try:
            con.execute('BEGIN IMMEDIATE')
            gravar_venda(con, venda_do_form(), venda_id)
            con.commit()
            log_acao('Venda editada', 'venda', venda_id, 'Saldo e custo recalculados')
            flash('Venda atualizada. Saldo do lote e financeiro recalculados.', 'success')
        except ValueError as exc:
            con.rollback(); flash(str(exc), 'error')
            return redirect(url_for('editar_venda', venda_id=venda_id, return_to=safe_return_url()))
        finally:
            con.close()
        return redirect(safe_return_url('vendas'))
    lotes_rows = fetchall(f'SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE ({lote_estoque_expr()})>0.0001 OR c.id=? ORDER BY c.id DESC', (venda['compra_id'] or 0,))
    return render_template('editar_venda.html', venda=venda, pessoas=get_pessoas_choices(), lotes=lotes_rows, tipos_cafe=TIPOS_CAFE, return_to=safe_return_url())


@app.route('/vendas/<int:venda_id>/excluir', methods=['POST'])
def excluir_venda(venda_id):
    con = db()
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute("SELECT id FROM financeiro WHERE origem=? AND status='Compensado'", (f'venda:{venda_id}',)).fetchone():
            flash('Esta venda já participou de um acerto e precisa ser preservada.', 'error')
            return redirect(safe_return_url('vendas'))
        venda = con.execute('SELECT compra_id FROM vendas WHERE id=?', (venda_id,)).fetchone()
        con.execute('DELETE FROM financeiro WHERE origem=?', (f'venda:{venda_id}',))
        con.execute('DELETE FROM vendas WHERE id=?', (venda_id,))
        if venda:
            atualizar_status_na_transacao(con, venda['compra_id'])
        con.commit()
    finally:
        con.close()
    log_acao('Venda excluída', 'venda', venda_id, 'Estoque recalculado')
    flash('Venda excluída. O saldo foi devolvido ao lote.', 'success')
    return redirect(safe_return_url('vendas'))


@app.route('/lotes')
def lotes():
    update_all_status()
    rows = fetchall(f"""SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido,
        COALESCE((SELECT SUM(v.lucro_total) FROM vendas v WHERE v.compra_id=c.id),0) lucro
        FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id ORDER BY c.id DESC""")
    return render_template('lotes.html', lotes=filtrar_operacoes(rows))


@app.route('/compras/<int:compra_id>/historico')
def historico_lote(compra_id):
    dados = get_lote_historico(compra_id)
    if not dados:
        flash('Lote/compra não encontrado.')
        return redirect(url_for('compras'))
    return render_template('recibo_lote.html', **dados)


@app.route('/financeiro', methods=['GET','POST'])
def financeiro():
    if request.method == 'POST':
        descricao = request.form.get('descricao', '').strip()
        if not descricao or fnum('valor') <= 0 or request.form.get('tipo') not in ('Entrada','Saída'):
            flash('Informe descrição, tipo e um valor maior que zero.', 'error')
            return redirect(url_for('financeiro'))
        con = db()
        cur = con.execute('INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)',
            (request.form.get('data') or today(), request.form['tipo'], descricao, request.form.get('categoria'), round(fnum('valor'),2), request.form.get('status') or 'Pendente', 'manual'))
        item_id = cur.lastrowid
        con.commit(); con.close()
        log_acao('Lançamento financeiro criado', 'financeiro', item_id, descricao)
        flash('Lançamento salvo.', 'success')
        return redirect(url_for('financeiro'))
    itens = financeiro_rows()
    return render_template('financeiro.html', itens=itens, hoje=today(), **indicadores_caixa(itens))



@app.route('/financeiro/<int:item_id>/baixar', methods=['POST'])
def baixar_financeiro(item_id):
    con = db()
    try:
        con.execute('BEGIN IMMEDIATE')
        item = con.execute('SELECT * FROM financeiro WHERE id=?', (item_id,)).fetchone()
        if not item or item['status'] != 'Pendente':
            flash('O lançamento já foi baixado ou não está disponível.', 'error')
            return redirect(safe_return_url('financeiro'))
        origem = item['origem'] or ''
        status = 'Recebido' if item['tipo']=='Entrada' else 'Pago'
        con.execute('UPDATE financeiro SET status=? WHERE id=?', (status,item_id))
        if origem.startswith('compra:'):
            con.execute("UPDATE compras SET status_pagamento='Pago' WHERE id=?", (origem.split(':')[1],))
        elif origem.startswith('venda:'):
            con.execute("UPDATE vendas SET status_recebimento='Pago ao cliente' WHERE id=?", (origem.split(':')[1],))
        con.commit()
    finally:
        con.close()
    log_acao('Baixa financeira realizada', 'financeiro', item_id, item['descricao'])
    flash('Baixa registrada. O lançamento de origem também foi atualizado.', 'success')
    return redirect(safe_return_url('financeiro'))

@app.route('/financeiro/<int:item_id>/editar', methods=['GET','POST'])
def editar_financeiro(item_id):
    item = fetchone('SELECT * FROM financeiro WHERE id=?', (item_id,))
    if not item or item['origem'] != 'manual':
        flash('Edite este lançamento pela compra ou venda de origem.', 'error')
        return redirect(url_for('financeiro'))
    if request.method == 'POST':
        if fnum('valor') <= 0 or not request.form.get('descricao','').strip() or request.form.get('tipo') not in ('Entrada','Saída'):
            flash('Preencha descrição, tipo e um valor maior que zero.', 'error')
            return redirect(url_for('editar_financeiro',item_id=item_id))
        con = db()
        con.execute('UPDATE financeiro SET data=?,tipo=?,categoria=?,descricao=?,valor=?,status=? WHERE id=?',
                    (request.form.get('data') or today(), request.form['tipo'],request.form.get('categoria'),request.form['descricao'].strip(),round(fnum('valor'),2),request.form.get('status') or 'Pendente',item_id))
        con.commit(); con.close()
        log_acao('Lançamento financeiro editado', 'financeiro', item_id, request.form['descricao'])
        flash('Lançamento atualizado.', 'success')
        return redirect(url_for('financeiro'))
    return render_template('editar_financeiro.html',item=item)

@app.route('/financeiro/<int:item_id>/excluir', methods=['POST'])
def excluir_financeiro(item_id):
    con = db()
    cur = con.execute("DELETE FROM financeiro WHERE id=? AND origem='manual'", (item_id,))
    removido = cur.rowcount
    con.commit(); con.close()
    if removido:
        log_acao('Lançamento financeiro excluído', 'financeiro', item_id, '')
    flash('Lançamento excluído.' if removido else 'Este lançamento deve ser alterado pela operação de origem.', 'success' if removido else 'error')
    return redirect(safe_return_url('financeiro'))


@app.route('/relatorios')
def relatorios():
    compras_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total FROM compras GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY total DESC")
    vendas_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total, SUM(lucro_total) lucro FROM vendas GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY total DESC")
    ranking_produtores = fetchall("""SELECT p.nome, SUM(c.quantidade_sacas) sacas, SUM(c.valor_total) total, AVG(CAST(pr.nota AS REAL)) nota_media FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id LEFT JOIN (SELECT compra_id, AVG(CAST(REPLACE(NULLIF(nota,''),',','.') AS REAL)) nota FROM provas GROUP BY compra_id) pr ON pr.compra_id=c.id GROUP BY p.id ORDER BY sacas DESC LIMIT 10""")
    ranking_clientes = fetchall("""SELECT p.nome, SUM(v.quantidade_sacas) sacas, SUM(v.valor_total) total, SUM(v.lucro_total) lucro FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id GROUP BY p.id ORDER BY total DESC LIMIT 10""")
    pendencias = fetchall("SELECT * FROM financeiro WHERE status='Pendente' ORDER BY data DESC")
    analise_qtd = fetchone("SELECT COUNT(*) c FROM provas WHERE COALESCE(aprovado,'Em análise')='Em análise'")['c']
    return render_template('relatorios.html', compras_tipo=compras_tipo, vendas_tipo=vendas_tipo, ranking_produtores=ranking_produtores, ranking_clientes=ranking_clientes, pendencias=pendencias, analise_qtd=analise_qtd)


@app.route('/simulador', methods=['GET','POST'])
def simulador():
    result = None
    if request.method == 'POST':
        qtd, compra, venda, frete, despesas = fnum('quantidade'), fnum('preco_compra'), fnum('preco_venda'), fnum('frete'), fnum('despesas')
        bruto = (venda-compra)*qtd
        liquido = bruto - frete - despesas
        investimento = compra*qtd + frete + despesas
        margem = (liquido / investimento * 100) if investimento else 0
        result = dict(bruto=bruto, liquido=liquido, lucro_saca=(liquido/qtd if qtd else 0), margem=margem, vale=liquido>0)
    return render_template('simulador.html', result=result)


@app.route('/recibo/<tipo>/<int:item_id>')
def recibo(tipo, item_id):
    if tipo == 'compra':
        item = fetchone("""SELECT c.*, p.nome pessoa_nome, p.documento, p.telefone FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE c.id=?""", (item_id,))
    else:
        item = fetchone("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, p.nome pessoa_nome, p.documento, p.telefone FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id WHERE v.id=?""", (item_id,))
    return render_template('recibo.html', tipo=tipo, item=item)


@app.route('/exportar/financeiro.csv')
def exportar_financeiro():
    rows = financeiro_rows()
    dados = [[br_date(r['data']),r['tipo'],r['categoria'],r['descricao'],br_num(r['valor']),r['status'],r['origem']] for r in rows]
    return csv_response('financeiro_cafe.csv', ['Data','Tipo','Categoria','Descrição','Valor','Status','Origem'], dados)


@app.route('/provas/<int:prova_id>/comprovante')
def comprovante_prova(prova_id):
    prova = fetchone("""SELECT pr.*, c.lote, p.nome pessoa_nome, p.documento, p.telefone, p.whatsapp
                      FROM provas pr
                      LEFT JOIN compras c ON c.id=pr.compra_id
                      LEFT JOIN pessoas p ON p.id=COALESCE(pr.pessoa_id, c.pessoa_id)
                      WHERE pr.id=?""", (prova_id,))
    if not prova:
        flash('Prova não encontrada.'); return redirect(url_for('provas'))
    nome = prova['pessoa_nome'] or prova['nome_avulso'] or prova['nome_cliente'] or 'Cliente avulso'
    texto = f"""Café Boa Vista\nResultado da prova de café\n\nCliente: {nome}\nData: {prova['data']}\nQuantidade: {br_num(prova['quantidade_sacas'] or prova['quantidade'])} sacas\nBebida: {prova['bebida'] or '-'}\nCata: {prova['cata'] or '-'}\nUmidade: {prova['umidade'] or '-'}\nResultado: {prova['aprovado'] or 'Em análise'}\nObservação: {prova['observacao'] or '-'}"""
    return render_template('comprovante_prova.html', prova=prova, nome=nome, texto_whatsapp=texto)


@app.route('/clientes/<int:pessoa_id>/extrato')
def extrato_cliente(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    atualizar_adiantamentos_abertos(pessoa_id)
    vendas_rows = fetchall("SELECT * FROM vendas WHERE pessoa_id=? ORDER BY data DESC, id DESC", (pessoa_id,))
    compras_rows = fetchall(f"""SELECT c.*, ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido
        FROM compras c WHERE c.pessoa_id=? ORDER BY data DESC, id DESC""", (pessoa_id,))
    provas_rows = fetchall("SELECT * FROM provas WHERE pessoa_id=? ORDER BY data DESC, id DESC", (pessoa_id,))
    adiantamentos_rows = [adiantamento_com_juros_atual(a) for a in fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? ORDER BY data DESC, id DESC", (pessoa_id,))]
    estoque_tipo = fetchall(f"""SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas, SUM(({lote_estoque_expr()}) * c.valor_saca) valor
        FROM compras c WHERE c.pessoa_id=? GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_vendas = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente')", (pessoa_id,))['v']
    adiantamentos_abertos = [a for a in adiantamentos_rows if adiantamento_em_aberto(a)]
    adiant_sem = sum(float(a.get('valor') or 0) for a in adiantamentos_abertos)
    adiant_juros = sum(float(a.get('valor_juros') or 0) for a in adiantamentos_abertos)
    adiant_total = sum(float(a.get('valor_total') or 0) for a in adiantamentos_abertos)
    texto = f"""Café Boa Vista\nExtrato do cliente\n\nCliente: {pessoa['nome']}\nSaldo vendas pendentes: {br_money(saldo_vendas)}\nValores pegos sem juros: {br_money(adiant_sem)}\nJuros: {br_money(adiant_juros)}\nTotal para acerto: {br_money(saldo_vendas - adiant_total)}"""
    return render_template('extrato_cliente.html', pessoa=pessoa, vendas=vendas_rows, compras=compras_rows, provas=provas_rows,
                           adiantamentos=adiantamentos_rows, estoque_tipo=estoque_tipo, saldo_vendas=saldo_vendas,
                           adiant_sem=adiant_sem, adiant_juros=adiant_juros, adiant_total=adiant_total, texto_whatsapp=texto)



@app.route('/clientes/<int:pessoa_id>/acerto')
def acerto_cliente(pessoa_id):
    dados = get_acerto_data(pessoa_id)
    if not dados:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    return render_template('acerto_cliente.html', **dados)

@app.route('/clientes/<int:pessoa_id>/acertar-tudo', methods=['POST'])
def acertar_tudo_cliente(pessoa_id):
    atualizar_adiantamentos_abertos(pessoa_id)
    con = db()
    try:
        con.execute('BEGIN IMMEDIATE')
        pessoa = con.execute('SELECT * FROM pessoas WHERE id=?', (pessoa_id,)).fetchone()
        if not pessoa:
            flash('Cliente não encontrado.', 'error'); return redirect(url_for('clientes'))
        vendas = con.execute("SELECT * FROM vendas WHERE pessoa_id=? AND status_recebimento IN ('Pendente','A pagar ao cliente')", (pessoa_id,)).fetchall()
        adiantamentos = [adiantamento_com_juros_atual(a) for a in con.execute('SELECT * FROM adiantamentos WHERE pessoa_id=?', (pessoa_id,)).fetchall() if adiantamento_em_aberto(a)]
        if not vendas and not adiantamentos:
            flash('Este cliente não tem valores em aberto. Nenhum acerto foi lançado.', 'error')
            return redirect(url_for('painel_cliente',pessoa_id=pessoa_id))
        total = round(sum(v['valor_total'] or 0 for v in vendas)-sum(a['valor_total'] or 0 for a in adiantamentos),2)
        for v in vendas:
            con.execute("UPDATE vendas SET status_recebimento='Pago ao cliente' WHERE id=?",(v['id'],))
            # O pagamento bruto foi compensado; apenas o valor líquido movimenta o caixa.
            con.execute("UPDATE financeiro SET status='Compensado' WHERE origem=? AND status='Pendente'",(f"venda:{v['id']}",))
        for a in adiantamentos:
            con.execute("UPDATE adiantamentos SET status='Pago',meses_atraso=?,valor_juros=?,valor_total=? WHERE id=?",(a['meses_atraso'],a['valor_juros'],a['valor_total'],a['id']))
        if abs(total)>0.004:
            con.execute('INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)',
                (today(),'Saída' if total>0 else 'Entrada',f'Acerto líquido - {pessoa["nome"]}','Acerto de cliente',abs(total),'Pago' if total>0 else 'Recebido',f'acerto:{pessoa_id}:{datetime.now().timestamp()}'))
        con.commit()
    finally:
        con.close()
    log_acao('Acerto geral do cliente', 'pessoa', pessoa_id, f'Saldo líquido: {br_money(total)}')
    flash('Acerto confirmado. Vendas e adiantamentos baixados; somente o valor líquido foi lançado no caixa.', 'success')
    return redirect(url_for('painel_cliente',pessoa_id=pessoa_id))


@app.route('/busca')
def busca_geral():
    q = request.args.get('q','').strip()
    like = f"%{q}%"
    pessoas_rows = provas_rows = compras_rows = vendas_rows = []
    if q:
        pessoas_rows = fetchall("SELECT * FROM pessoas WHERE normalizar(nome) LIKE normalizar(?) OR normalizar(documento) LIKE normalizar(?) OR normalizar(telefone) LIKE normalizar(?) OR normalizar(whatsapp) LIKE normalizar(?) OR normalizar(cidade) LIKE normalizar(?) OR normalizar(fazenda) LIKE normalizar(?) ORDER BY nome LIMIT 30", (like,like,like,like,like,like))
        provas_rows = fetchall("""SELECT pr.*, p.nome pessoa_nome FROM provas pr LEFT JOIN pessoas p ON p.id=pr.pessoa_id
                                  WHERE normalizar(p.nome) LIKE normalizar(?) OR normalizar(pr.nome_avulso) LIKE normalizar(?) OR normalizar(pr.nome_cliente) LIKE normalizar(?) OR normalizar(pr.bebida) LIKE normalizar(?) OR normalizar(pr.cata) LIKE normalizar(?) OR normalizar(pr.observacao) LIKE normalizar(?)
                                  ORDER BY pr.id DESC LIMIT 30""", (like,like,like,like,like,like))
        compras_rows = fetchall("""SELECT c.*, p.nome pessoa_nome FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id
                                   WHERE normalizar(p.nome) LIKE normalizar(?) OR normalizar(c.lote) LIKE normalizar(?) OR normalizar(c.tipo_cafe) LIKE normalizar(?) OR normalizar(c.observacao) LIKE normalizar(?) ORDER BY c.id DESC LIMIT 30""", (like,like,like,like))
        vendas_rows = fetchall("""SELECT v.*, EXISTS(SELECT 1 FROM financeiro f WHERE f.origem='venda:' || v.id AND f.status='Compensado') acerto_confirmado, p.nome pessoa_nome FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id
                                  WHERE normalizar(p.nome) LIKE normalizar(?) OR normalizar(v.lote) LIKE normalizar(?) OR normalizar(v.tipo_cafe) LIKE normalizar(?) OR normalizar(v.observacao) LIKE normalizar(?) ORDER BY v.id DESC LIMIT 30""", (like,like,like,like))
    return render_template('busca.html', q=q, pessoas=pessoas_rows, provas=provas_rows, compras=compras_rows, vendas=vendas_rows)


@app.route('/backup', methods=['GET','POST'])
def backup():
    if request.method == 'POST':
        arquivo = request.files.get('arquivo')
        if not arquivo or not arquivo.filename:
            flash('Selecione um backup do sistema.', 'error'); return redirect(url_for('backup'))
        fd, caminho = tempfile.mkstemp(suffix='.sqlite3', dir=DB_DIR)
        os.close(fd)
        candidato = Path(caminho)
        anterior = DB_DIR / f'backup_antes_restaurar_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
        try:
            arquivo.save(candidato)
            with sqlite3.connect(candidato) as teste:
                if teste.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Arquivo inválido.')
                tabelas = {r[0] for r in teste.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'pessoas','compras','provas','vendas','financeiro'}.issubset(tabelas):
                    raise ValueError('O arquivo não é um backup deste sistema.')
                essenciais = {'pessoas': {'id','tipo','nome','criado_em'}, 'compras': {'id','pessoa_id','data','lote','tipo_cafe','quantidade_sacas','peso_kg','valor_saca','valor_total','status_pagamento','observacao'}, 'vendas': {'id','pessoa_id','data','lote','tipo_cafe','quantidade_sacas','valor_saca','valor_total','status_recebimento','observacao'}, 'provas': {'id','data','compra_id','bebida','peneira','umidade','defeitos','nota','classificacao','observacao'}, 'financeiro': {'id','data','tipo','descricao','valor','status','origem'}}
                for tabela, campos in essenciais.items():
                    if not campos.issubset({r[1] for r in teste.execute(f'PRAGMA table_info({tabela})')}):
                        raise ValueError('Este backup tem uma estrutura incompatível.')
            origem = db()
            destino = sqlite3.connect(anterior)
            try:
                origem.backup(destino)
            finally:
                origem.close(); destino.close()
            origem = sqlite3.connect(candidato)
            destino = db()
            try:
                origem.backup(destino)
            finally:
                origem.close(); destino.close()
            try:
                init_db()
            except Exception:
                origem = sqlite3.connect(anterior); destino = db()
                try:
                    origem.backup(destino)
                finally:
                    origem.close(); destino.close()
                raise
            log_acao('Backup restaurado','sistema',None,f'Cópia anterior: {anterior.name}')
            flash('Backup validado e restaurado. Uma cópia dos dados anteriores foi guardada.', 'success')
        except (sqlite3.Error, ValueError, OSError):
            flash('Não foi possível restaurar: envie um backup válido e compatível. Os dados atuais foram preservados.', 'error')
        finally:
            candidato.unlink(missing_ok=True)
        return redirect(url_for('backup'))
    return render_template('backup.html',historico=fetchall('SELECT * FROM historico ORDER BY id DESC LIMIT 80'),last_backup=fetchone("SELECT * FROM historico WHERE acao LIKE 'Backup%' ORDER BY id DESC LIMIT 1"))


@app.route('/backup/baixar')
def baixar_backup():
    nome = f'backup_controle_cafe_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite3'
    log_acao('Backup baixado','sistema',None,nome)
    fd, caminho = tempfile.mkstemp(suffix='.sqlite3')
    os.close(fd)
    origem, destino = db(), sqlite3.connect(caminho)
    try:
        origem.backup(destino)
    finally:
        origem.close(); destino.close()
    try:
        conteudo = Path(caminho).read_bytes()
    finally:
        Path(caminho).unlink(missing_ok=True)
    return send_file(io.BytesIO(conteudo), as_attachment=True,download_name=nome,mimetype='application/octet-stream')


def csv_response(filename, headers, rows):
    out = io.StringIO(); w = csv.writer(out, delimiter=';')
    w.writerow(headers)
    for r in rows:
        w.writerow([r[h] if h in r.keys() else '' for h in headers] if hasattr(r, 'keys') else r)
    return Response('\ufeff' + out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})


@app.route('/exportar/clientes.csv')
def exportar_clientes():
    rows = fetchall("SELECT id,tipo,nome,documento,telefone,whatsapp,cidade,endereco,fazenda,observacao,criado_em FROM pessoas ORDER BY nome")
    return csv_response('clientes_cafe.csv', ['id','tipo','nome','documento','telefone','whatsapp','cidade','endereco','fazenda','observacao','criado_em'], rows)


@app.route('/exportar/provas.csv')
def exportar_provas():
    rows = fetchall("SELECT id,data,nome_avulso,nome_cliente,cata,quantidade_sacas,bebida,umidade,aprovado,observacao FROM provas ORDER BY id DESC")
    return csv_response('provas_cafe.csv', ['id','data','nome_avulso','nome_cliente','cata','quantidade_sacas','bebida','umidade','aprovado','observacao'], rows)


@app.route('/exportar/compras.csv')
def exportar_compras():
    rows = fetchall("SELECT id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,divisor_saca,ajuste_sacas,valor_saca,valor_total,status_pagamento,status_lote,observacao FROM compras ORDER BY id DESC")
    return csv_response('compras_cafe.csv', ['id','data','lote','tipo_cafe','quantidade_sacas','peso_kg','divisor_saca','ajuste_sacas','valor_saca','valor_total','status_pagamento','status_lote','observacao'], rows)


@app.route('/exportar/vendas.csv')
def exportar_vendas():
    rows = fetchall("SELECT id,data,lote,tipo_cafe,quantidade_sacas,valor_saca,subtotal_cafe,valor_juros,valor_total,status_recebimento,observacao FROM vendas ORDER BY id DESC")
    return csv_response('vendas_cafe.csv', ['id','data','lote','tipo_cafe','quantidade_sacas','valor_saca','subtotal_cafe','valor_juros','valor_total','status_recebimento','observacao'], rows)


@app.route('/relatorios/cafes-analise')
def cafes_analise():
    rows = fetchall("""SELECT pr.*, p.nome pessoa_nome FROM provas pr LEFT JOIN pessoas p ON p.id=pr.pessoa_id
                       WHERE COALESCE(pr.aprovado,'Em análise')='Em análise' ORDER BY pr.data DESC, pr.id DESC""")
    return render_template('cafes_analise.html', provas=rows)


@app.route('/historico')
def historico():
    rows = fetchall("SELECT * FROM historico ORDER BY id DESC LIMIT 200")
    return render_template('historico.html', historico=rows)

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',8080)), debug=False)
