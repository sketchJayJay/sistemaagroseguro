from flask import Flask, render_template, request, redirect, url_for, flash, Response
import sqlite3, csv, io
from pathlib import Path
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "controle-cafe-pro"
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "controle_cafe.sqlite3"


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
    cur.executescript('''
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
        compra_id INTEGER,
        data TEXT NOT NULL,
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
        aprovado TEXT DEFAULT 'Aprovado',
        observacao TEXT,
        FOREIGN KEY(compra_id) REFERENCES compras(id)
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
    ''')
    for table, cols in {
        'pessoas': [('documento','TEXT'),('whatsapp','TEXT'),('endereco','TEXT'),('fazenda','TEXT')],
        'compras': [('forma_pagamento','TEXT'),('frete','REAL DEFAULT 0'),('outras_despesas','REAL DEFAULT 0'),('origem_cafe','TEXT'),('status_lote',"TEXT DEFAULT 'Em estoque'")],
        'provas': [('aroma','TEXT'),('corpo','TEXT'),('acidez','TEXT'),('docura','TEXT'),('aprovado',"TEXT DEFAULT 'Aprovado'")],
        'vendas': [('compra_id','INTEGER'),('custo_saca','REAL DEFAULT 0'),('lucro_total','REAL DEFAULT 0'),('forma_pagamento','TEXT')],
        'financeiro': [('categoria','TEXT')]
    }.items():
        for column, definition in cols:
            add_column(cur, table, column, definition)
    con.commit(); con.close()


def fetchall(query, params=()):
    con = db(); rows = con.execute(query, params).fetchall(); con.close(); return rows


def fetchone(query, params=()):
    con = db(); row = con.execute(query, params).fetchone(); con.close(); return row


def fnum(name):
    raw = (request.form.get(name) or '0').replace('.', '').replace(',', '.') if isinstance(request.form.get(name), str) else request.form.get(name)
    try: return float(raw or 0)
    except Exception: return 0.0


def today(): return date.today().isoformat()


def lote_estoque_expr():
    return """c.quantidade_sacas - COALESCE((SELECT SUM(v.quantidade_sacas) FROM vendas v WHERE v.compra_id=c.id),0)"""


@app.route('/')
def index():
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
        con.commit(); con.close(); flash('Cadastro salvo com sucesso.')
        return redirect(url_for('pessoas'))
    q = request.args.get('q','').strip()
    sql = "SELECT * FROM pessoas"
    params = ()
    if q:
        sql += " WHERE nome LIKE ? OR telefone LIKE ? OR whatsapp LIKE ? OR cidade LIKE ? OR documento LIKE ?"
        params = tuple([f'%{q}%']*5)
    rows = fetchall(sql + " ORDER BY id DESC", params)
    return render_template('pessoas.html', pessoas=rows, q=q)


