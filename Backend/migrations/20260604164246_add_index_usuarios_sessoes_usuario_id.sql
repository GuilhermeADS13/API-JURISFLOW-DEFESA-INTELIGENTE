-- FK 'usuarios_sessoes_usuario_id_fkey' nao tinha indice cobrindo.
-- Detectado pelo Supabase advisor (performance — unindexed_foreign_keys).
-- Toda query JOIN/CASCADE entre usuarios <-> usuarios_sessoes fazia
-- seq scan; indice corrige isso.

CREATE INDEX IF NOT EXISTS idx_usuarios_sessoes_usuario_id
  ON public.usuarios_sessoes(usuario_id);
