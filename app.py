from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file
import sqlite3, csv, io, shutil, urllib.parse
from pathlib import Path
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "controle-cafe-pro"
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
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


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
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
    """)
    for table, cols in {
        'pessoas': [('documento','TEXT'),('whatsapp','TEXT'),('endereco','TEXT'),('fazenda','TEXT')],
        'compras': [('forma_pagamento','TEXT'),('frete','REAL DEFAULT 0'),('outras_despesas','REAL DEFAULT 0'),('origem_cafe','TEXT'),('status_lote',"TEXT DEFAULT 'Em estoque'"),('divisor_saca','REAL DEFAULT 60'),('ajuste_sacas','REAL DEFAULT 0')],
        'provas': [('pessoa_id','INTEGER'),('cata','TEXT'),('nome_cliente','TEXT'),('nome_avulso','TEXT'),('quantidade','REAL DEFAULT 0'),('quantidade_sacas','REAL DEFAULT 0'),('aroma','TEXT'),('corpo','TEXT'),('acidez','TEXT'),('docura','TEXT'),('aprovado',"TEXT DEFAULT 'Em análise'")],
        'vendas': [('compra_id','INTEGER'),('custo_saca','REAL DEFAULT 0'),('lucro_total','REAL DEFAULT 0'),('forma_pagamento','TEXT'),('subtotal_cafe','REAL DEFAULT 0'),('juros_percentual','REAL DEFAULT 0'),('meses_atraso','REAL DEFAULT 0'),('valor_juros','REAL DEFAULT 0')],
        'financeiro': [('categoria','TEXT')],
        'adiantamentos': [('taxa_juros','REAL DEFAULT 0'),('meses_atraso','REAL DEFAULT 0'),('valor_juros','REAL DEFAULT 0'),('valor_total','REAL DEFAULT 0'),('observacao','TEXT'),('status',"TEXT DEFAULT 'Aberto'"),('criado_em','TEXT')],
        'historico': [('entidade','TEXT'),('entidade_id','INTEGER'),('detalhe','TEXT')],
        'usuarios': [('nome','TEXT'),('tipo',"TEXT DEFAULT 'Administrador'")]
    }.items():
        for column, definition in cols:
            add_column(cur, table, column, definition)
    cur.execute("UPDATE provas SET aprovado='Em análise' WHERE aprovado IS NULL OR aprovado='' OR aprovado='Aprovado'")
    cur.execute("UPDATE vendas SET subtotal_cafe=valor_total WHERE subtotal_cafe IS NULL OR subtotal_cafe=0")
    con.commit(); con.close()


def fetchall(query, params=()):
    con = db(); rows = con.execute(query, params).fetchall(); con.close(); return rows


def fetchone(query, params=()):
    con = db(); row = con.execute(query, params).fetchone(); con.close(); return row


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


def get_acerto_data(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        return None
    atualizar_adiantamentos_abertos(pessoa_id)
    vendas_rows = fetchall("SELECT * FROM vendas WHERE pessoa_id=? AND status_recebimento='Pendente' ORDER BY data DESC, id DESC", (pessoa_id,))
    adiantamentos_rows = [adiantamento_com_juros_atual(a) for a in fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? AND UPPER(TRIM(COALESCE(status,'Aberto'))) NOT IN ('PAGO','PAGA','QUITADO','QUITADA') ORDER BY data DESC, id DESC", (pessoa_id,))]
    estoque_tipo = fetchall(f"""SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas, SUM(({lote_estoque_expr()}) * c.valor_saca) valor
        FROM compras c WHERE c.pessoa_id=? GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_vendas = sum(float(v['valor_total'] or 0) for v in vendas_rows)
    adiant_sem = sum(float(a['valor'] or 0) for a in adiantamentos_rows)
    adiant_juros = sum(float(a['valor_juros'] or 0) for a in adiantamentos_rows)
    adiant_total = sum(float(a['valor_total'] or 0) for a in adiantamentos_rows)
    total = saldo_vendas + adiant_total
    texto = f"""Café Boa Vista\nAcerto do cliente\n\nCliente: {pessoa['nome']}\nVendas pendentes: {br_money(saldo_vendas)}\nValores que pegou: {br_money(adiant_sem)}\nJuros dos valores: {br_money(adiant_juros)}\nTotal para acerto: {br_money(total)}"""
    return dict(pessoa=pessoa, vendas=vendas_rows, adiantamentos=adiantamentos_rows, estoque_tipo=estoque_tipo,
                saldo_vendas=saldo_vendas, adiant_sem=adiant_sem, adiant_juros=adiant_juros,
                adiant_total=adiant_total, total=total, texto_whatsapp=texto, hoje=today())


