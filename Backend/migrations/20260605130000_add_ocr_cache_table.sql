-- PR13 #B2: Cache de OCR (Melhoria 6 dos PDFs)
-- Evita reprocessar Tesseract no mesmo PDF (5-10s/pagina, ate 2min em 15 pags).
-- Key = SHA-256 do PDF bytes; valor = texto extraido. Sem TTL — OCR de um PDF nao muda.
-- ultimo_uso_em permite cleanup posterior (cron) se a tabela crescer demais.

CREATE TABLE IF NOT EXISTS public.ocr_cache (
  file_hash TEXT PRIMARY KEY,
  texto_extraido TEXT NOT NULL,
  paginas_processadas INT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ultimo_uso_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ocr_cache_ultimo_uso
  ON public.ocr_cache(ultimo_uso_em);

-- RLS: nega tudo pra anon/authenticated. service_role bypassa (backend usa essa).
-- Mesmo padrao da public.configuracoes.
ALTER TABLE public.ocr_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "deny_all_public" ON public.ocr_cache
  FOR ALL TO anon, authenticated
  USING (false)
  WITH CHECK (false);

COMMENT ON TABLE public.ocr_cache IS
  'Cache de texto extraido via Tesseract OCR indexado por SHA-256 do PDF original. Reduz reprocessamento de 30-120s para <1s em reuploads do mesmo arquivo.';
