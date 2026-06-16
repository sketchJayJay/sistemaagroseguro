from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
app.secret_key = "controle-cafe-dev"
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "controle_cafe.sqlite3"


def br_money(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

app.jinja_env.filters["money"] = br_money


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS pessoas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        telefone TEXT,
        cidade TEXT,
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
        nota TEXT,
        classificacao TEXT,
        observacao TEXT,
        FOREIGN KEY(compra_id) REFERENCES compras(id)
    );

    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pessoa_id INTEGER,
        data TEXT NOT NULL,
        lote TEXT,
        tipo_cafe TEXT,
        quantidade_sacas REAL NOT NULL DEFAULT 0,
        valor_saca REAL NOT NULL DEFAULT 0,
        valor_total REAL NOT NULL DEFAULT 0,
        status_recebimento TEXT DEFAULT 'Pendente',
        observacao TEXT,
        FOREIGN KEY(pessoa_id) REFERENCES pessoas(id)
    );

    CREATE TABLE IF NOT EXISTS financeiro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        tipo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'Pendente',
        origem TEXT
    );
    ''')
    con.commit()
    con.close()


def fetchall(query, params=()):
    con = db()
    rows = con.execute(query, params).fetchall()
    con.close()
    return rows


def fetchone(query, params=()):
    con = db()
    row = con.execute(query, params).fetchone()
    con.close()
    return row


@app.route('/')
def index():
    total_compras = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM compras")['v']
    total_vendas = fetchone("SELECT COALESCE(SUM(valor_total),0) v FROM vendas")['v']
    sacas_compradas = fetchone("SELECT COALESCE(SUM(quantidade_sacas),0) v FROM compras")['v']
    sacas_vendidas = fetchone("SELECT COALESCE(SUM(quantidade_sacas),0) v FROM vendas")['v']
    financeiro_entrada = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Entrada'")['v']
    financeiro_saida = fetchone("SELECT COALESCE(SUM(valor),0) v FROM financeiro WHERE tipo='Saída'")['v']
    ultimas_compras = fetchall("""
        SELECT compras.*, pessoas.nome pessoa_nome FROM compras
        LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id
        ORDER BY compras.id DESC LIMIT 5
    """)
    ultimas_vendas = fetchall("""
        SELECT vendas.*, pessoas.nome pessoa_nome FROM vendas
        LEFT JOIN pessoas ON pessoas.id = vendas.pessoa_id
        ORDER BY vendas.id DESC LIMIT 5
    """)
    return render_template('index.html', total_compras=total_compras, total_vendas=total_vendas,
                           sacas_compradas=sacas_compradas, sacas_vendidas=sacas_vendidas,
                           estoque=sacas_compradas - sacas_vendidas,
                           saldo=financeiro_entrada - financeiro_saida,
                           ultimas_compras=ultimas_compras, ultimas_vendas=ultimas_vendas)


@app.route('/pessoas', methods=['GET', 'POST'])
def pessoas():
    if request.method == 'POST':
        con = db()
        con.execute("INSERT INTO pessoas (tipo,nome,telefone,cidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                    (request.form['tipo'], request.form['nome'], request.form.get('telefone'), request.form.get('cidade'), request.form.get('observacao'), datetime.now().isoformat()))
        con.commit(); con.close()
        flash('Cadastro salvo com sucesso.')
        return redirect(url_for('pessoas'))
    q = request.args.get('q','').strip()
    if q:
        rows = fetchall("SELECT * FROM pessoas WHERE nome LIKE ? OR telefone LIKE ? OR cidade LIKE ? ORDER BY nome", (f'%{q}%', f'%{q}%', f'%{q}%'))
    else:
        rows = fetchall("SELECT * FROM pessoas ORDER BY id DESC")
    return render_template('pessoas.html', pessoas=rows, q=q)


@app.route('/compras', methods=['GET', 'POST'])
def compras():
    pessoas_rows = fetchall("SELECT * FROM pessoas WHERE tipo IN ('Fornecedor','Cliente e Fornecedor') ORDER BY nome")
    if request.method == 'POST':
        qtd = float(request.form.get('quantidade_sacas') or 0)
        valor_saca = float(request.form.get('valor_saca') or 0)
        total = qtd * valor_saca
        con = db()
        cur = con.cursor()
        cur.execute("""INSERT INTO compras (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,peso_kg,valor_saca,valor_total,status_pagamento,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, request.form['data'], request.form.get('lote'), request.form.get('tipo_cafe'), qtd,
                     float(request.form.get('peso_kg') or 0), valor_saca, total, request.form.get('status_pagamento'), request.form.get('observacao')))
        compra_id = cur.lastrowid
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,valor,status,origem) VALUES (?,?,?,?,?,?)",
                    (request.form['data'], 'Saída', f"Compra de café lote {request.form.get('lote') or compra_id}", total, request.form.get('status_pagamento'), f"compra:{compra_id}"))
        con.commit(); con.close()
        flash('Compra lançada e estoque atualizado.')
        return redirect(url_for('compras'))
    rows = fetchall("""
        SELECT compras.*, pessoas.nome pessoa_nome FROM compras
        LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id
        ORDER BY compras.id DESC
    """)
    return render_template('compras.html', compras=rows, pessoas=pessoas_rows, hoje=datetime.now().date().isoformat())


@app.route('/provas', methods=['GET', 'POST'])
def provas():
    compras_rows = fetchall("""SELECT compras.*, pessoas.nome pessoa_nome FROM compras LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id ORDER BY compras.id DESC""")
    if request.method == 'POST':
        con = db()
        con.execute("""INSERT INTO provas (compra_id,data,bebida,peneira,umidade,defeitos,nota,classificacao,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('compra_id') or None, request.form['data'], request.form.get('bebida'), request.form.get('peneira'), request.form.get('umidade'), request.form.get('defeitos'), request.form.get('nota'), request.form.get('classificacao'), request.form.get('observacao')))
        con.commit(); con.close()
        flash('Prova registrada.')
        return redirect(url_for('provas'))
    rows = fetchall("""
        SELECT provas.*, compras.lote, compras.tipo_cafe, pessoas.nome pessoa_nome
        FROM provas
        LEFT JOIN compras ON compras.id = provas.compra_id
        LEFT JOIN pessoas ON pessoas.id = compras.pessoa_id
        ORDER BY provas.id DESC
    """)
    return render_template('provas.html', provas=rows, compras=compras_rows, hoje=datetime.now().date().isoformat())


@app.route('/vendas', methods=['GET', 'POST'])
def vendas():
    pessoas_rows = fetchall("SELECT * FROM pessoas WHERE tipo IN ('Cliente','Cliente e Fornecedor') ORDER BY nome")
    if request.method == 'POST':
        qtd = float(request.form.get('quantidade_sacas') or 0)
        valor_saca = float(request.form.get('valor_saca') or 0)
        total = qtd * valor_saca
        con = db(); cur = con.cursor()
        cur.execute("""INSERT INTO vendas (pessoa_id,data,lote,tipo_cafe,quantidade_sacas,valor_saca,valor_total,status_recebimento,observacao)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                    (request.form.get('pessoa_id') or None, request.form['data'], request.form.get('lote'), request.form.get('tipo_cafe'), qtd, valor_saca, total, request.form.get('status_recebimento'), request.form.get('observacao')))
        venda_id = cur.lastrowid
        cur.execute("INSERT INTO financeiro (data,tipo,descricao,valor,status,origem) VALUES (?,?,?,?,?,?)",
                    (request.form['data'], 'Entrada', f"Venda de café lote {request.form.get('lote') or venda_id}", total, request.form.get('status_recebimento'), f"venda:{venda_id}"))
        con.commit(); con.close()
        flash('Venda lançada e estoque atualizado.')
        return redirect(url_for('vendas'))
    rows = fetchall("""
        SELECT vendas.*, pessoas.nome pessoa_nome FROM vendas
        LEFT JOIN pessoas ON pessoas.id = vendas.pessoa_id
        ORDER BY vendas.id DESC
    """)
    return render_template('vendas.html', vendas=rows, pessoas=pessoas_rows, hoje=datetime.now().date().isoformat())


@app.route('/financeiro', methods=['GET', 'POST'])
def financeiro():
    if request.method == 'POST':
        con = db()
        con.execute("INSERT INTO financeiro (data,tipo,descricao,valor,status,origem) VALUES (?,?,?,?,?,?)",
                    (request.form['data'], request.form['tipo'], request.form['descricao'], float(request.form.get('valor') or 0), request.form.get('status'), 'manual'))
        con.commit(); con.close()
        flash('Lançamento financeiro salvo.')
        return redirect(url_for('financeiro'))
    rows = fetchall("SELECT * FROM financeiro ORDER BY data DESC, id DESC")
    entrada = sum(r['valor'] for r in rows if r['tipo'] == 'Entrada')
    saida = sum(r['valor'] for r in rows if r['tipo'] == 'Saída')
    return render_template('financeiro.html', itens=rows, entrada=entrada, saida=saida, saldo=entrada-saida, hoje=datetime.now().date().isoformat())


@app.route('/relatorios')
def relatorios():
    compras_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total FROM compras GROUP BY tipo_cafe")
    vendas_tipo = fetchall("SELECT COALESCE(tipo_cafe,'Sem tipo') nome, SUM(quantidade_sacas) sacas, SUM(valor_total) total FROM vendas GROUP BY tipo_cafe")
    pendencias = fetchall("SELECT * FROM financeiro WHERE status='Pendente' ORDER BY data DESC")
    return render_template('relatorios.html', compras_tipo=compras_tipo, vendas_tipo=vendas_tipo, pendencias=pendencias)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=True)
else:
    init_db()