def fnum(name):
    val = request.form.get(name)
    if isinstance(val, str):
        raw = val.strip()
        if raw.count(',') == 1 and raw.count('.') >= 1:
            raw = raw.replace('.', '').replace(',', '.')
        else:
            raw = raw.replace(',', '.')
    else:
        raw = val
    try: return float(raw or 0)
    except Exception: return 0.0


def today(): return date.today().isoformat()


def meses_juros_automatico(data_inicio, data_base=None):
    """Calcula meses completos entre a data que pegou e hoje.
    Ex.: 02/03 até 02/04 = 1 mês. Antes de virar o dia, não conta o novo mês.
    """
    try:
        inicio = datetime.strptime((data_inicio or today())[:10], '%Y-%m-%d').date()
    except Exception:
        inicio = date.today()
    base = data_base or date.today()
    meses = (base.year - inicio.year) * 12 + (base.month - inicio.month)
    if base.day < inicio.day:
        meses -= 1
    return max(0, meses)


def calcular_juros_simples(valor, taxa, meses):
    valor = float(valor or 0)
    taxa = float(taxa or 0)
    meses = float(meses or 0)
    juros = valor * (taxa / 100) * meses
    return juros, valor + juros


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
    if not compra_id: return
    row = fetchone(f"SELECT c.id, c.quantidade_sacas, ({lote_estoque_expr()}) estoque FROM compras c WHERE c.id=?", (compra_id,))
    if not row: return
    estoque = float(row['estoque'] or 0)
    status = 'Vendido' if estoque <= 0.0001 else ('Vendido parcial' if estoque < float(row['quantidade_sacas'] or 0) else 'Em estoque')
    con = db(); con.execute("UPDATE compras SET status_lote=? WHERE id=?", (status, compra_id)); con.commit(); con.close()


def update_all_status():
    ids = [r['id'] for r in fetchall("SELECT id FROM compras")]
    for i in ids: update_compra_status(i)


# Login removido temporariamente: o sistema entra direto enquanto finalizamos as regras de uso.
# A tabela usuarios pode continuar no banco sem atrapalhar, para recolocar login depois sem perder histórico.

def usuario_logado():
    return None

app.jinja_env.globals['usuario_logado'] = usuario_logado

@app.route('/')
def index():
    update_all_status()
    atualizar_adiantamentos_abertos()
    total_compras = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM compras")['v']
    total_vendas = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas")['v']
    sacas_compradas = fetchone("SELECT COALESCE(SUM(quantidade_sacas),0) v FROM compras")['v']
    sacas_vendidas = fetchone("SELECT COALESCE(SUM(quantidade_sacas),0) v FROM vendas")['v']
    entrada = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Entrada'")['v']
    saida = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Saída'")['v']
    receber = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Entrada' AND status='Pendente'")['v']
    pagar = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Saída' AND status='Pendente'")['v']
    lucro = fetchone("SELECT COALESCE(SUM(lucro_total),0) v FROM vendas")['v']
    valor_estoque = fetchone(f"SELECT COALESCE(SUM(({lote_estoque_expr()}) * c.valor_saca),0) v FROM compras c")['v']
    ultimas_compras = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC LIMIT 6""")
    ultimas_vendas = fetchall("""SELECT vendas.*, pessoas.nome pessoa_nome FROM vendas LEFT JOIN pessoas ON pessoas.id = vendas.pessoa_id ORDER BY vendas.id DESC LIMIT 6""")
    return render_template('index.html', total_compras=total_compras, total_vendas=total_vendas, estoque=sacas_compradas-sacas_vendidas,
                           saldo=entrada-saida, receber=receber, pagar=pagar, lucro=lucro, valor_estoque=valor_estoque,
                           ultimas_compras=ultimas_compras, ultimas_vendas=ultimas_vendas)


@app.route('/pessoas', methods=['GET','POST'])
def pessoas():
    if request.method == 'POST':
        con = db()
        con.execute("""INSERT INTO pessoas (tipo,nome,documento,telefone,whatsapp,cidade,endereco,fazenda,observacao,criado_em)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (request.form['tipo'], request.form['nome'], request.form.get('documento'), request.form.get('telefone'), request.form.get('whatsapp'), request.form.get('cidade'), request.form.get('endereco'), request.form.get('fazenda'), request.form.get('observacao'), datetime.now().isoformat()))
        con.commit(); con.close(); log_acao('Cadastro de pessoa criado', 'pessoa', None, request.form.get('nome')); flash('Cadastro salvo com sucesso.')
        return redirect(url_for('pessoas'))
    q = request.args.get('q','').strip()
    sql = "SELECT * FROM pessoas"
    params = ()
    if q:
        sql += " WHERE nome LIKE ? OR telefone LIKE ? OR whatsapp LIKE ? OR cidade LIKE ? OR documento LIKE ?"
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
                    (request.form['tipo'], request.form['nome'], request.form.get('documento'), request.form.get('telefone'), request.form.get('whatsapp'), request.form.get('cidade'), request.form.get('endereco'), request.form.get('fazenda'), request.form.get('observacao'), pessoa_id))
        con.commit(); con.close(); log_acao('Cadastro de pessoa editado', 'pessoa', pessoa_id, pessoa['nome']); flash('Cadastro atualizado.')
        return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))
    return render_template('editar_pessoa.html', pessoa=pessoa)


