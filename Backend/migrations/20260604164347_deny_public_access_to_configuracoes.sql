-- Fecha o lint 'rls_enabled_no_policy' pra public.configuracoes mantendo
-- o efeito desejado: anon/authenticated nao acessa nada. service_role
-- bypassa RLS automaticamente, entao o backend continua funcionando.
--
-- USING (false) garante que toda query SELECT/UPDATE/DELETE retorna 0
-- linhas pra roles publicos. WITH CHECK (false) bloqueia INSERTs.

CREATE POLICY "deny_all_public" ON public.configuracoes
  FOR ALL TO anon, authenticated
  USING (false)
  WITH CHECK (false);