@app.route('/compras', methods=['GET','POST'])
def compras():
    pessoas_rows = fetchall("SELECT * FROM pessoas WHERE tipo IN ('Fornecedor','Cliente e Fornecedor') ORDER BY nome")
    if request.method == 'POST':
        qtd, valor_saca = fnum('quantidade_sacas'), fnum('valor_saca')
        frete, outras = fnum('frete'), fnum('outras_despesas')
        total = qtd * valor_saca + frete + outras
        con = db(); cur = con.cursor()
        cur.execute("""INSERT INTO compras (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,valor_saca,valor_total,status_pagamento,forma_pagamento,frete,outras_despesas,origem_cafe,status_lote,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, request.form['data'], request.form.get('lote'), request.form.get('tipo_cafe'), qtd, fnum('peso_kg'), valor_saca, total, request.form.get('status_pagamento'), request.form.get('forma_pagamento'), frete, outras, request.form.get('origem_cafe'), request.form.get('status_lote'), request.form.get('observacao')))
        compra_id = cur.lastrowid
        lote = request.form.get('lote') or f"Compra {compra_id}"
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (request.form['data'], 'Saída', f"Compra de café - {lote}", 'Compra de café', total, request.form.get('status_pagamento'), f"compra:{compra_id}"))
        con.commit(); con.close(); flash('Compra lançada. Lote, estoque e financeiro atualizados.')
        return redirect(url_for('compras'))
    rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    return render_template('compras.html', compras=rows, pessoas=pessoas_rows, hoje=today())


@app.route('/provas', methods=['GET','POST'])
def provas():
    compras_rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    if request.method == 'POST':
        con = db()
        con.execute("""INSERT INTO provas (compra_id,data,bebida,peneira,umidade,defeitos,aroma,corpo,acidez,docura,nota,classificacao,aprovado,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('compra_id') or None, request.form['data'], request.form.get('bebida'), request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('aroma'), request.form.get('corpo'), request.form.get('acidez'), request.form.get('docura'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('aprovado'), request.form.get('observacao')))
        con.commit(); con.close(); flash('Prova registrada com classificação.')
        return redirect(url_for('provas'))
    rows = fetchall("""SELECT provas.*, compras.lote, compras.tipo_cafe, pessoas.nome pessoa_nome FROM provas LEFT JOIN compras ON compras.id = provas.compra_id LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY provas.id DESC""")
    return render_template('provas.html', provas=rows, compras=compras_rows, hoje=today())


@app.route('/vendas', methods=['GET','POST'])
def vendas():
    pessoas_rows = fetchall("SELECT * FROM pessoas WHERE tipo IN ('Cliente','Cliente e Fornecedor') ORDER BY nome")
    lotes = fetchall(f"""SELECT c.*, p.nome pessoa_nome, ({lote_estoque_expr()}) estoque_lote FROM compras c LEFT JOIN pessoas p ON p.id=c.pessoa_id WHERE ({lote_estoque_expr()}) > 0 ORDER BY c.id DESC""")
    if request.method == 'POST':
        qtd, valor_saca = fnum('quantidade_sacas'), fnum('valor_saca')
        compra_id = request.form.get('compra_id') or None
        compra = fetchone("SELECT * FROM compras WHERE id=?", (compra_id,)) if compra_id else None
        custo_saca = float(compra['valor_saca']) if compra else fnum('custo_saca')
        total = qtd * valor_saca
        lucro = (valor_saca - custo_saca) * qtd
        lote = request.form.get('lote') or (compra['lote'] if compra else '')
        tipo_cafe = request.form.get('tipo_cafe') or (compra['tipo_cafe'] if compra else '')
        con = db(); cur = con.cursor()
        cur.execute("""INSERT INTO vendas (pessoa_id,compra_id,data,lote,tipo_cafe,quantidade_sacas,valor_saca,valor_total,custo_saca,lucro_total,status_recebimento,forma_pagamento,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, compra_id, request.form['data'], lote, tipo_cafe, qtd, valor_saca, total, custo_saca, lucro, request.form.get('status_recebimento'), request.form.get('forma_pagamento'), request.form.get('observacao')))
        venda_id = cur.lastrowid
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,categoria,valor,status,origem) VALUES (?,?,?,?,?,?,?)",
                    (request.form['data'], 'Entrada', f"Venda de café - {lote or venda_id}", 'Venda de café', total, request.form.get('status_recebimento'), f"venda:{venda_id}"))
        con.commit(); con.close(); flash('Venda lançada com cálculo de lucro automático.')
        return redirect(url_for('vendas'))
    rows = fetchall("""SELECT vendas.*, pessoas.nome pessoa_nome FROM vendas LEFT JOIN pessoas ON pessoas.id = vendas.pessoa_id ORDER BY vendas.id DESC""")
    return render_template('vendas.html', vendas=rows, pessoas=pessoas_rows, lotes=lotes, hoje=today())


@app.route('/lotes')
def lotes():
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
    return render_template('relatorios.html', compras_tipo=compras_tipo, vendas_tipo=vendas_tipo, ranking_produtores=ranking_produtores, ranking_clientes=ranking_clientes, pendencias=pendencias)


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

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
