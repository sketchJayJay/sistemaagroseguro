# Café Boa Vista · Gestão do Café 2.0

Sistema web para clientes e produtores, provas, compras, lotes, vendas parciais, adiantamentos, acertos e financeiro. Interface renovada em verde escuro, com telas adaptadas a celular e computador.

## O que mudou

- Menu compacto com indicação da tela atual; menu lateral móvel e botão de voltar.
- Painel com vendas dos últimos seis meses, estoque por tipo e atalhos para pendências.
- Indicadores clicáveis e gráficos gerados pelos próprios lançamentos, sem serviços externos.
- Compras e vendas com prévia do total; detalhes opcionais ficam recolhidos.
- Ao escolher um lote na venda, proprietário, tipo de café e saldo disponível são preenchidos.
- Filtros por cliente/lote, tipo, situação e datas nas compras, vendas e estoque.
- Painel do cliente dividido em Resumo, Vendas, Estoque, Provas, Adiantamentos e Contas/Pix.
- Financeiro com filtro de mês, tipo e situação, baixa de pendências e edição/exclusão de lançamentos manuais.
- Exportação do financeiro respeita a seleção exibida; CSV com acentuação e valores brasileiros.
- Tabelas com ordenação e paginação local; campos de busca filtram nomes com ou sem acentos.
- Recibos, comprovantes, extratos, WhatsApp e impressão continuam disponíveis.

## Correções de operação

1. Provas aprovadas permanecem aprovadas após reiniciar ou atualizar.
2. Uma prova só pode gerar uma compra; falhas de validação não criam cadastros avulsos.
3. O saldo de estoque considera apenas vendas vinculadas a cada lote. Vendas avulsas não diminuem o depósito.
4. A verificação de estoque e a venda usam a mesma transação, inclusive em requisições simultâneas.
5. A quantidade da compra não pode ficar abaixo do que já foi vendido; uma operação inválida não salva apenas parte das alterações.
6. O custo do lote para novas vendas inclui frete e despesas. Ao editar o custo da compra, os resultados das vendas vinculadas são recalculados.
7. A baixa de uma compra ou venda no financeiro também atualiza o registro de origem.
8. Saldo realizado considera somente lançamentos pagos/recebidos; pendências ficam separadas.
9. Acerto líquido = vendas ainda não pagas − adiantamentos em aberto − juros. Saldo positivo é pagamento ao cliente; negativo é valor a receber dele.
10. No acerto, os pagamentos brutos das vendas ficam como **Compensado**; apenas o valor líquido é lançado no caixa. Adiantamentos já registrados como saída continuam no histórico.
11. Repetir um acerto já concluído não cria outro lançamento. Vendas compensadas em acerto não podem ser editadas ou apagadas.
12. O saldo líquido geral é calculado por cliente, evitando compensar a dívida de um produtor com o saldo de outro.
13. Juros simples contam meses completos, incluindo o aniversário no último dia dos meses mais curtos.
14. Lotes com vendas e cadastros com movimentações não são excluídos por engano. Excluir uma compra sem vendas preserva suas provas.
15. Backup usa uma cópia consistente do banco; a restauração valida o arquivo e guarda uma cópia anterior.
16. Ranking de produtores não duplica compras quando um lote possui várias provas.

As correções de acerto valem para as novas confirmações. Lançamentos financeiros antigos já registrados não são reinterpretados automaticamente. O resultado do café usa a diferença entre preço de venda e custo do lote; o caixa mostra apenas os movimentos financeiros confirmados.

## Atualizar no Coolify

1. No sistema atual, abra **Backup** e baixe uma cópia completa.
2. Atualize os arquivos do código. Mantenha o volume persistente existente e seu conteúdo.
3. Use o `Dockerfile` da pasta raiz e a porta interna **8080**.
4. O destino do volume do banco continua sendo **/app/data**. Não apague nem recrie o volume existente para instalar esta atualização.
5. Faça o redeploy e recarregue o navegador. Os arquivos de visual e comportamento têm versão na URL para atualizar o cache.

O banco continua sendo `controle_cafe.sqlite3`. A inicialização acrescenta tabelas/colunas ausentes e índices; não recria os cadastros ou o estoque. Os bancos incluídos no ZIP são os mesmos do arquivo recebido, sem os dados fictícios usados nos testes.

A pasta `controle-cafe` foi mantida com o mesmo código atualizado para compatibilidade com instalações que usam esse diretório. A pasta raiz é o caminho recomendado; cada instalação deve continuar usando o mesmo banco e volume de antes.

## Rodar localmente

Requer Python 3.12 ou posterior.

```bash
pip install -r requirements.txt
python app.py
```

Acesse `http://localhost:8080`.

Variáveis opcionais:

- `PORT`: porta local, padrão `8080`.
- `DATA_DIR`: diretório persistente do banco. Padrão: pasta `data` ao lado de `app.py`.
- `SECRET_KEY`: chave da aplicação Flask.

O acesso direto da versão principal recebida foi mantido. Esta atualização não configura um novo login ou usuários.

## Verificação

```bash
python -m unittest discover -s tests -v
```

26 testes de regressão cobrem vendas parciais e simultâneas, edição/estorno de saldo, custos, juros, acertos, financeiro, backup, migração, telas, impressos e exportações. Os testes usam bancos temporários.

Também foram verificados os formulários no navegador e as telas em larguras de 360, 390, 768 e 1280 pixels, incluindo cadastro → compra por peso → venda parcial → adiantamento → acerto líquido.
