-- Revoga EXECUTE da funcao rls_auto_enable() dos roles publicos.
-- Detectado pelo Supabase advisor (security) — funcao SECURITY DEFINER
-- exposta via REST permite privilege escalation se usada por
-- anon/authenticated. Continua acessivel via service_role e postgres.

REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon;
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