@app.route('/pessoas/<int:pessoa_id>/excluir', methods=['POST'])
def excluir_pessoa(pessoa_id):
    con = db()
    con.execute("UPDATE compras SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("UPDATE vendas SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("UPDATE provas SET pessoa_id=NULL WHERE pessoa_id=?", (pessoa_id,))
    con.execute("DELETE FROM pessoas WHERE id=?", (pessoa_id,))
    con.commit(); con.close(); log_acao('Cliente excluído', 'pessoa', pessoa_id, 'Históricos mantidos sem vínculo'); flash('Cliente removido. Históricos foram mantidos sem vínculo.')
    return redirect(url_for('pessoas'))



@app.route('/clientes')
def clientes():
    q = request.args.get('q','').strip()
    sql = "SELECT * FROM pessoas WHERE 1=1"
    params = []
    if q:
        sql += " AND (nome LIKE ? OR documento LIKE ? OR telefone LIKE ? OR whatsapp LIKE ? OR cidade LIKE ? OR fazenda LIKE ?)"
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
    taxa = float(request.args.get('taxa_juros') or 0)
    meses = float(request.args.get('meses_atraso') or 0)
    vendas_rows = fetchall("""SELECT v.*, c.lote lote_compra FROM vendas v LEFT JOIN compras c ON c.id=v.compra_id WHERE v.pessoa_id=? ORDER BY v.id DESC""", (pessoa_id,))
    compras_rows = fetchall(f"""SELECT c.*, ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido
        FROM compras c WHERE c.pessoa_id=? ORDER BY c.id DESC""", (pessoa_id,))
    provas_rows = fetchall("""SELECT pr.*, c.lote FROM provas pr LEFT JOIN compras c ON c.id=pr.compra_id WHERE pr.pessoa_id=? ORDER BY pr.id DESC""", (pessoa_id,))
    estoque_tipo = fetchall(f"""SELECT COALESCE(c.tipo_cafe,'Sem tipo') tipo, SUM({lote_estoque_expr()}) sacas, SUM(({lote_estoque_expr()}) * c.valor_saca) valor
        FROM compras c WHERE c.pessoa_id=? GROUP BY COALESCE(c.tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_tipo = fetchall("""SELECT COALESCE(tipo_cafe,'Sem tipo') tipo, SUM(valor_total) valor, SUM(quantidade_sacas) sacas
        FROM vendas WHERE pessoa_id=? AND status_recebimento='Pendente' GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY tipo""", (pessoa_id,))
    saldo_pendente = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento='Pendente'", (pessoa_id,))['v']
    adiantamentos = [adiantamento_com_juros_atual(a) for a in fetchall("SELECT * FROM adiantamentos WHERE pessoa_id=? ORDER BY data DESC, id DESC", (pessoa_id,))]
    adiantamentos_abertos = [a for a in adiantamentos if adiantamento_em_aberto(a)]
    total_adiantamentos = sum(float(a.get('valor') or 0) for a in adiantamentos_abertos)
    juros_adiantamentos = sum(float(a.get('valor_juros') or 0) for a in adiantamentos_abertos)
    total_adiantamentos_juros = sum(float(a.get('valor_total') or 0) for a in adiantamentos_abertos)
    juros = saldo_pendente * (taxa/100) * meses
    return render_template('cliente_painel.html', pessoa=pessoa, vendas=vendas_rows, compras=compras_rows, provas=provas_rows,
                           estoque_tipo=estoque_tipo, saldo_tipo=saldo_tipo, saldo_pendente=saldo_pendente,
                           taxa=taxa, meses=meses, juros=juros, total_com_juros=saldo_pendente+juros, tipos_cafe=TIPOS_CAFE,
                           adiantamentos=adiantamentos, total_adiantamentos=total_adiantamentos,
                           juros_adiantamentos=juros_adiantamentos, total_adiantamentos_juros=total_adiantamentos_juros, hoje=today())


@app.route('/clientes/<int:pessoa_id>/aplicar-juros', methods=['POST'])
def aplicar_juros_cliente(pessoa_id):
    pessoa = fetchone("SELECT * FROM pessoas WHERE id=?", (pessoa_id,))
    if not pessoa:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    taxa = fnum('taxa_juros')
    meses = fnum('meses_atraso')
    saldo = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento='Pendente'", (pessoa_id,))['v']
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


@app.route('/compras', methods=['GET','POST'])
def compras():
    pessoas_rows = get_pessoas_choices("")
    if request.method == 'POST':
        peso, divisor, ajuste, informada = fnum('peso_kg'), fnum('divisor_saca') or 60, fnum('ajuste_sacas'), fnum('quantidade_sacas')
        qtd = calc_sacas(peso, divisor, ajuste, informada)
        valor_saca = fnum('valor_saca')
        frete, outras = fnum('frete'), fnum('outras_despesas')
        total = qtd * valor_saca + frete + outras
        con = db(); cur = con.cursor()
        cur.execute("""INSERT INTO compras (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,divisor_saca,ajuste_sacas,valor_saca,valor_total,status_pagamento,forma_pagamento,frete,outras_despesas,origem_cafe,status_lote,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, request.form['data'], request.form.get('lote'), request.form.get('tipo_cafe'), qtd, peso, divisor, ajuste, valor_saca, total, request.form.get('status_pagamento'), request.form.get('forma_pagamento'), frete, outras, request.form.get('origem_cafe'), request.form.get('status_lote') or 'Em estoque', request.form.get('observacao')))
        compra_id = cur.lastrowid
        lote = request.form.get('lote') or f"Compra {compra_id}"
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (request.form['data'], 'Saída', f"Compra de café - {lote}", 'Compra de café', total, request.form.get('status_pagamento'), f"compra:{compra_id}"))
        con.commit(); con.close(); log_acao('Compra lançada', 'compra', compra_id, f"{lote} - {br_money(total)}"); flash('Compra lançada. Sacas calculadas, lote, estoque e financeiro atualizados.')
        return redirect(url_for('compras'))
    rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    return render_template('compras.html', compras=rows, pessoas=pessoas_rows, hoje=today(), tipos_cafe=TIPOS_CAFE)


