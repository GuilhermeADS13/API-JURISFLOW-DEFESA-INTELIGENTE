-- PR13 #B3: Base de legislacao curada (Melhoria 4 dos PDFs, parte de ROI maximo)
-- Tabela de leis/sumulas indexadas com vetor + tsvector pra busca hibrida.
-- O Gerador consulta antes de gerar e cita verbatim em vez de inferir
-- — elimina alucinacao de citacoes na origem, nao como pos-correcao.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.legislacao (
  id BIGSERIAL PRIMARY KEY,
  origem TEXT NOT NULL,             -- 'CLT', 'CF/88', 'CPC', 'CDC', 'CC', 'Sumula TST', 'Sumula STJ'
  numero TEXT NOT NULL,             -- 'art. 818', 'Sumula 338', 'art. 7, XVI'
  texto TEXT NOT NULL,
  area_juridica TEXT,
  embedding vector(384),
  texto_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('portuguese', coalesce(numero, '') || ' ' || coalesce(texto, ''))
  ) STORED,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(origem, numero)
);

CREATE INDEX IF NOT EXISTS idx_legislacao_embedding_hnsw
  ON public.legislacao USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_legislacao_texto_tsv
  ON public.legislacao USING GIN(texto_tsv);
CREATE INDEX IF NOT EXISTS idx_legislacao_area
  ON public.legislacao(area_juridica)
  WHERE area_juridica IS NOT NULL;

-- RLS: anon/authenticated podem LER (legislacao eh publica, sem dados sensiveis).
-- Backend usa service_role pra ingerir/atualizar.
ALTER TABLE public.legislacao ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_legislacao" ON public.legislacao
  FOR SELECT TO anon, authenticated
  USING (true);

COMMENT ON TABLE public.legislacao IS
  'Base de leis (CLT, CF, CPC, CDC, CC) e sumulas (TST, STJ) curadas. Consulta hibrida (vetorial + lexical) injetada no SYSTEM do Gerador via novo node n8n. Reduz alucinacao de citacoes ao prover artigos verbatim em vez de inferidos.';
