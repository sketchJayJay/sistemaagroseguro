# Controle Café Pro

Sistema web/mobile para quem trabalha com compra, prova e venda de café.

## Funções principais

- Cadastro completo de clientes, fornecedores e produtores
- Compra de café com lote, frete, despesas e pagamento
- Prova/classificação do café com bebida, peneira, umidade, defeitos e nota
- Venda por lote com cálculo automático de custo, lucro e margem
- Estoque por lote com venda parcial/total
- Financeiro com entradas, saídas, contas a pagar e contas a receber
- Recibo de compra e venda para imprimir ou salvar em PDF
- Relatórios e ranking de produtores/clientes
- Simulador de negociação para saber se a compra compensa
- Exportação CSV do financeiro
- Layout responsivo para celular e computador

## Rodar local

```bash
pip install -r requirements.txt
python app.py
```

Acesse: http://localhost:8080

## Coolify

- Tipo: Dockerfile
- Porta: 8080
- Volume recomendado para não perder dados: `/app/data`