@app.route('/compras/<int:compra_id>/editar', methods=['GET','POST'])
def editar_compra(compra_id):
    compra = fetchone("SELECT * FROM compras WHERE id=?", (compra_id,))
    if not compra:
        flash('Compra não encontrada.'); return redirect(url_for('compras'))
    pessoas_rows = get_pessoas_choices("")
    if request.method == 'POST':
        peso, divisor, ajuste, informada = fnum('peso_kg'), fnum('divisor_saca') or 60, fnum('ajuste_sacas'), fnum('quantidade_sacas')
        qtd = calc_sacas(peso, divisor, ajuste, informada)
        valor_saca = fnum('valor_saca'); frete, outras = fnum('frete'), fnum('outras_despesas')
        total = qtd * valor_saca + frete + outras
        con = db(); con.execute("""UPDATE compras SET pessoa_id=?, data=?, lote=?, tipo_cafe=?, quantidade_sacas=?, peso_kg=?, divisor_saca=?, ajuste_sacas=?, valor_saca=?, valor_total=?, status_pagamento=?, forma_pagamento=?, frete=?, outras_despesas=?, origem_cafe=?, status_lote=?, observacao=? WHERE id=?""",
            (request.form.get('pessoa_id') or None, request.form['data'], request.form.get('lote'), request.form.get('tipo_cafe'), qtd, peso, divisor, ajuste, valor_saca, total, request.form.get('status_pagamento'), request.form.get('forma_pagamento'), frete, outras, request.form.get('origem_cafe'), request.form.get('status_lote'), request.form.get('observacao'), compra_id))
        con.commit(); con.close()
        update_financeiro(f"compra:{compra_id}", request.form['data'], 'Saída', f"Compra de café - {request.form.get('lote') or compra_id}", 'Compra de café', total, request.form.get('status_pagamento'))
        update_compra_status(compra_id)
        log_acao('Compra editada', 'compra', compra_id, f"Total: {br_money(total)}")
        flash('Compra atualizada.')
        return redirect(url_for('compras'))
    return render_template('editar_compra.html', compra=compra, pessoas=pessoas_rows, tipos_cafe=TIPOS_CAFE)


