"""Regressões das operações de café. Todos os testes usam bancos temporários."""
import io
import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from flask import template_rendered

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
_OLD_DATA_DIR = os.environ.get('DATA_DIR')
os.environ['DATA_DIR'] = _BOOT.name
import app as sistema
if _OLD_DATA_DIR is None:
    os.environ.pop('DATA_DIR', None)
else:
    os.environ['DATA_DIR'] = _OLD_DATA_DIR

class OperacoesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sistema.DB_DIR = Path(self.tmp.name)
        sistema.DB_PATH = sistema.DB_DIR / 'controle_cafe.sqlite3'
        sistema.init_db()
        sistema.app.config.update(TESTING=True)
        self.client = sistema.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, **data):
        response = self.client.post(path, data=data)
        self.assertEqual(response.status_code, 302)
        return response

    def pessoa(self, nome='Produtor de teste'):
        self.post('/pessoas', tipo='Cliente e Fornecedor', nome=nome)
        return sistema.fetchone('SELECT MAX(id) id FROM pessoas')['id']

    def compra(self, pessoa=None, **extra):
        dados = dict(data=sistema.today(), lote='Lote teste', quantidade_sacas='26.24', peso_kg='1574.4', divisor_saca='60', valor_saca='1000', status_pagamento='Pendente', tipo_cafe='Duro')
        if pessoa: dados['pessoa_id']=str(pessoa)
        dados.update(extra)
        self.post('/compras', **dados)
        return sistema.fetchone('SELECT MAX(id) id FROM compras')['id']

    def venda(self, compra=None, pessoa=None, **extra):
        dados = dict(data=sistema.today(), quantidade_sacas='6.24', valor_saca='1300', status_recebimento='A pagar ao cliente')
        if compra: dados['compra_id']=str(compra)
        if pessoa: dados['pessoa_id']=str(pessoa)
        dados.update(extra)
        self.post('/vendas', **dados)
        return sistema.fetchone('SELECT MAX(id) id FROM vendas')['id']

    def context(self, path):
        result=[]
        def capture(sender,template,context,**extra): result.append(context)
        template_rendered.connect(capture, sistema.app, weak=False)
        try:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            return result[-1]
        finally:
            template_rendered.disconnect(capture,sistema.app)

    def estoque(self,cid):
        return sistema.get_lote_historico(cid)['restante']

    def test_peso_sacas_vendas_parciais_e_estorno(self):
        pessoa=self.pessoa()
        cid=self.compra(pessoa,quantidade_sacas='',peso_kg='1574,40')
        self.assertAlmostEqual(self.estoque(cid),26.24)
        v1=self.venda(cid,valor_saca='1.300,00')
        v2=self.venda(cid,quantidade_sacas='5',valor_saca='1405')
        self.assertAlmostEqual(self.estoque(cid),15)
        row=sistema.fetchone('SELECT * FROM vendas WHERE id=?',(v1,))
        self.assertEqual(row['pessoa_id'],pessoa)
        self.assertAlmostEqual(row['valor_total'],8112)
        self.post(f'/vendas/{v2}/excluir')
        self.assertAlmostEqual(self.estoque(cid),20)
        self.assertEqual(sistema.fetchone('SELECT status_lote FROM compras WHERE id=?',(cid,))['status_lote'],'Vendido parcial')

    def test_venda_nao_ultrapassa_estoque(self):
        cid=self.compra()
        self.venda(cid,quantidade_sacas='26.24')
        self.venda(cid,quantidade_sacas='0.01')
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),1)
        self.assertAlmostEqual(self.estoque(cid),0)

    def test_duas_vendas_concorrentes_nao_geram_saldo_negativo(self):
        cid=self.compra(quantidade_sacas='10')
        def vender(_):
            with sistema.app.test_client() as client:
                return client.post('/vendas',data={'data':sistema.today(),'compra_id':str(cid),'quantidade_sacas':'7','valor_saca':'1000'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(vender,range(2))),[302,302])
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),1)
        self.assertAlmostEqual(self.estoque(cid),3)

    def test_numeros_invalidos_e_negativos_nao_sao_salvos(self):
        for invalid in ['-1','nan','inf','texto']:
            self.venda(quantidade_sacas=invalid)
        self.venda(quantidade_sacas='0')
        self.compra(quantidade_sacas='-5')
        self.post('/financeiro',data=sistema.today(),tipo='Entrada',descricao='Inválido',valor='-100')
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),0)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM compras')),0)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM financeiro')),0)

    def test_editar_quantidade_compra_menor_que_vendido_faz_rollback(self):
        pessoa=self.pessoa();cid=self.compra(pessoa);self.venda(cid)
        self.post(f'/compras/{cid}/editar',data=sistema.today(),pessoa_id=str(pessoa),quantidade_sacas='5',valor_saca='2000',status_pagamento='Pago')
        row=sistema.fetchone('SELECT * FROM compras WHERE id=?',(cid,))
        self.assertAlmostEqual(row['quantidade_sacas'],26.24)
        self.assertEqual(row['valor_saca'],1000)
        self.assertEqual(row['status_pagamento'],'Pendente')

    def test_venda_invalida_na_edicao_da_compra_nao_salva_metade_da_operacao(self):
        cid=self.compra()
        self.post(f'/compras/{cid}/editar',data=sistema.today(),quantidade_sacas='26.24',valor_saca='1700',venda_quantidade_sacas='30',venda_valor_saca='2000')
        self.assertEqual(sistema.fetchone('SELECT valor_saca FROM compras WHERE id=?',(cid,))['valor_saca'],1000)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),0)

    def test_editar_venda_considera_quantidade_anterior(self):
        cid=self.compra();vid=self.venda(cid)
        self.post(f'/vendas/{vid}/editar',data=sistema.today(),compra_id=str(cid),quantidade_sacas='26.24',valor_saca='1400',status_recebimento='A pagar ao cliente')
        self.assertAlmostEqual(self.estoque(cid),0)
        self.post(f'/vendas/{vid}/editar',data=sistema.today(),compra_id=str(cid),quantidade_sacas='30',valor_saca='1400')
        self.assertAlmostEqual(self.estoque(cid),0)
        self.assertAlmostEqual(sistema.fetchone('SELECT quantidade_sacas FROM vendas WHERE id=?',(vid,))['quantidade_sacas'],26.24)

    def test_custo_do_lote_inclui_despesas_e_recalcula_lucro(self):
        cid=self.compra(quantidade_sacas='10',frete='500',outras_despesas='200')
        vid=self.venda(cid,quantidade_sacas='2',valor_saca='1300')
        row=sistema.fetchone('SELECT * FROM vendas WHERE id=?',(vid,))
        self.assertAlmostEqual(row['custo_saca'],1070)
        self.assertAlmostEqual(row['lucro_total'],460)
        self.post(f'/compras/{cid}/editar',data=sistema.today(),quantidade_sacas='10',valor_saca='1100',frete='500',outras_despesas='200')
        self.assertAlmostEqual(sistema.fetchone('SELECT lucro_total FROM vendas WHERE id=?',(vid,))['lucro_total'],260)

    def test_venda_nao_pode_mudar_proprietario_do_lote(self):
        p1,p2=self.pessoa('João'),self.pessoa('Dois');cid=self.compra(p1)
        self.assertEqual(len(self.context('/clientes?q=joao')['clientes']),1)
        self.assertEqual(len(self.context('/compras?q=joao')['compras']),1)
        self.venda(cid,p2)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),0)
        self.assertAlmostEqual(self.estoque(cid),26.24)

    def test_venda_avulsa_nao_baixa_estoque_dos_lotes(self):
        self.compra(quantidade_sacas='10');self.venda(quantidade_sacas='5')
        self.assertAlmostEqual(self.context('/')['estoque'],10)

    def test_excluir_compra_com_vendas_nao_apaga_historico(self):
        cid=self.compra();self.venda(cid)
        self.post(f'/compras/{cid}/excluir')
        self.assertIsNotNone(sistema.fetchone('SELECT id FROM compras WHERE id=?',(cid,)))
        self.assertEqual(len(sistema.fetchall('SELECT * FROM vendas')),1)

    def test_excluir_compra_sem_vendas_preserva_prova(self):
        cid=self.compra()
        self.post('/provas',data=sistema.today(),compra_id=str(cid),bebida='Duro',aprovado='Aprovado')
        self.post(f'/compras/{cid}/excluir')
        row=sistema.fetchone('SELECT * FROM provas')
        self.assertIsNotNone(row)
        self.assertIsNone(row['compra_id'])
        self.assertEqual(row['aprovado'],'Aprovado')

    def test_prova_aprovada_e_reserva_persistem_apos_reiniciar(self):
        self.post('/provas',data=sistema.today(),nome_avulso='Teste',bebida='Duro',aprovado='Aprovado')
        cid=self.compra(status_lote='Reservado')
        sistema.init_db();sistema.init_db();self.client.get('/')
        self.assertEqual(sistema.fetchone('SELECT aprovado FROM provas')['aprovado'],'Aprovado')
        self.assertEqual(sistema.fetchone('SELECT status_lote FROM compras WHERE id=?',(cid,))['status_lote'],'Reservado')

    def test_prova_transformada_uma_vez_sem_cadastro_duplicado(self):
        self.post('/provas',data=sistema.today(),nome_avulso='Avulso',quantidade_sacas='10',bebida='Duro')
        pid=sistema.fetchone('SELECT id FROM provas')['id']
        self.post(f'/provas/{pid}/transformar-compra',valor_saca='0')
        self.assertEqual(len(sistema.fetchall('SELECT * FROM pessoas')),0)
        self.post(f'/provas/{pid}/transformar-compra',valor_saca='1000')
        self.post(f'/provas/{pid}/transformar-compra',valor_saca='1000')
        self.assertEqual(len(sistema.fetchall('SELECT * FROM pessoas')),1)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM compras')),1)
        self.assertEqual(sistema.fetchone('SELECT aprovado FROM provas')['aprovado'],'Aprovado')

    def test_juros_com_aniversario_no_fim_do_mes(self):
        self.assertEqual(sistema.meses_juros_automatico('2026-01-31',date(2026,2,28)),1)
        self.assertEqual(sistema.meses_juros_automatico('2024-01-31',date(2024,2,29)),1)
        self.assertEqual(sistema.meses_juros_automatico('2026-01-31',date(2026,2,27)),0)
        self.assertEqual(sistema.calcular_juros_simples(800,3,2),(48,848))

    def test_financeiro_saldo_realizado_filtros_e_exportacao(self):
        self.post('/financeiro',data='2026-09-01',tipo='Entrada',descricao='Pago setembro',valor='100',status='Recebido')
        self.post('/financeiro',data='2026-09-02',tipo='Entrada',descricao='Pendente setembro',valor='500',status='Pendente')
        self.post('/financeiro',data='2026-10-01',tipo='Saída',descricao='Pago outubro',valor='20',status='Pago')
        ctx=self.context('/financeiro')
        self.assertEqual((ctx['entrada'],ctx['saida'],ctx['saldo'],ctx['receber']),(100,20,80,500))
        ctx=self.context('/financeiro?mes=2026-09&status=Recebido')
        self.assertEqual(len(ctx['itens']),1)
        csv=self.client.get('/exportar/financeiro.csv?mes=2026-09&status=Recebido').data.decode('utf-8-sig')
        self.assertIn('Pago setembro',csv)
        self.assertNotIn('Pendente setembro',csv)
        self.assertNotIn('Pago outubro',csv)
        self.assertIn('100,00',csv)

    def test_baixa_financeira_sincroniza_compra_e_venda(self):
        cid=self.compra();vid=self.venda(cid)
        for origem,path,col,expected in [(f'compra:{cid}','compras','status_pagamento','Pago'),(f'venda:{vid}','vendas','status_recebimento','Pago ao cliente')]:
            item=sistema.fetchone('SELECT id FROM financeiro WHERE origem=?',(origem,))
            self.post(f'/financeiro/{item["id"]}/baixar')
            self.post(f'/financeiro/{item["id"]}/baixar')
            self.assertEqual(sistema.fetchone(f'SELECT {col} FROM {path}')[col],expected)
        self.assertEqual(len(sistema.fetchall('SELECT * FROM financeiro')),2)

    def test_editar_excluir_financeiro_manual_e_proteger_vinculados(self):
        self.post('/financeiro',data=sistema.today(),tipo='Saída',descricao='Manual',valor='100',status='Pago')
        mid=sistema.fetchone('SELECT id FROM financeiro')['id']
        self.post(f'/financeiro/{mid}/editar',data=sistema.today(),tipo='Saída',descricao='Corrigido',valor='150',status='Pago')
        self.assertEqual(sistema.fetchone('SELECT valor FROM financeiro WHERE id=?',(mid,))['valor'],150)
        cid=self.compra();linked=sistema.fetchone('SELECT id FROM financeiro WHERE origem=?',(f'compra:{cid}',))['id']
        self.post(f'/financeiro/{linked}/excluir')
        self.assertIsNotNone(sistema.fetchone('SELECT id FROM financeiro WHERE id=?',(linked,)))
        self.post(f'/financeiro/{mid}/excluir')
        self.assertIsNone(sistema.fetchone('SELECT id FROM financeiro WHERE id=?',(mid,)))

    def test_acerto_desconta_adiantamento_sem_duplicar_caixa(self):
        pessoa=self.pessoa();cid=self.compra(pessoa,quantidade_sacas='10');vid=self.venda(cid,quantidade_sacas='2',valor_saca='1000')
        self.post(f'/clientes/{pessoa}/adiantamentos',data=sistema.today(),valor='500',taxa_juros='0',lancar_financeiro='1')
        self.assertEqual(sistema.get_acerto_data(pessoa)['total'],1500)
        self.post(f'/clientes/{pessoa}/acertar-tudo')
        self.assertEqual(sistema.fetchone('SELECT status FROM financeiro WHERE origem=?',(f'venda:{vid}',))['status'],'Compensado')
        acerto=sistema.fetchone("SELECT * FROM financeiro WHERE origem LIKE 'acerto:%'")
        self.assertEqual((acerto['tipo'],acerto['valor']),('Saída',1500))
        ctx=self.context('/financeiro')
        self.assertEqual(ctx['saida'],2000)
        self.assertEqual(sistema.get_acerto_data(pessoa)['total'],0)
        self.post(f'/clientes/{pessoa}/acertar-tudo')
        self.assertEqual(len(sistema.fetchall("SELECT * FROM financeiro WHERE origem LIKE 'acerto:%'")),1)
        self.post(f'/vendas/{vid}/excluir')
        self.assertIsNotNone(sistema.fetchone('SELECT id FROM vendas WHERE id=?',(vid,)))

    def test_acerto_negativo_registra_recebimento_do_cliente(self):
        pessoa=self.pessoa();self.venda(pessoa=pessoa,quantidade_sacas='1',valor_saca='100')
        self.post(f'/clientes/{pessoa}/adiantamentos',data=sistema.today(),valor='500',taxa_juros='0')
        self.assertEqual(sistema.get_acerto_data(pessoa)['total'],-400)
        self.post(f'/clientes/{pessoa}/acertar-tudo')
        row=sistema.fetchone("SELECT * FROM financeiro WHERE origem LIKE 'acerto:%'")
        self.assertEqual((row['tipo'],row['valor'],row['status']),('Entrada',400,'Recebido'))

    def test_dashboard_nao_compensa_divida_entre_clientes(self):
        p1,p2=self.pessoa('Um'),self.pessoa('Dois')
        self.venda(pessoa=p1,quantidade_sacas='1',valor_saca='1000')
        self.post(f'/clientes/{p2}/adiantamentos',data=sistema.today(),valor='800',taxa_juros='0')
        ctx=self.context('/')
        self.assertEqual(ctx['liquido_a_pagar_clientes'],1000)
        self.assertEqual(ctx['saldo_recuperar'],800)

    def test_deletar_cadastro_com_movimentacoes_e_bloqueado(self):
        pessoa=self.pessoa();self.compra(pessoa)
        self.post(f'/pessoas/{pessoa}/excluir')
        self.assertIsNotNone(sistema.fetchone('SELECT id FROM pessoas WHERE id=?',(pessoa,)))

    def test_ranking_nao_duplica_compras_com_multiplas_provas(self):
        pessoa=self.pessoa();cid=self.compra(pessoa,quantidade_sacas='10')
        for nota in ['80','90']:
            self.post('/provas',data=sistema.today(),compra_id=str(cid),nota=nota,bebida='Duro')
        row=self.context('/relatorios')['ranking_produtores'][0]
        self.assertEqual(row['sacas'],10)
        self.assertEqual(row['total'],10000)
        self.assertEqual(row['nota_media'],85)

    def test_backup_invalido_preserva_banco_e_valido_restaura(self):
        pessoa=self.pessoa()
        antes=sistema.DB_PATH.read_bytes()
        self.client.post('/backup',data={'arquivo':(io.BytesIO(b'arquivo corrompido'),'teste.sqlite3')},content_type='multipart/form-data')
        self.assertEqual(antes,sistema.DB_PATH.read_bytes())
        backup=self.client.get('/backup/baixar').data
        self.pessoa('Posterior')
        self.client.post('/backup',data={'arquivo':(io.BytesIO(backup),'backup.sqlite3')},content_type='multipart/form-data')
        self.assertEqual(len(sistema.fetchall('SELECT * FROM pessoas')),1)
        self.assertEqual(sistema.fetchone('SELECT id FROM pessoas')['id'],pessoa)
        self.assertEqual(sistema.fetchone('PRAGMA integrity_check')[0],'ok')
        self.assertTrue(list(sistema.DB_DIR.glob('backup_antes_restaurar_*.sqlite3')))

    def test_migracao_do_banco_original_nao_apaga_dados(self):
        shutil.copy2(ROOT/'data'/'controle_cafe.sqlite3',sistema.DB_PATH)
        sistema.init_db()
        pessoa=self.pessoa('Preservado');cid=self.compra(pessoa)
        before={t:len(sistema.fetchall(f'SELECT * FROM {t}')) for t in ['pessoas','compras','financeiro']}
        sistema.init_db();sistema.init_db()
        self.assertEqual(before,{t:len(sistema.fetchall(f'SELECT * FROM {t}')) for t in before})
        self.assertAlmostEqual(self.estoque(cid),26.24)

    def test_todas_as_telas_impressos_e_exportacoes_abrem(self):
        pessoa=self.pessoa();cid=self.compra(pessoa);vid=self.venda(cid)
        self.post('/provas',data=sistema.today(),pessoa_id=str(pessoa),bebida='Duro')
        pid=sistema.fetchone('SELECT id FROM provas')['id']
        self.post('/financeiro',data=sistema.today(),tipo='Entrada',descricao='Manual',valor='100',status='Pago')
        mid=sistema.fetchone("SELECT id FROM financeiro WHERE origem='manual'")['id']
        paths=['/','/pessoas','/clientes','/compras','/vendas','/provas','/lotes','/financeiro','/relatorios','/simulador','/busca?q=teste','/backup','/historico','/relatorios/cafes-analise',f'/clientes/{pessoa}',f'/clientes/{pessoa}/extrato',f'/clientes/{pessoa}/acerto',f'/compras/{cid}/editar',f'/compras/{cid}/historico',f'/vendas/{vid}/editar',f'/provas/{pid}/editar',f'/provas/{pid}/comprovante',f'/pessoas/{pessoa}/editar',f'/financeiro/{mid}/editar',f'/recibo/compra/{cid}',f'/recibo/venda/{vid}']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,200)
        for kind in ['clientes','compras','vendas','provas','financeiro']:
            self.assertEqual(self.client.get('/exportar/'+kind+'.csv').status_code,200)
        self.assertEqual(self.client.post('/simulador',data={'quantidade':'10','preco_compra':'1000','preco_venda':'1300','frete':'300','despesas':'200'}).status_code,200)

if __name__ == '__main__':
    unittest.main()
