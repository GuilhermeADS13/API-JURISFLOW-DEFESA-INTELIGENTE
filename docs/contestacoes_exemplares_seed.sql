-- Seed inicial de contestacoes exemplares para o few-shot do agente Claude.
-- Esses exemplos foram selecionados pelo escritorio como representativos
-- de alta qualidade. Popule com minutas reais aprovadas pelo advogado.
--
-- Como aplicar:
--   psql $DATABASE_URL -f contestacoes_exemplares_seed.sql
--
-- Ou via endpoint admin:
--   POST /api/admin/exemplares  (requer ADMIN_EMAILS no .env)

INSERT INTO contestacoes_exemplares (tipo_acao, tese_central, fundamentos_resumo, nota_qualidade)
VALUES (
  'Direito do Consumidor',
  'Improcedencia total dos pedidos autorais por ausencia de vicio do produto e inexistencia de nexo causal para configurar dano moral indenizavel.',
  'Art. 14 do CDC — responsabilidade pelo fato do produto exige comprovacao de defeito, dano e nexo causal.
Art. 6o, VIII, CDC — inversao do onus da prova e excepcao, nao regra; requer verossimilhanca ou hipossuficiencia tecnicamente demonstrada.
Laudo tecnico atestando ausencia de defeito deve ser juntado como prova documental (art. 434 CPC).
Dano moral: para configuracao, exige-se efetivo abalo a honra, imagem ou dignidade — mero dissabor ou aborrecimento cotidiano nao e indenizavel (STJ, posicao reiterada).
Pedido: improcedencia total, condenacao do autor em honorarios (art. 85 CPC).',
  9
),
(
  'Rescisao Contratual',
  'Contestacao por inexistencia de inadimplemento contratual imputavel ao reu; eventuais atrasos decorrem de forca maior e caso fortuito, afastando a responsabilidade.',
  'Art. 393 CC — o devedor nao responde pelos prejuizos resultantes de caso fortuito ou forca maior.
Art. 476 CC — exceptio non adimpleti contractus: se o autor nao cumpriu previamente sua obrigacao, nao pode exigir o cumprimento da contraparte.
Clausula contratual de tolerancia (verificar instrumento): atrasos ate X dias nao configuram inadimplemento.
Prova documental: registros de comunicacao, atas de reuniao e notificacoes extrajudiciais demonstram boa-fe do reu.
Pedido: improcedencia; subsidiariamente, reducao da clausula penal ao valor do dano efetivo (art. 413 CC).',
  8
),
(
  'Trabalhista — Verbas Rescisorias',
  'Improcedencia dos pedidos de horas extras e adicional noturno por inexistencia de jornada extraordinaria habitual, comprovada por controles de ponto fidedignos.',
  'Art. 74, par. 2o, CLT — empregador com mais de 20 empregados e obrigado a manter registro de ponto; os cartoes juntados refletem a jornada real.
Sumula 338, TST — os cartoes de ponto apresentados pelo reclamado gozam de presuncao relativa de veracidade, cabendo ao reclamante impugna-los especificamente.
Horas extras: para configuracao exige-se superacao do limite do art. 58 CLT (tolerancia de 5 minutos, ate 10 minutos diarios — Sumula 366 TST).
Adicional noturno: apenas devido para jornada entre 22h e 5h (art. 73 CLT); horario do reclamante nao se enquadra.
Pedido: improcedencia; caso deferidas horas extras, aplicar integracoes apenas sobre os reflexos legalmente previstos.',
  9
);