@app.route('/compras/<int:compra_id>/excluir', methods=['POST'])
def excluir_compra(compra_id):
    con = db()
    con.execute("DELETE FROM financeiro WHERE origem=?", (f"compra:{compra_id}",))
    vendas_ids = [r['id'] for r in con.execute("SELECT id FROM vendas WHERE compra_id=?", (compra_id,)).fetchall()]
    for vid in vendas_ids:
        con.execute("DELETE FROM financeiro WHERE origem=?", (f"venda:{vid}",))
    con.execute("DELETE FROM vendas WHERE compra_id=?", (compra_id,))
    con.execute("DELETE FROM provas WHERE compra_id=?", (compra_id,))
    con.execute("DELETE FROM compras WHERE id=?", (compra_id,))
    con.commit(); con.close(); log_acao('Compra excluída', 'compra', compra_id, 'Vendas/provas vinculadas também excluídas'); flash('Compra excluída junto com vendas/provas vinculadas.')
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
                    (pessoa_id, compra_id, request.form['data'], cata, request.form.get('nome_cliente'), nome_avulso, quantidade, quantidade, bebida, request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('aroma'), request.form.get('corpo'), request.form.get('acidez'), request.form.get('docura'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('aprovado') or 'Em análise', observacao))
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
                    (pessoa_id, compra_id, request.form['data'], cata, request.form.get('nome_cliente'), request.form.get('nome_avulso'), quantidade, quantidade, request.form.get('bebida'), request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('aroma'), request.form.get('corpo'), request.form.get('acidez'), request.form.get('docura'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('aprovado') or 'Em análise', request.form.get('observacao'), prova_id))
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
    prova = fetchone("SELECT * FROM provas WHERE id=?", (prova_id,))
    if not prova:
        flash('Prova não encontrada.'); return redirect(url_for('provas'))
    pessoa_id = prova['pessoa_id']
    valor_saca = fnum('valor_saca')
    qtd = float(prova['quantidade_sacas'] or prova['quantidade'] or 0)
    if not pessoa_id:
        nome = prova['nome_avulso'] or prova['nome_cliente'] or 'Cliente avulso'
        con = db(); cur = con.cursor()
        cur.execute("INSERT INTO pessoas (tipo,nome,criado_em) VALUES (?,?,?)", ('Cliente e Fornecedor', nome, datetime.now().isoformat()))
        pessoa_id = cur.lastrowid
        cur.execute("UPDATE provas SET pessoa_id=? WHERE id=?", (pessoa_id, prova_id))
        con.commit(); con.close()
    if qtd <= 0 or valor_saca <= 0:
        flash('Informe quantidade na prova e valor por saca para transformar em compra.')
        return redirect(url_for('provas'))
    lote = request.form.get('lote') or f"Prova {prova_id}"
    tipo = prova['bebida'] or request.form.get('tipo_cafe')
    total = qtd * valor_saca
    con = db(); cur = con.cursor()
    cur.execute("""INSERT INTO compras (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,divisor_saca,ajuste_sacas,valor_saca,valor_total,status_pagamento,forma_pagamento,status_lote,observacao)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pessoa_id, today(), lote, tipo, qtd, 0, 60, 0, valor_saca, total, request.form.get('status_pagamento') or 'Pendente', request.form.get('forma_pagamento'), 'Em estoque', f'Compra gerada pela prova #{prova_id}'))
    compra_id = cur.lastrowid
    cur.execute("UPDATE provas SET compra_id=?, aprovado='Aprovado' WHERE id=?", (compra_id, prova_id))
    cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                (today(), 'Saída', f'Compra de café - {lote}', 'Compra de café', total, request.form.get('status_pagamento') or 'Pendente', f'compra:{compra_id}'))
    con.commit(); con.close()
    log_acao('Prova transformada em compra', 'prova', prova_id, f"Compra #{compra_id}")
    flash('Prova transformada em compra e enviada para o estoque do cliente.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))


@app.route('/vendas', methods=['GET','POST'])
def vendas():
    pessoas_rows = get_pessoas_choices("")
    lotes = fetchall(f"""SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE ({lote_estoque_expr()}) > 0 ORDER BY c.id DESC""")
    if request.method == 'POST':
        qtd, valor_saca = fnum('quantidade_sacas'), fnum('valor_saca')
        compra_id = request.form.get('compra_id') or None
        compra = fetchone("SELECT * FROM compras WHERE id=?", (compra_id,)) if compra_id else None
        custo_saca = float(compra['valor_saca']) if compra else fnum('custo_saca')
        subtotal = qtd * valor_saca
        taxa, meses = fnum('juros_percentual'), fnum('meses_atraso')
        juros = subtotal * (taxa/100) * meses
        total = subtotal + juros
        lucro = (valor_saca - custo_saca) * qtd
        lote = request.form.get('lote') or (compra['lote'] if compra else '')
        tipo_cafe = request.form.get('tipo_cafe') or (compra['tipo_cafe'] if compra else '')
        if compra_id:
            estoque_row = fetchone(f"SELECT ({lote_estoque_expr()}) estoque FROM compras c WHERE c.id=?", (compra_id,))
            estoque_atual = float(estoque_row['estoque'] or 0) if estoque_row else 0
            if qtd > estoque_atual + 0.0001:
                flash(f'Não dá para vender {br_num(qtd)} sacas. Esse lote tem apenas {br_num(estoque_atual)} sacas disponíveis.')
                return redirect(url_for('vendas'))
        con = db(); cur = con.cursor()
        cur.execute("""INSERT INTO vendas (pessoa_id,compra_id,data,lote,tipo_cafe,quantidade_sacas,valor_saca,subtotal_cafe,juros_percentual,meses_atraso,valor_juros,valor_total,custo_saca,lucro_total,status_recebimento,forma_pagamento,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, compra_id, request.form['data'], lote, tipo_cafe, qtd, valor_saca, subtotal, taxa, meses, juros, total, custo_saca, lucro, request.form.get('status_recebimento'), request.form.get('forma_pagamento'), request.form.get('observacao')))
        venda_id = cur.lastrowid
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (request.form['data'], 'Entrada', f"Venda de café - {lote or venda_id}", 'Venda de café', total, request.form.get('status_recebimento'), f"venda:{venda_id}"))
        con.commit(); con.close(); update_compra_status(compra_id)
        log_acao('Venda lançada', 'venda', venda_id, f"{lote} - {br_money(total)}")
        flash('Venda lançada com lucro, juros e status de estoque atualizados.')
        return redirect(url_for('vendas'))
    rows = fetchall("""SELECT vendas.*, pessoas.nome pessoa_nome FROM vendas LEFT JOIN pessoas ON pessoas.id = vendas.pessoa_id ORDER BY vendas.id DESC""")
    return render_template('vendas.html', vendas=rows, pessoas=pessoas_rows, lotes=lotes, hoje=today(), tipos_cafe=TIPOS_CAFE)


