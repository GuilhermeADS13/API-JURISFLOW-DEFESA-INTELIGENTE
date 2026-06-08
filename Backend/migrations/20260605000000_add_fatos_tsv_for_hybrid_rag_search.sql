-- PR12 #4 Busca Hibrida RAG (BM25 lexical + vetorial)
-- Adiciona coluna tsvector gerada automaticamente a partir de fatos + pedido_autor,
-- com configuracao 'portuguese' do Postgres (suporta stemming + stopwords).
-- O GIN index acelera lookup ts_rank_cd para milhares de linhas.
--
-- A coluna eh GENERATED ALWAYS AS ... STORED: Postgres recalcula automaticamente
-- sempre que fatos ou pedido_autor mudam, sem precisar de trigger.

ALTER TABLE public.contestacoes
  ADD COLUMN IF NOT EXISTS fatos_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', coalesce(fatos, '') || ' ' || coalesce(pedido_autor, ''))
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_contestacoes_fatos_tsv
  ON public.contestacoes USING GIN(fatos_tsv);

COMMENT ON COLUMN public.contestacoes.fatos_tsv IS
  'tsvector gerado automaticamente de (fatos || pedido_autor) com dicionario portuguese. Usado pela busca hibrida RAG (BM25 lexical) em complemento ao fatos_embedding (vetorial pgvector).';
