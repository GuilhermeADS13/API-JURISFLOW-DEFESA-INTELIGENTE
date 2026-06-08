-- PR13 #B1: Metadados juridicos estruturados (Melhoria 2 dos PDFs)
-- Adiciona area_juridica canonica (5 valores) + resultado (procedente/improcedente/parcial/em_andamento).
-- area_juridica permite filtrar antes da busca vetorial quando expandir alem de trabalhista.
-- resultado retroalimenta o RAG: futuramente pode-se filtrar "so exemplares que GANHARAM".

ALTER TABLE public.contestacoes
  ADD COLUMN IF NOT EXISTS area_juridica TEXT,
  ADD COLUMN IF NOT EXISTS resultado TEXT
    CHECK (resultado IN ('procedente', 'improcedente', 'parcial', 'em_andamento') OR resultado IS NULL);

CREATE INDEX IF NOT EXISTS idx_contestacoes_area_juridica
  ON public.contestacoes(area_juridica)
  WHERE area_juridica IS NOT NULL;

COMMENT ON COLUMN public.contestacoes.area_juridica IS
  'Area juridica canonica derivada de tipo_acao: trabalhista|consumidor|bancario|previdenciario|civel. Classificacao via _classificar_area_juridica() no backend, conservador (None se nao casar).';

COMMENT ON COLUMN public.contestacoes.resultado IS
  'Desfecho da contestacao: procedente|improcedente|parcial|em_andamento. Preenchido manualmente pelo advogado apos sentenca. Permite filtrar exemplares vitoriosos no RAG.';