@app.route('/vendas/<int:venda_id>/editar', methods=['GET','POST'])
def editar_venda(venda_id):
    venda = fetchone("SELECT * FROM vendas WHERE id=?", (venda_id,))
    if not venda:
        flash('Venda não encontrada.'); return redirect(url_for('vendas'))
    old_compra_id = venda['compra_id']
    pessoas_rows = get_pessoas_choices("")
    lotes = fetchall(f"""SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE ({lote_estoque_expr()}) > 0 OR c.id=? ORDER BY c.id DESC""", (old_compra_id or 0,))
    if request.method == 'POST':
        qtd, valor_saca = fnum('quantidade_sacas'), fnum('valor_saca')
        compra_id = request.form.get('compra_id') or None
        compra = fetchone("SELECT * FROM compras WHERE id=?", (compra_id,)) if compra_id else None
        custo_saca = float(compra['valor_saca']) if compra else fnum('custo_saca')
        subtotal = qtd * valor_saca
        taxa, meses = fnum('juros_percentual'), fnum('meses_atraso')
        juros = subtotal * (taxa/100) * meses
        total = subtotal + juros
        lucro = (valor_saca - custo_saca) * qtd
        lote = request.form.get('lote') or (compra['lote'] if compra else '')
        tipo_cafe = request.form.get('tipo_cafe') or (compra['tipo_cafe'] if compra else '')
        if compra_id:
            estoque_row = fetchone(f"SELECT ({lote_estoque_expr()}) estoque FROM compras c WHERE c.id=?", (compra_id,))
            estoque_atual = float(estoque_row['estoque'] or 0) if estoque_row else 0
            # se estiver editando a mesma venda/lote, soma a quantidade antiga para calcular o disponível real
            if str(compra_id) == str(old_compra_id or ''):
                estoque_atual += float(venda['quantidade_sacas'] or 0)
            if qtd > estoque_atual + 0.0001:
                flash(f'Não dá para salvar. Disponível real do lote: {br_num(estoque_atual)} sacas.')
                return redirect(url_for('editar_venda', venda_id=venda_id))
        con = db(); con.execute("""UPDATE vendas SET pessoa_id=?, compra_id=?, data=?, lote=?, tipo_cafe=?, quantidade_sacas=?, valor_saca=?, subtotal_cafe=?, juros_percentual=?, meses_atraso=?, valor_juros=?, valor_total=?, custo_saca=?, lucro_total=?, status_recebimento=?, forma_pagamento=?, observacao=? WHERE id=?""",
            (request.form.get('pessoa_id') or None, compra_id, request.form['data'], lote, tipo_cafe, qtd, valor_saca, subtotal, taxa, meses, juros, total, custo_saca, lucro, request.form.get('status_recebimento'), request.form.get('forma_pagamento'), request.form.get('observacao'), venda_id))
        con.commit(); con.close()
        update_financeiro(f"venda:{venda_id}", request.form['data'], 'Entrada', f"Venda de café - {lote or venda_id}", 'Venda de café', total, request.form.get('status_recebimento'))
        update_compra_status(old_compra_id); update_compra_status(compra_id)
        log_acao('Venda editada', 'venda', venda_id, f"Total: {br_money(total)}")
        flash('Venda atualizada. Preço, juros, lucro e estoque recalculados.')
        return redirect(url_for('vendas'))
    return render_template('editar_venda.html', venda=venda, pessoas=pessoas_rows, lotes=lotes, tipos_cafe=TIPOS_CAFE)


