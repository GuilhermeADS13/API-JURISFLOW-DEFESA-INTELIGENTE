-- Policies basicas pras 5 tabelas com RLS habilitado mas sem nenhuma
-- policy — detectado pelo advisor security.
--
-- IMPORTANTE: o backend (FastAPI) acessa via service_role que ja faz
-- bypass automatico de TODA RLS. Essas policies sao DEFESA EM
-- PROFUNDIDADE: se algum dia algum codigo usar anon/authenticated
-- diretamente contra o PostgREST, ele so consegue acessar suas
-- proprias linhas. Sem essas policies, anon/authenticated nao acessa
-- nada (RLS sem policy = nega tudo) — ate isso seria seguro, mas
-- agora fica documentado e flexivel.
--
-- Modelo: owner = auth.uid()::text comparado com usuario_id (text).
-- contestacoes_exemplares: leitura publica autenticada (RAG precisa
-- consultar entre usuarios). configuracoes: nega tudo, so service_role.

-- ─────────── contestacoes ────────────────────────────────────────
CREATE POLICY "owner_select" ON public.contestacoes
  FOR SELECT TO authenticated
  USING (auth.uid()::text = usuario_id);

CREATE POLICY "owner_insert" ON public.contestacoes
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid()::text = usuario_id);

CREATE POLICY "owner_update" ON public.contestacoes
  FOR UPDATE TO authenticated
  USING (auth.uid()::text = usuario_id)
  WITH CHECK (auth.uid()::text = usuario_id);

CREATE POLICY "owner_delete" ON public.contestacoes
  FOR DELETE TO authenticated
  USING (auth.uid()::text = usuario_id);

-- ─────────── usuarios ────────────────────────────────────────────
CREATE POLICY "self_select" ON public.usuarios
  FOR SELECT TO authenticated
  USING (auth.uid()::text = id::text);

CREATE POLICY "self_update" ON public.usuarios
  FOR UPDATE TO authenticated
  USING (auth.uid()::text = id::text)
  WITH CHECK (auth.uid()::text = id::text);

-- ─────────── usuarios_sessoes ────────────────────────────────────
CREATE POLICY "owner_select" ON public.usuarios_sessoes
  FOR SELECT TO authenticated
  USING (auth.uid()::text = usuario_id::text);

CREATE POLICY "owner_delete" ON public.usuarios_sessoes
  FOR DELETE TO authenticated
  USING (auth.uid()::text = usuario_id::text);

-- ─────────── contestacoes_exemplares (RAG read-only) ─────────────
CREATE POLICY "authenticated_read_exemplares" ON public.contestacoes_exemplares
  FOR SELECT TO authenticated
  USING (true);

-- ─────────── configuracoes (admin/service_role only) ─────────────
-- Sem policy explicita pra anon/authenticated = bloqueado.
-- service_role bypassa RLS automaticamente, mantem acesso.
