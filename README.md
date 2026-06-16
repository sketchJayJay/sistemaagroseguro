# Controle Café

Sistema web simples para empresas que trabalham com compra, prova e venda de café.

## Rodar local
```bash
pip install -r requirements.txt
python app.py
```
Acesse: http://localhost:8080

## Coolify
- Build Pack: Dockerfile
- Porta: 8080
- Volume recomendado: `/app/data` para não perder o banco SQLite

## Funcionalidades
- Cadastro de clientes e fornecedores
- Compra/entrada de café
- Prova/classificação do lote
- Venda/saída de café
- Estoque automático
- Financeiro simples
- Relatórios