@app.route('/vendas/<int:venda_id>/excluir', methods=['POST'])
def excluir_venda(venda_id):
    venda = fetchone("SELECT compra_id FROM vendas WHERE id=?", (venda_id,))
    con = db(); con.execute("DELETE FROM financeiro WHERE origem=?", (f"venda:{venda_id}",)); con.execute("DELETE FROM vendas WHERE id=?", (venda_id,)); con.commit(); con.close()
    if venda: update_compra_status(venda['compra_id'])
    log_acao('Venda excluída', 'venda', venda_id, '')
    flash('Venda excluída e estoque recalculado.')
    return redirect(url_for('vendas'))


@app.route('/lotes')
def lotes():
    update_all_status()
    rows = fetchall(f"""SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote,
        COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0) vendido,
        COALESCE((SELECT SUM(v.lucro_total) FROM vendas v WHERE v.compra_id=c.id),0) lucro
        FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id ORDER BY c.id DESC""")
    return render_template('lotes.html', lotes=rows)


@app.route('/financeiro', methods=['GET','POST'])
def financeiro():
    if request.method == 'POST':
        con = db()
        con.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (request.form['data'], request.form['tipo'], request.form['descricao'], request.form.get('categoria'), fnum('valor'), request.form.get('status'), 'manual'))
        con.commit(); con.close(); flash('Lançamento financeiro salvo.')
        return redirect(url_for('financeiro'))
    itens = fetchall("SELECT * FROM financeiro ORDER BY data DESC, id DESC")
    entrada = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Entrada'")['v']
    saida = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Saída'")['v']
    receber = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Entrada' AND status='Pendente'")['v']
    pagar = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Saída' AND status='Pendente'")['v']
    return render_template('financeiro.html', itens=itens, entrada=entrada, saida=saida, saldo=entrada-saida, receber=receber, pagar=pagar, hoje=today())


@app.route('/relatorios')
def relatorios():
    compras_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total FROM compras GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY total DESC")
    vendas_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total, SUM(lucro_total) lucro FROM vendas GROUP BY COALESCE(tipo_cafe,'Sem tipo') ORDER BY total DESC")
    ranking_produtores = fetchall("""SELECT p.nome, SUM(c.quantidade_sacas) sacas, SUM(c.valor_total) total, AVG(CAST(NULLIF(pr.nota,'') AS REAL)) nota_media FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id LEFT JOIN provas pr ON pr.compra_id=c.id GROUP BY p.id ORDER BY sacas DESC LIMIT 10""")
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
        item = fetchone("""SELECT v.*, p.nome pessoa_nome, p.documento, p.telefone FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id WHERE v.id=?""", (item_id,))
    return render_template('recibo.html', tipo=tipo, item=item)


@app.route('/exportar/financeiro.csv')
def exportar_financeiro():
    rows = fetchall("SELECT data,tipo,categoria,descricao,valor,status,origem FROM financeiro ORDER BY data DESC")
    out = io.StringIO(); w = csv.writer(out, delimiter=';')
    w.writerow(['Data','Tipo','Categoria','Descrição','Valor','Status','Origem'])
    for r in rows: w.writerow([r['data'], r['tipo'], r['categoria'], r['descricao'], r['valor'], r['status'], r['origem']])
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=financeiro_cafe.csv'})


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
    saldo_vendas = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas WHERE pessoa_id=? AND status_recebimento='Pendente'", (pessoa_id,))['v']
    adiantamentos_abertos = [a for a in adiantamentos_rows if adiantamento_em_aberto(a)]
    adiant_sem = sum(float(a.get('valor') or 0) for a in adiantamentos_abertos)
    adiant_juros = sum(float(a.get('valor_juros') or 0) for a in adiantamentos_abertos)
    adiant_total = sum(float(a.get('valor_total') or 0) for a in adiantamentos_abertos)
    texto = f"""Café Boa Vista\nExtrato do cliente\n\nCliente: {pessoa['nome']}\nSaldo vendas pendentes: {br_money(saldo_vendas)}\nValores pegos sem juros: {br_money(adiant_sem)}\nJuros: {br_money(adiant_juros)}\nTotal para acerto: {br_money(saldo_vendas + adiant_total)}"""
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
    dados = get_acerto_data(pessoa_id)
    if not dados:
        flash('Cliente não encontrado.'); return redirect(url_for('clientes'))
    pessoa = dados['pessoa']; total = dados['total']
    vendas_ids = [v['id'] for v in dados['vendas']]
    adiant_ids = [a['id'] for a in dados['adiantamentos']]
    con = db()
    for vid in vendas_ids:
        con.execute("UPDATE vendas SET status_recebimento='Recebido' WHERE id=?", (vid,))
        con.execute("UPDATE financeiro SET status='Pago' WHERE origem=?", (f"venda:{vid}",))
    for aid in adiant_ids:
        con.execute("UPDATE adiantamentos SET status='Pago' WHERE id=?", (aid,))
    con.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                (today(), 'Entrada', f"Acerto geral - {pessoa['nome']}", 'Acerto de cliente', total, 'Pago', f"acerto:{pessoa_id}:{datetime.now().timestamp()}"))
    con.commit(); con.close()
    log_acao('Acerto geral do cliente', 'pessoa', pessoa_id, f'Total acertado: {br_money(total)}')
    flash('Acerto geral confirmado. Vendas pendentes e valores pegos foram marcados como pagos.')
    return redirect(url_for('painel_cliente', pessoa_id=pessoa_id))


