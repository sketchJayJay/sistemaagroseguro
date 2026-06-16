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


## Personalização aplicada

- Identidade visual da empresa **Café Boa Vista**
- Logo aplicada no menu lateral, painel e recibos
- Dados do comprador e contatos exibidos no sistema
- Tema em verde/branco seguindo a marca

## Atualização solicitada

- Provas com cliente cadastrado ou nome avulso, quantidade de saca, cata e resultado padrão "Em análise".
- Provas vinculadas aparecem dentro do painel do cliente.
- Painel do cliente com vendas, estoque restante, saldo por tipo de café e cálculo de juros por taxa/mês em atraso.
- Tipos de café padronizados: Duro, Duro riado, Duro riado Rio, Riado rio, Rio e Escolha.
- Compras com cálculo de sacas por peso dividido pelo kg/saca e ajuste manual.
- Edição e exclusão de clientes, compras e vendas.
- Venda recalcula status do lote para Vendido ou Vendido parcial.
- Venda permite editar preço, juros, meses em atraso e status de recebimento.
- Busca nos seletores de cliente/fornecedor para facilitar no celular.