@app.route('/busca')
def busca_geral():
    q = request.args.get('q','').strip()
    like = f"%{q}%"
    pessoas_rows = provas_rows = compras_rows = vendas_rows = []
    if q:
        pessoas_rows = fetchall("SELECT * FROM pessoas WHERE nome LIKE ? OR documento LIKE ? OR telefone LIKE ? OR whatsapp LIKE ? OR cidade LIKE ? OR fazenda LIKE ? ORDER BY nome LIMIT 30", (like,like,like,like,like,like))
        provas_rows = fetchall("""SELECT pr.*, p.nome pessoa_nome FROM provas pr LEFT JOIN pessoas p ON p.id=pr.pessoa_id
                                  WHERE p.nome LIKE ? OR pr.nome_avulso LIKE ? OR pr.nome_cliente LIKE ? OR pr.bebida LIKE ? OR pr.cata LIKE ? OR pr.observacao LIKE ?
                                  ORDER BY pr.id DESC LIMIT 30""", (like,like,like,like,like,like))
        compras_rows = fetchall("""SELECT c.*, p.nome pessoa_nome FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id
                                   WHERE p.nome LIKE ? OR c.lote LIKE ? OR c.tipo_cafe LIKE ? OR c.observacao LIKE ? ORDER BY c.id DESC LIMIT 30""", (like,like,like,like))
        vendas_rows = fetchall("""SELECT v.*, p.nome pessoa_nome FROM vendas v LEFT JOIN pessoas p ON p.id=v.pessoa_id
                                  WHERE p.nome LIKE ? OR v.lote LIKE ? OR v.tipo_cafe LIKE ? OR v.observacao LIKE ? ORDER BY v.id DESC LIMIT 30""", (like,like,like,like))
    return render_template('busca.html', q=q, pessoas=pessoas_rows, provas=provas_rows, compras=compras_rows, vendas=vendas_rows)


@app.route('/backup', methods=['GET','POST'])
def backup():
    if request.method == 'POST':
        arquivo = request.files.get('arquivo')
        if not arquivo or not arquivo.filename:
            flash('Selecione um arquivo de backup .sqlite3 para restaurar.')
            return redirect(url_for('backup'))
        backup_path = DB_DIR / f"backup_antes_restaurar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
        if DB_PATH.exists():
            shutil.copy(DB_PATH, backup_path)
        arquivo.save(DB_PATH)
        log_acao('Backup restaurado', 'sistema', None, f'Backup anterior salvo em {backup_path.name}')
        flash('Backup restaurado. Faça redeploy/reinicie o app se alguma tela não atualizar na hora.')
        return redirect(url_for('backup'))
    historico_rows = fetchall("SELECT * FROM historico ORDER BY id DESC LIMIT 80")
    last_backup = fetchone("SELECT * FROM historico WHERE acao LIKE 'Backup%' ORDER BY id DESC LIMIT 1")
    return render_template('backup.html', historico=historico_rows, last_backup=last_backup)


@app.route('/backup/baixar')
def baixar_backup():
    if not DB_PATH.exists():
        flash('Banco ainda não foi criado.')
        return redirect(url_for('backup'))
    nome = f"backup_controle_cafe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    log_acao('Backup baixado', 'sistema', None, nome)
    return send_file(DB_PATH, as_attachment=True, download_name=nome)


def csv_response(filename, headers, rows):
    out = io.StringIO(); w = csv.writer(out, delimiter=';')
    w.writerow(headers)
    for r in rows:
        w.writerow([r[h] if h in r.keys() else '' for h in headers])
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})


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
    app.run(host='0.0.0.0', port=8080, debug=True)
