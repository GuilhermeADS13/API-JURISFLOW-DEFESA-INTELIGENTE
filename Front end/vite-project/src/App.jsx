// Componente raiz do frontend: autenticacao, envio de casos, dashboard e suporte.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Modal } from "react-bootstrap";

import AppNavbar from "./components/AppNavbar";
import AuthModal from "./components/AuthModal";
import HeroSection from "./components/HeroSection";
import StatsSection from "./components/StatsSection";
import MainPanelSection from "./components/MainPanelSection";
import DashboardSection from "./components/DashboardSection";
import SupportSection from "./components/SupportSection";
import AppFooter from "./components/AppFooter";
import RevisaoHumanaModal from "./components/RevisaoHumanaModal";
import {
  AGENT_API_URL,
  DASHBOARD_SUMMARY_API_URL,
  PETICAO_API_URL,
  SUPPORT_CONTACT_API_URL,
  confirmarExtracaoUrl,
  patchMinutaUrl,
} from "./config/api";
import { getSupabaseClient, isSupabaseConfigured } from "./lib/supabaseClient";
import { base64ToBlob, normalizeFileName, readFileAsBase64, validateFile } from "./utils/files";
import { escapeHtml } from "./utils/html";
import {
  clearSession,
  persistDraft,
  persistSession,
  readDraftFromStorage,
  readStoredSession,
} from "./utils/storage";
import {
  getApiErrorMessage,
  getPasswordChecks,
  isValidEmail,
  isValidNumeroProcesso,
  normalizeEmail,
  validateAuthField,
} from "./utils/validators";

function readValidSession() {
  const session = readStoredSession();
  if (!session?.email) return null;
  const normalizedEmail = normalizeEmail(session.email);
  if (!isValidEmail(normalizedEmail)) {
    clearSession();
    return null;
  }

  return {
    id: session.id || "",
    name: session.name || "Conta",
    email: normalizedEmail,
  };
}

function mapSupabaseUser(user, fallbackName = "Conta") {
  if (!user?.email) return null;
  const normalizedEmail = normalizeEmail(user.email);
  if (!isValidEmail(normalizedEmail)) return null;

  const metadataName =
    typeof user.user_metadata?.name === "string" ? user.user_metadata.name.trim() : "";

  const inferredName = normalizedEmail.split("@")[0] || "Conta";

  return {
    id: user.id || "",
    name: metadataName || fallbackName || inferredName,
    email: normalizedEmail,
  };
}

function getSupabaseAuthErrorMessage(error, fallbackMessage) {
  const message = (error?.message || "").toLowerCase();

  if (message.includes("invalid login credentials")) {
    return "Não encontramos uma conta com esse e-mail e senha.";
  }

  if (message.includes("email not confirmed")) {
    return "Confirme seu e-mail antes de entrar.";
  }

  if (message.includes("user already registered")) {
    return "Ja existe uma conta com este e-mail.";
  }

  if (message.includes("password should be at least")) {
    return "A senha precisa ter pelo menos 6 caracteres.";
  }

  return fallbackMessage;
}

// PR5 Observabilidade: extrai as secoes da minuta editada no editor ao vivo.
// O liveDraft tem cabecalhos do tipo "TESE CENTRAL", "MERITO", "FUNDAMENTOS",
// "PEDIDOS" inseridos por handleSubmitPeticao. Este parser converte de volta
// num dict que o backend grava em `minuta_json_editada`.
function parseMinutaSecoes(texto) {
  if (!texto || typeof texto !== "string") return {};
  const mapaCabecalhos = {
    "TESE CENTRAL": "tese_central",
    PRELIMINARES: "preliminares",
    "MERITO": "merito",
    "MÉRITO": "merito",
    "IMPUGNACAO DOS PEDIDOS": "impugnacao_pedidos",
    "IMPUGNAÇÃO DOS PEDIDOS": "impugnacao_pedidos",
    FUNDAMENTOS: "fundamentos",
    PEDIDOS: "pedidos",
    OBSERVACOES: "observacoes",
    "OBSERVAÇÕES": "observacoes",
  };
  const linhas = texto.split("\n");
  const out = {};
  let secaoAtual = null;
  let buffer = [];
  const flush = () => {
    if (secaoAtual && buffer.length > 0) {
      out[secaoAtual] = buffer.join("\n").trim();
    }
    buffer = [];
  };
  for (const linha of linhas) {
    const trimmed = linha.trim();
    const upper = trimmed.toUpperCase();
    if (mapaCabecalhos[upper]) {
      flush();
      secaoAtual = mapaCabecalhos[upper];
      continue;
    }
    if (secaoAtual) buffer.push(linha);
  }
  flush();
  return out;
}

function buildEmptyDashboardCards() {
  return [
    { label: "Total de casos", value: "0" },
    { label: "Concluidas", value: "0" },
    { label: "Em analise", value: "0" },
    { label: "Com pendencia", value: "0" },
  ];
}

function getDashboardRefreshIntervalMs() {
  const rawInterval = Number(import.meta.env.VITE_DASHBOARD_REFRESH_MS || 30000);
  if (!Number.isFinite(rawInterval)) return 30000;
  return Math.max(30000, rawInterval);
}

// Tempo medio medido em producao (Sonnet 4.6, pipeline completo n8n).
// Ultima medicao real: gerador sozinho leva ~7min em peticoes longas.
// Cap a barra em 95% apos esse limite e troca a copy — feedback ao usuario
// de que ainda esta rodando, sem barra batendo 100% e ficando travada.
const TOTAL_ESTIMADO_S = 420;
const TIMEOUT_HARD_S = 600;

function ProgressoGeracao({ ativo, segundos }) {
  const passouEstimado = segundos > TOTAL_ESTIMADO_S;
  const pct = passouEstimado
    ? 95
    : Math.min(95, Math.round((segundos / TOTAL_ESTIMADO_S) * 100));
  const mm = Math.floor(segundos / 60);
  const ss = String(segundos % 60).padStart(2, "0");
  return (
    <Modal
      show={ativo}
      centered
      backdrop="static"
      keyboard={false}
      dialogClassName="progresso-modal"
    >
      <Modal.Body className="text-center px-4 py-4">
        <h5 className="progresso-titulo mb-3">Preparando peça…</h5>
        <div className="progresso-bar-wrapper mb-3">
          <div
            className="progresso-bar-fill"
            style={{ width: `${pct}%` }}
          />
          <span className="progresso-bar-pct">{pct}%</span>
        </div>
        <div className="progresso-timer mb-2">
          {mm}:{ss}
        </div>
        <div className="progresso-aviso d-block">
          {passouEstimado ? (
            <>
              Finalizando — pode levar até{" "}
              <strong>{Math.floor(TIMEOUT_HARD_S / 60)} min</strong> em casos
              longos.{" "}
              <strong className="progresso-aviso-forte">
                Não feche a janela.
              </strong>
            </>
          ) : (
            <>
              Tempo médio: <strong>5 min</strong>.{" "}
              <strong className="progresso-aviso-forte">
                Não feche a janela.
              </strong>
            </>
          )}
        </div>
      </Modal.Body>
    </Modal>
  );
}

export default function App() {
  // `draftSeed`: snapshot inicial do rascunho recuperado do navegador.
  const [draftSeed] = useState(readDraftFromStorage);
  // `currentPage`: controla navegacao entre Inicio, Painel, Dashboard e Suporte.
  const [currentPage, setCurrentPage] = useState("inicio");

  // Estados de UI global (modais, loading e ultimo caso gerado).
  const [showResultModal, setShowResultModal] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  // Progresso visivel ao usuario enquanto o pipeline IA roda (~5 min).
  // Etapas com tempos esperados baseados no timing real do workflow n8n:
  //   Extrator: ~45-50s | RAG: ~2s | Gerador: ~4-5min | Self-Correction: ~10s
  // Single source of truth = segundos; etapa eh derivada via etapaAtualParaSegundos.
  const [progresso, setProgresso] = useState({ ativo: false, segundos: 0 });
  const [lastCaseId, setLastCaseId] = useState(null);
  // `authUser`: perfil autenticado em memoria + storage local seguro (sem token).
  const [authUser, setAuthUser] = useState(readValidSession);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({
    name: "",
    email: "",
    password: "",
  });
  const [authTouched, setAuthTouched] = useState({});
  const [authErrors, setAuthErrors] = useState({});
  const [authFeedback, setAuthFeedback] = useState(null);
  const [authLoading, setAuthLoading] = useState(false);
  // `pendingConfirmEmail`: email aguardando confirmacao apos signUp bem-sucedido.
  // Quando preenchido, o modal exibe a tela de "verifique seu e-mail".
  const [pendingConfirmEmail, setPendingConfirmEmail] = useState(null);
  // Controla throttle do botao de reenvio: timestamp da ultima tentativa.
  const [resendCooldownUntil, setResendCooldownUntil] = useState(0);
  const [resendLoading, setResendLoading] = useState(false);

  const [form, setForm] = useState(() => ({
    processo: "",
    autor: "",
    reu: "",
    tipoAcao: "",
    subtipoAcao: "",
    fatos: "",
    pedidoAutor: "",
    ...(draftSeed.form || {}),
  }));

  const [history, setHistory] = useState([]);
  const [dashboardCards, setDashboardCards] = useState(buildEmptyDashboardCards);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  // `uploadedFile`: arquivo base selecionado pelo usuario para envio ao backend.
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadError, setUploadError] = useState("");
  // Guia Tecnico v2: modo de entrada do painel.
  // 'manual'  = formulario tradicional (envia para /gerar-contestacao)
  // 'peticao' = upload da peticao inicial (envia para /contestar-por-peticao)
  const [modo, setModo] = useState(draftSeed.form?.modo || "manual");
  const [peticaoFile, setPeticaoFile] = useState(null);
  const [peticaoError, setPeticaoError] = useState("");
  const [modeloBaseFile, setModeloBaseFile] = useState(null);
  const [modeloBaseError, setModeloBaseError] = useState("");
  const [tipoAcaoHint, setTipoAcaoHint] = useState("");
  const [pontosContestante, setPontosContestante] = useState("");
  // PR5 Multi-documentos: lista de anexos opcionais (alem da peticao principal).
  const [anexosFiles, setAnexosFiles] = useState([]);
  const [anexosError, setAnexosError] = useState("");
  // PR5 HiL: modal de revisao humana quando confianca da IA < 0.7.
  const [showRevisaoModal, setShowRevisaoModal] = useState(false);
  const [revisaoData, setRevisaoData] = useState(null); // { contestacao_id, dados_extraidos, dados_confianca, modelo_base_base64 }
  const [revisaoLoading, setRevisaoLoading] = useState(false);
  const [revisaoError, setRevisaoError] = useState("");
  const [formErrors, setFormErrors] = useState({});
  const [draftInfo, setDraftInfo] = useState(() => draftSeed.info);
  const [feedback, setFeedback] = useState(null);
  const [automationStatus, setAutomationStatus] = useState({
    webhook: 100,
    ia: 86,
    validacao: 92,
  });

  const [liveDraft, setLiveDraft] = useState("");
  const [liveDraftTouched, setLiveDraftTouched] = useState(false);
  const [iaResult, setIaResult] = useState(null);
  // Estados dedicados ao fluxo de suporte/reclamacoes.
  const [supportForm, setSupportForm] = useState(() => ({
    nome: authUser?.name || "",
    email: authUser?.email || "",
    categoria: "",
    processo: "",
    assunto: "",
    mensagem: "",
  }));
  const [supportErrors, setSupportErrors] = useState({});
  const [supportFeedback, setSupportFeedback] = useState(null);
  const [supportLoading, setSupportLoading] = useState(false);

  /**
   * Porcentagem dos campos obrigatorios preenchidos (PR6 P3.2).
   * Conta apenas processo, autor, reu, tipoAcao, fatos, pedidoAutor + arquivo
   * base. Subtipo nao entra (e opcional). Antes contava todo Object.values do
   * form, dando 100% mesmo sem preencher tudo que importa.
   */
  const completion = useMemo(() => {
    const requiredTextFields = [
      form.processo,
      form.autor,
      form.reu,
      form.tipoAcao,
      form.fatos,
      form.pedidoAutor,
    ];
    const filled = requiredTextFields.filter((v) => (v || "").trim().length > 0).length;
    const total = requiredTextFields.length + 1; // +1 para o arquivo base
    const completedFile = uploadedFile ? 1 : 0;
    return Math.round(((filled + completedFile) / total) * 100);
  }, [form, uploadedFile]);

  const authPasswordChecks = useMemo(
    () => getPasswordChecks(authForm.password),
    [authForm.password],
  );
  const dashboardRefreshIntervalMs = useMemo(getDashboardRefreshIntervalMs, []);

  const generatedPreviewParagraphs = useMemo(() => {
    const autor = form.autor.trim() || "a parte autora";
    const tipoAcao = form.tipoAcao.trim() || "ramo jurídico ainda não definido";
    const pedidoAutor = form.pedidoAutor.trim() || "os pedidos formulados";
    const observacoes = form.fatos.trim();

    return [
      `No âmbito de ${tipoAcao.toLowerCase()}, defesa apresentada em face dos pedidos de ${autor} e destaca ausência de pressupostos para procedência do pedido inicial.`,
      `O agente recomenda reforço argumentativo com base em ${pedidoAutor.toLowerCase()}, mantendo linguagem jurídica formal e estrutura definida pelo escritório.`,
      observacoes
        ? `Observações relevantes para a equipe: ${observacoes}`
        : "O documento segue para revisão humana antes da exportação final.",
    ];
  }, [form]);

  const generatedDraftText = useMemo(
    () => generatedPreviewParagraphs.join("\n\n"),
    [generatedPreviewParagraphs],
  );

  useEffect(() => {
    if (!liveDraftTouched) {
      setLiveDraft(generatedDraftText);
    }
  }, [generatedDraftText, liveDraftTouched]);

  // PR5 Observabilidade: auto-save da minuta editada (debounce 3s).
  // Salvamos em `minuta_json_editada` para futuro fine-tuning vs minuta_original.
  useEffect(() => {
    if (!lastCaseId || !liveDraftTouched) return;
    if (!liveDraft || liveDraft.trim().length < 50) return;
    const timer = setTimeout(async () => {
      try {
        const accessToken = await getSupabaseAccessToken();
        // Parse simples por secoes (TESE CENTRAL, MERITO, etc.) que o
        // handleSubmitPeticao gerou ao popular o liveDraft.
        const secoes = parseMinutaSecoes(liveDraft);
        if (Object.keys(secoes).length === 0) return;
        await fetch(patchMinutaUrl(lastCaseId), {
          method: "PATCH",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify(secoes),
        });
      } catch {
        // Silent — auto-save nao deve quebrar a UX. Erros caem em logs do backend.
      }
    }, 3000);
    return () => clearTimeout(timer);
  }, [liveDraft, liveDraftTouched, lastCaseId]);

  useEffect(() => {
    setSupportForm((prev) => ({
      ...prev,
      nome: prev.nome || authUser?.name || "",
      email: prev.email || authUser?.email || "",
    }));
  }, [authUser]);

  // Timer da barra de progresso: avanca 1s a cada segundo enquanto ativo.
  useEffect(() => {
    if (!progresso.ativo) return undefined;
    const interval = setInterval(() => {
      setProgresso((p) => {
        if (!p.ativo) return p;
        return { ...p, segundos: p.segundos + 1 };
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [progresso.ativo]);

  // Quando loading sai de true para false, desliga a barra de progresso.
  useEffect(() => {
    if (!loading && progresso.ativo) {
      setProgresso((p) => ({ ...p, ativo: false }));
    }
  }, [loading, progresso.ativo]);

  useEffect(() => {
    let isActive = true;

    const syncSession = async () => {
      if (!isSupabaseConfigured) {
        if (!isActive) return;
        clearSession();
        setAuthUser(null);
        return;
      }

      try {
        const supabase = getSupabaseClient();
        const { data, error } = await supabase.auth.getUser();
        if (!isActive) return;

        if (error || !data?.user) {
          clearSession();
          setAuthUser(null);
          return;
        }

        const session = mapSupabaseUser(data.user);
        if (!session) return;
        persistSession(session);
        setAuthUser(session);
      } catch {
        if (!isActive) return;
        clearSession();
        setAuthUser(null);
      }
    };

    syncSession();

    if (!isSupabaseConfigured) {
      return () => {
        isActive = false;
      };
    }

    const supabase = getSupabaseClient();
    const { data: authState } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session?.user) {
        clearSession();
        setAuthUser(null);
        return;
      }

      const profile = mapSupabaseUser(session.user);
      if (!profile) {
        clearSession();
        setAuthUser(null);
        return;
      }

      persistSession(profile);
      setAuthUser(profile);
    });

    return () => {
      isActive = false;
      authState.subscription.unsubscribe();
    };
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setFormErrors((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const handleLiveDraftChange = (event) => {
    setLiveDraftTouched(true);
    setLiveDraft(event.target.value);
  };

  const handleResetLiveDraft = () => {
    setLiveDraft(generatedDraftText);
    setLiveDraftTouched(false);
  };

  const openAuthModal = (mode = "login") => {
    setAuthMode(mode);
    setAuthTouched({});
    setAuthErrors({});
    setAuthFeedback(null);
    setAuthLoading(false);
    setAuthForm({
      name: "",
      email: "",
      password: "",
    });
    setShowAuthModal(true);
  };

  const closeAuthModal = () => {
    setShowAuthModal(false);
    setAuthTouched({});
    setAuthErrors({});
    setAuthFeedback(null);
    setAuthLoading(false);
    setPendingConfirmEmail(null);
    setResendCooldownUntil(0);
  };

  const handleResendConfirmation = async () => {
    if (!pendingConfirmEmail || resendLoading) return;
    const now = Date.now();
    if (now < resendCooldownUntil) return;

    setResendLoading(true);
    try {
      const supabase = getSupabaseClient();
      const { error } = await supabase.auth.resend({
        type: "signup",
        email: pendingConfirmEmail,
      });
      if (error) {
        setAuthFeedback({
          variant: "danger",
          text: "Não foi possível reenviar o e-mail. Tente novamente em instantes.",
        });
      } else {
        setResendCooldownUntil(Date.now() + 60_000);
        setAuthFeedback({
          variant: "success",
          text: "E-mail de confirmacao reenviado. Verifique sua caixa de entrada e spam.",
        });
      }
    } catch {
      setAuthFeedback({
        variant: "danger",
        text: "Erro ao tentar reenviar o e-mail de confirmacao.",
      });
    } finally {
      setResendLoading(false);
    }
  };

  const handleChangeConfirmEmail = () => {
    setPendingConfirmEmail(null);
    setResendCooldownUntil(0);
    setAuthFeedback(null);
    setAuthMode("signup");
    setAuthForm((prev) => ({ ...prev, email: "" }));
  };

  const handleAuthModeChange = (mode) => {
    setAuthMode(mode);
    setPendingConfirmEmail(null);
    setResendCooldownUntil(0);
    setAuthTouched({});
    setAuthErrors({});
    setAuthFeedback(null);
    setAuthLoading(false);
    setAuthForm({
      name: "",
      email: "",
      password: "",
    });
  };

  const handleAuthFieldChange = (event) => {
    const { name, value } = event.target;
    setAuthForm((prev) => ({ ...prev, [name]: value }));
    setAuthErrors((prev) => {
      const next = { ...prev };
      if (!authTouched[name]) {
        delete next[name];
        return next;
      }

      const fieldError = validateAuthField(name, value, authMode);
      if (fieldError) {
        next[name] = fieldError;
      } else {
        delete next[name];
      }

      return next;
    });
  };

  const handleAuthFieldBlur = (event) => {
    const { name, value } = event.target;
    setAuthTouched((prev) => ({ ...prev, [name]: true }));
    setAuthErrors((prev) => {
      const next = { ...prev };
      const fieldError = validateAuthField(name, value, authMode);
      if (fieldError) {
        next[name] = fieldError;
      } else {
        delete next[name];
      }
      return next;
    });
  };

  const validateAuthForm = () => {
    const fields = authMode === "signup" ? ["name", "email", "password"] : ["email", "password"];
    return fields.reduce((accumulator, fieldName) => {
      const fieldError = validateAuthField(fieldName, authForm[fieldName], authMode);
      if (fieldError) {
        accumulator[fieldName] = fieldError;
      }
      return accumulator;
    }, {});
  };

  const handleAuthSubmit = async (event) => {
    // Faz cadastro/login diretamente no servidor de autenticacao do Supabase.
    event.preventDefault();
    if (authLoading) return;

    setAuthTouched(
      authMode === "signup"
        ? { name: true, email: true, password: true }
        : { email: true, password: true },
    );

    const errors = validateAuthForm();

    if (Object.keys(errors).length) {
      setAuthErrors(errors);
      setAuthFeedback({
        variant: "danger",
        text: "Revise os dados de acesso antes de continuar.",
      });
      return;
    }

    setAuthLoading(true);
    setAuthFeedback(null);

    try {
      if (!isSupabaseConfigured) {
        setAuthFeedback({
          variant: "danger",
          text: "Supabase não configurado no frontend. Verifique o .env.local.",
        });
        return;
      }

      const supabase = getSupabaseClient();
      const normalizedEmail = normalizeEmail(authForm.email);

      if (authMode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email: normalizedEmail,
          password: authForm.password,
          options: {
            data: {
              name: authForm.name.trim(),
            },
          },
        });

        if (error) {
          if ((error.message || "").toLowerCase().includes("already registered")) {
            setAuthErrors({ email: "Já existe uma conta com este e-mail." });
          }

          setAuthFeedback({
            variant: "danger",
            text: getSupabaseAuthErrorMessage(error, "Não foi possível criar sua conta agora."),
          });
          return;
        }

        // Se confirmacao de e-mail estiver ativa no projeto, pode nao existir sessao imediata.
        if (!data?.session) {
          clearSession();
          setAuthUser(null);
          // Mantem o modal aberto mostrando a tela de "verifique seu e-mail".
          setPendingConfirmEmail(normalizedEmail);
          setAuthFeedback(null);
          return;
        }

        setShowAuthModal(false);

        const session = mapSupabaseUser(data.user, authForm.name.trim() || "Conta");
        if (!session) {
          setFeedback({
            variant: "warning",
            text: "Conta criada, mas não foi possível carregar os dados da sessão.",
          });
          return;
        }

        persistSession(session);
        setAuthUser(session);
        setFeedback({
          variant: "success",
          text: `Conta criada com sucesso. Bem-vindo ao workspace, ${session.name}.`,
        });
        return;
      }

      const { data, error } = await supabase.auth.signInWithPassword({
        email: normalizedEmail,
        password: authForm.password,
      });

      if (error) {
        const lowerMessage = (error.message || "").toLowerCase();

        if (lowerMessage.includes("invalid login credentials")) {
          setAuthErrors({
            email: "Verifique o e-mail informado.",
            password: "Verifique a senha informada.",
          });
        }

        setAuthFeedback({
          variant: "danger",
          text: getSupabaseAuthErrorMessage(error, "Não encontramos uma conta com esse e-mail e senha."),
        });
        return;
      }

      const session = mapSupabaseUser(data.user);
      if (!session) {
        setAuthFeedback({
          variant: "danger",
          text: "Não foi possível carregar os dados da conta.",
        });
        return;
      }

      persistSession(session);
      setAuthUser(session);
      setPendingConfirmEmail(null);
      setResendCooldownUntil(0);
      setShowAuthModal(false);
      setFeedback({
        variant: "success",
        text: `Acesso liberado. Bem-vindo de volta, ${session.name}.`,
      });
    } catch {
      setAuthFeedback({
        variant: "danger",
        text: "Não foi possível conectar com o servidor do Supabase.",
      });
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    let remoteLogoutFailed = false;

    try {
      if (!isSupabaseConfigured) {
        remoteLogoutFailed = true;
      } else {
        const supabase = getSupabaseClient();
        const { error } = await supabase.auth.signOut();
        if (error) {
          remoteLogoutFailed = true;
        }
      }
    } catch {
      remoteLogoutFailed = true;
    }

    if (!isSupabaseConfigured) {
      clearSession();
      setAuthUser(null);
      setFeedback({
        variant: "warning",
        text: "Sessao local encerrada. Configure o Supabase para logout remoto.",
      });
      return;
    }

    clearSession();
    setAuthUser(null);
    setFeedback({
      variant: remoteLogoutFailed ? "warning" : "info",
      text: remoteLogoutFailed
        ? "Sessão local encerrada, mas não foi possível confirmar logout no Supabase."
        : "Sessão encerrada com sucesso.",
    });
  };

  const handleFileSelect = (file) => {
    const error = validateFile(file);
    if (error) {
      setUploadedFile(null);
      setUploadError(error);
      return;
    }

    setUploadedFile(file);
    setUploadError("");
    setFormErrors((prev) => {
      const next = { ...prev };
      delete next.upload;
      return next;
    });
  };

  const handleRemoveFile = () => {
    setUploadedFile(null);
    setUploadError("");
  };

  const handleModoChange = (novoModo) => {
    setModo(novoModo);
    setFeedback(null);
    setFormErrors({});
  };

  const handlePeticaoFileSelect = (file) => {
    const error = validateFile(file);
    if (error) {
      setPeticaoFile(null);
      setPeticaoError(error);
      return;
    }
    setPeticaoFile(file);
    setPeticaoError("");
  };

  const handleRemovePeticaoFile = () => {
    setPeticaoFile(null);
    setPeticaoError("");
  };

  const handleModeloBaseFileSelect = (file) => {
    // Modelo base aceita apenas .docx (mesma valida��o do backend).
    const nome = (file?.name || "").toLowerCase();
    if (!nome.endsWith(".docx")) {
      setModeloBaseFile(null);
      setModeloBaseError("Modelo base deve ser .docx.");
      return;
    }
    const error = validateFile(file);
    if (error) {
      setModeloBaseFile(null);
      setModeloBaseError(error);
      return;
    }
    setModeloBaseFile(file);
    setModeloBaseError("");
  };

  const handleRemoveModeloBaseFile = () => {
    setModeloBaseFile(null);
    setModeloBaseError("");
  };

  // PR5 Multi-documentos
  const handleAdicionarAnexo = (file) => {
    if (!file) return;
    const error = validateFile(file);
    if (error) {
      setAnexosError(error);
      return;
    }
    if (anexosFiles.length >= 5) {
      setAnexosError("Máximo de 5 anexos por petição.");
      return;
    }
    setAnexosFiles((prev) => [...prev, file]);
    setAnexosError("");
  };

  const handleRemoverAnexo = (index) => {
    setAnexosFiles((prev) => prev.filter((_, i) => i !== index));
    setAnexosError("");
  };

  const validateForm = () => {
    const errors = {};

    // No modo "peticao" so exigimos a peticao inicial; campos do form sao
    // preenchidos automaticamente apos a extracao do agente.
    if (modo === "peticao") {
      if (!peticaoFile) errors.peticao = "Anexe a petição inicial em PDF ou DOCX.";
      return errors;
    }

    if (!form.processo.trim()) errors.processo = "Informe o número do processo.";
    if (form.processo.trim() && !isValidNumeroProcesso(form.processo)) {
      errors.processo = "Use o formato 0001234-56.2026.8.00.0000.";
    }
    if (!form.autor.trim()) errors.autor = "Informe o autor da ação.";
    if (!form.reu.trim()) errors.reu = "Informe o réu (parte que você representa).";
    if (!form.tipoAcao.trim()) errors.tipoAcao = "Selecione o ramo do direito.";
    if (!form.fatos.trim()) errors.fatos = "Resuma os fatos narrados pelo autor.";
    if (!form.pedidoAutor.trim()) errors.pedidoAutor = "Informe os pedidos do autor.";
    if (!uploadedFile) errors.upload = "Anexe a peça base para continuar.";

    return errors;
  };

  const handleSaveDraft = () => {
    const savedAt = new Date().toLocaleString("pt-BR");
    const payload = {
      form: { ...form, modo },
      fileName: uploadedFile ? uploadedFile.name : null,
      savedAt,
    };

    try {
      persistDraft(payload);
      setDraftInfo(`Último rascunho salvo em ${savedAt}`);
      setFeedback({
        variant: "success",
        text: "Rascunho salvo com sucesso.",
      });
    } catch {
      setFeedback({
        variant: "danger",
        text: "Não foi possível salvar o rascunho no navegador.",
      });
    }
  };

  const getSupabaseAccessToken = useCallback(async () => {
    if (!isSupabaseConfigured) return null;

    try {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.getSession();
      if (error) return null;
      return data?.session?.access_token || null;
    } catch {
      return null;
    }
  }, []);

  const loadDashboardData = useCallback(
    async ({ silent = false } = {}) => {
      if (!authUser) {
        setHistory([]);
        setDashboardCards(buildEmptyDashboardCards());
        return;
      }

      if (!silent) {
        setDashboardLoading(true);
      }

      try {
        const accessToken = await getSupabaseAccessToken();
        const headers = { "Content-Type": "application/json" };
        if (accessToken) {
          headers.Authorization = `Bearer ${accessToken}`;
        }

        const response = await fetch(DASHBOARD_SUMMARY_API_URL, {
          method: "GET",
          credentials: "include",
          headers,
        });

        if (response.status === 401) {
          clearSession();
          setAuthUser(null);
          setHistory([]);
          setDashboardCards(buildEmptyDashboardCards());
          return;
        }

        if (!response.ok) {
          throw new Error(
            await getApiErrorMessage(
              response,
              "Não foi possível carregar histórico real do dashboard.",
            ),
          );
        }

        const data = await response.json().catch(() => ({}));
        const nextCards =
          Array.isArray(data?.cards) && data.cards.length > 0
            ? data.cards
            : buildEmptyDashboardCards();
        const nextHistory = Array.isArray(data?.history) ? data.history : [];

        setDashboardCards(nextCards);
        setHistory(nextHistory);
      } catch (error) {
        if (!silent) {
          setFeedback({
            variant: "warning",
            text:
              error instanceof Error
                ? error.message
                : "Não foi possível sincronizar o dashboard com o banco de dados.",
          });
        }
      } finally {
        if (!silent) {
          setDashboardLoading(false);
        }
      }
    },
    [authUser, getSupabaseAccessToken],
  );

  useEffect(() => {
    if (!authUser) {
      setHistory([]);
      setDashboardCards(buildEmptyDashboardCards());
      setDashboardLoading(false);
      return;
    }

    void loadDashboardData({ silent: true });
  }, [authUser, loadDashboardData]);

  useEffect(() => {
    if (!authUser || currentPage !== "dashboard") return undefined;

    let running = false;
    const syncDashboard = async () => {
      if (running) return;
      running = true;
      try {
        await loadDashboardData({ silent: true });
      } finally {
        running = false;
      }
    };

    const intervalId = window.setInterval(() => {
      void syncDashboard();
    }, dashboardRefreshIntervalMs);

    const handleFocus = () => {
      void syncDashboard();
    };

    window.addEventListener("focus", handleFocus);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
    };
  }, [authUser, currentPage, dashboardRefreshIntervalMs, loadDashboardData]);

  // Mantem formulario de suporte sincronizado com o usuario logado (quando existir).
  const handleSupportChange = (event) => {
    const { name, value } = event.target;
    setSupportForm((prev) => ({ ...prev, [name]: value }));
    setSupportErrors((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  // Aplica regras basicas de validacao antes de enviar ao backend de suporte.
  const validateSupportForm = () => {
    const errors = {};

    if (!supportForm.nome.trim()) {
      errors.nome = "Informe seu nome.";
    } else if (supportForm.nome.trim().length < 3) {
      errors.nome = "Use pelo menos 3 caracteres no nome.";
    }

    if (!supportForm.email.trim()) {
      errors.email = "Informe seu e-mail para retorno.";
    } else if (!isValidEmail(supportForm.email)) {
      errors.email = "Informe um e-mail válido.";
    }

    if (!supportForm.categoria.trim()) {
      errors.categoria = "Selecione a categoria da reclamação.";
    }

    if (supportForm.processo.trim() && !isValidNumeroProcesso(supportForm.processo)) {
      errors.processo = "Use o formato 0001234-56.2026.8.00.0000.";
    }

    if (!supportForm.assunto.trim()) {
      errors.assunto = "Informe o assunto da reclamação.";
    } else if (supportForm.assunto.trim().length < 4) {
      errors.assunto = "Use ao menos 4 caracteres no assunto.";
    }

    if (!supportForm.mensagem.trim()) {
      errors.mensagem = "Descreva a reclamação para o suporte.";
    } else if (supportForm.mensagem.trim().length < 15) {
      errors.mensagem = "Detalhe mais a reclamação (mínimo de 15 caracteres).";
    }

    return errors;
  };

  // Envia reclamacao para /api/suporte/contato e exibe protocolo retornado.
  const handleSupportSubmit = async (event) => {
    event.preventDefault();
    if (supportLoading) return;

    const errors = validateSupportForm();
    if (Object.keys(errors).length) {
      setSupportErrors(errors);
      setSupportFeedback({
        variant: "danger",
        text: "Revise os campos obrigatórios antes de enviar a reclamação.",
      });
      return;
    }

    setSupportLoading(true);
    setSupportFeedback(null);

    const payload = {
      name: supportForm.nome.trim(),
      email: normalizeEmail(supportForm.email),
      category: supportForm.categoria.trim(),
      processo: supportForm.processo.trim() || null,
      subject: supportForm.assunto.trim(),
      message: supportForm.mensagem.trim(),
    };

    try {
      const accessToken = await getSupabaseAccessToken();
      const requestHeaders = {
        "Content-Type": "application/json",
      };
      if (accessToken) {
        requestHeaders.Authorization = `Bearer ${accessToken}`;
      }

      const response = await fetch(SUPPORT_CONTACT_API_URL, {
        method: "POST",
        credentials: "include",
        headers: requestHeaders,
        body: JSON.stringify(payload),
      });

      if (response.status === 401) {
        clearSession();
        setAuthUser(null);
        openAuthModal("login");
        throw new Error("Sua sessão expirou. Faça login novamente para enviar ao suporte.");
      }

      if (!response.ok) {
        const errorMessage = await getApiErrorMessage(
          response,
          "Não foi possível enviar a reclamação para o suporte.",
        );
        throw new Error(errorMessage);
      }

      const data = await response.json().catch(() => ({}));
      setSupportErrors({});
      setSupportFeedback({
        variant: "success",
        text: data?.protocolo
          ? `Reclamação recebida com sucesso. Protocolo: ${data.protocolo}.`
          : "Reclamação recebida com sucesso pelo time de suporte.",
      });
      setSupportForm((prev) => ({
        ...prev,
        categoria: "",
        processo: "",
        assunto: "",
        mensagem: "",
      }));
    } catch (error) {
      setSupportFeedback({
        variant: "danger",
        text:
          error instanceof Error
            ? error.message
            : "Não foi possível enviar a reclamação para o suporte.",
      });
    } finally {
      setSupportLoading(false);
    }
  };

  /**
   * Dispara download automatico do DOCX quando a API devolve base64 + nome.
   * Chamado em todos os caminhos de submit (manual, peticao, confirmacao HiL).
   * Como roda dentro de um callback iniciado por clique do usuario, o browser
   * trata como user-gesture e nao aciona popup blocker.
   */
  const autoDownloadDocx = (arquivoB64, arquivoNome) => {
    if (!arquivoB64 || !arquivoNome) return;
    try {
      const mime = arquivoNome.toLowerCase().endsWith(".docx")
        ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        : "application/octet-stream";
      autoDownloadArquivo(arquivoB64, arquivoNome, mime);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[autoDownloadDocx] falhou:", err);
    }
  };

  const autoDownloadArquivo = (arquivoB64, arquivoNome, mime) => {
    if (!arquivoB64 || !arquivoNome) return;
    const blob = base64ToBlob(arquivoB64, mime || "application/octet-stream");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = arquivoNome;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  /**
   * Baixa a peca de uma contestacao ja salva (regenera via /baixar).
   * - formato='docx': dispara download do .docx (com template/timbre se salvo)
   * - formato='pdf':  abre nova aba com versao imprimivel + window.print()
   *                   o usuario salva como PDF pelo dialogo do navegador
   */
  const handleBaixarContestacao = async (contestacaoId, formato = "docx") => {
    try {
      const accessToken = await getSupabaseAccessToken();
      const url = new URL(
        `/api/contestacoes/${contestacaoId}/baixar`,
        PETICAO_API_URL,
      );
      if (formato === "pdf") url.searchParams.set("formato", "pdf");
      const resp = await fetch(url.toString(), {
        method: "GET",
        credentials: "include",
        headers: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      });
      if (!resp.ok) {
        const msg = await getApiErrorMessage(resp, `Falha HTTP ${resp.status}.`);
        setFeedback({
          variant: "danger",
          text: `Nao foi possivel baixar a peca: ${msg}`,
        });
        return;
      }
      const data = await resp.json();
      const b64 = data?.arquivo_editado_base64 || "";
      const nome =
        data?.arquivo_editado_nome ||
        `contestacao_${contestacaoId}.${formato === "pdf" ? "pdf" : "docx"}`;
      const mime =
        data?.arquivo_editado_mime_type ||
        (formato === "pdf"
          ? "application/pdf"
          : "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
      if (!b64) {
        setFeedback({ variant: "warning", text: "Resposta sem arquivo." });
        return;
      }
      autoDownloadArquivo(b64, nome, mime);
    } catch (err) {
      console.error("[handleBaixarContestacao] falhou:", err);
      setFeedback({
        variant: "danger",
        text: `Erro ao baixar a peca: ${err.message || err}`,
      });
    }
  };

  const handleExcluirContestacao = async (contestacaoId) => {
    if (!contestacaoId) return;
    if (
      !window.confirm(
        "Tem certeza que deseja excluir esta peça? Esta ação não pode ser desfeita.",
      )
    ) {
      return;
    }
    try {
      const accessToken = await getSupabaseAccessToken();
      const url = new URL(
        `/api/contestacoes/${contestacaoId}`,
        PETICAO_API_URL,
      ).toString();
      const resp = await fetch(url, {
        method: "DELETE",
        credentials: "include",
        headers: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      });
      if (!resp.ok) {
        const msg = await getApiErrorMessage(resp, `Falha HTTP ${resp.status}.`);
        setFeedback({
          variant: "danger",
          text: `Não foi possível excluir: ${msg}`,
        });
        return;
      }
      setHistory((prev) =>
        prev.filter((p) => p.contestacao_id !== contestacaoId),
      );
      setFeedback({ variant: "success", text: "Peça excluída com sucesso." });
    } catch (err) {
      console.error("[handleExcluirContestacao] falhou:", err);
      setFeedback({
        variant: "danger",
        text: `Erro ao excluir a peça: ${err.message || err}`,
      });
    }
  };

  const handleSubmitPeticao = async () => {
    if (!authUser) {
      setFeedback({
        variant: "warning",
        text: "Faça login para enviar casos ao backend.",
      });
      openAuthModal("login");
      return;
    }

    if (!peticaoFile) {
      setFeedback({
        variant: "danger",
        text: "Anexe a petição inicial em PDF ou DOCX antes de enviar.",
      });
      setFormErrors({ peticao: "Anexe a petição inicial." });
      return;
    }

    setLoading(true);
    setSubmitted(false);
    setFeedback(null);
    setLastCaseId(null);
    setAutomationStatus({ webhook: 100, ia: 32, validacao: 18 });
    setProgresso({ ativo: true, segundos: 0 });

    try {
      const accessToken = await getSupabaseAccessToken();
      if (isSupabaseConfigured && !accessToken) {
        clearSession();
        setAuthUser(null);
        openAuthModal("login");
        setFeedback({
          variant: "warning",
          text: "Sua sessão expirou. Faça login novamente para continuar.",
        });
        setLoading(false);
        return;
      }

      // Pre-ping no backend: confirma que /health responde em ate 3s antes
      // de comecar a serializar 3MB de base64. Evita travar o botao em
      // "Processando..." quando o backend esta off ou o browser bloqueia.
      try {
        const healthUrl = new URL("/health", PETICAO_API_URL).toString();
        const pingCtrl = new AbortController();
        const pingTimer = setTimeout(() => pingCtrl.abort(), 3000);
        const pingResp = await fetch(healthUrl, { method: "GET", signal: pingCtrl.signal });
        clearTimeout(pingTimer);
        if (!pingResp.ok) throw new Error(`backend nao saudavel (HTTP ${pingResp.status})`);
      } catch (pingErr) {
        setLoading(false);
        setFeedback({
          variant: "danger",
          text: `Backend nao responde em http://localhost:8000. Verifique se a stack esta no ar (docker compose up -d) antes de gerar. Detalhe: ${pingErr.message || pingErr}`,
        });
        return;
      }

      const peticaoBase64 = await readFileAsBase64(peticaoFile);
      const modeloBaseBase64 = modeloBaseFile
        ? await readFileAsBase64(modeloBaseFile)
        : null;

      // PR5 Multi-documentos: serializa todos os anexos em paralelo.
      const anexosSerializados = await Promise.all(
        anexosFiles.map(async (f) => ({
          base64: await readFileAsBase64(f),
          nome: f.name,
          mime_type: f.type || "application/octet-stream",
        })),
      );

      const payload = {
        arquivo_peticao_base64: peticaoBase64,
        arquivo_peticao_nome: peticaoFile.name,
        arquivo_peticao_mime_type: peticaoFile.type || "application/octet-stream",
        modelo_base_base64: modeloBaseBase64,
        modelo_base_nome: modeloBaseFile?.name || null,
        tipo_acao_hint: tipoAcaoHint.trim() || null,
        pontos_contestante: pontosContestante.trim() || null,
        arquivos_anexos: anexosSerializados,
      };

      // Avisa o usuario se o payload eh grande (modelo .docx vira ~2-3MB
      // em base64); ajuda a calibrar expectativa de tempo de upload.
      const payloadStr = JSON.stringify(payload);
      const payloadMB = (payloadStr.length / (1024 * 1024)).toFixed(2);
      if (payloadStr.length > 5 * 1024 * 1024) {
        console.warn(`[peticao] payload de ${payloadMB}MB pode demorar pra fazer upload`);
      }

      // AbortController com timeout de 9 minutos. Fluxo n8n (Claude Sonnet)
      // costuma levar ~5-6min; backend gasta +10-30s salvando+embedding.
      // 9min dá margem confortavel sem trancar o usuario pra sempre.
      const submitCtrl = new AbortController();
      const HARD_TIMEOUT_MS = 9 * 60 * 1000; // 9min - margem sobre N8N_TIMEOUT_SECONDS=360
      const submitTimer = setTimeout(() => submitCtrl.abort(), HARD_TIMEOUT_MS);

      let response;
      try {
        response = await fetch(PETICAO_API_URL, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: payloadStr,
          signal: submitCtrl.signal,
        });
      } catch (fetchErr) {
        clearTimeout(submitTimer);
        setLoading(false);
        const abortado = fetchErr.name === "AbortError";
        setFeedback({
          variant: "danger",
          text: abortado
            ? `Timeout (${Math.round(HARD_TIMEOUT_MS / 60000)}min) — o backend não respondeu a tempo. Pode ser bloqueio do browser/extensão, ou o n8n demorou demais. Tente novamente ou veja os logs.`
            : `Falha de rede ao enviar a petição: ${fetchErr.message}. Verifique se o backend está no ar e se não há extensão bloqueando POST grandes (payload de ${payloadMB}MB).`,
        });
        return;
      }
      clearTimeout(submitTimer);

      if (!response.ok) {
        const errorMessage = await getApiErrorMessage(
          response,
          `Falha HTTP ${response.status}.`,
        );
        if (response.status === 401) {
          clearSession();
          setAuthUser(null);
          openAuthModal("login");
          throw new Error("Sessão expirada ou token inválido. Faça login novamente.");
        }
        throw new Error(errorMessage);
      }

      const backendData = await response.json().catch(() => ({}));

      // PR5 HiL: confianca baixa -> abre modal de revisao em vez do resultado.
      if (backendData?.requer_revisao_humana === true) {
        setLoading(false);
        setRevisaoData({
          contestacao_id: backendData.contestacao_id,
          dados_extraidos: backendData.dados_extraidos || {},
          dados_confianca: backendData.dados_confianca,
          modelo_base_base64: modeloBaseBase64,
        });
        setRevisaoError("");
        setShowRevisaoModal(true);
        setFeedback({
          variant: "warning",
          text:
            backendData.mensagem ||
            "Confiança baixa na extração. Revise os dados antes de gerar a minuta.",
        });
        await loadDashboardData({ silent: true });
        return;
      }

      const dadosExtraidos = backendData?.dados_extraidos || {};
      const minuta = backendData?.minuta || {};
      const engine = backendData?.engine_ia || {};
      const arquivoB64 = backendData?.arquivo_editado_base64 || "";
      const arquivoNome = backendData?.arquivo_editado_nome || "contestacao.docx";

      // Preenche o formulario manual com os dados extraidos para facilitar
      // edicao posterior do advogado.
      setForm((prev) => ({
        ...prev,
        processo: dadosExtraidos.numero_processo || prev.processo,
        autor: dadosExtraidos.autor || prev.autor,
        reu: dadosExtraidos.reu || prev.reu,
        tipoAcao: dadosExtraidos.tipo_acao || prev.tipoAcao,
        pedidoAutor: minuta.tese_central || prev.pedidoAutor,
        fatos: dadosExtraidos.fatos_resumo || prev.fatos,
      }));

      // Coloca o texto da minuta no editor ao vivo.
      const impugPedidos = minuta.impugnacao_pedidos && typeof minuta.impugnacao_pedidos === "object"
        ? Object.entries(minuta.impugnacao_pedidos)
            .map(([pedido, resposta]) => `${pedido}\n${resposta}`)
            .join("\n\n")
        : null;
      const partesMinuta = [
        minuta.tese_central && `TESE CENTRAL\n${minuta.tese_central}`,
        minuta.preliminares && `PRELIMINARES\n${minuta.preliminares}`,
        minuta.merito && `MERITO\n${minuta.merito}`,
        impugPedidos && `IMPUGNACAO DOS PEDIDOS\n${impugPedidos}`,
        minuta.fundamentos && `FUNDAMENTOS\n${minuta.fundamentos}`,
        minuta.pedidos && `PEDIDOS\n${minuta.pedidos}`,
      ].filter(Boolean);
      if (partesMinuta.length > 0) {
        setLiveDraft(partesMinuta.join("\n\n"));
        setLiveDraftTouched(true);
      }

      const riscos = Array.isArray(minuta.riscos) ? minuta.riscos : [];
      const defesasConsultadas = backendData?.defesas_anteriores?.consultadas ?? 0;
      // PR6 #2 — Self-Correction: avisos de citacoes incertas para o advogado revisar.
      const citacoesIncertas = Array.isArray(backendData?.citacoes_incertas)
        ? backendData.citacoes_incertas : [];
      const citacoesVerificadas = Array.isArray(backendData?.citacoes_verificadas)
        ? backendData.citacoes_verificadas : [];
      // PR12 #10 — Detector de Contradicoes: minuta vs fatos extraidos da peticao.
      const contradicoes = Array.isArray(backendData?.contradicoes)
        ? backendData.contradicoes : [];
      setIaResult({
        engine, riscos, arquivoB64, arquivoNome, defesasConsultadas,
        citacoesIncertas, citacoesVerificadas, contradicoes,
      });
      autoDownloadDocx(arquivoB64, arquivoNome);

      if (typeof backendData?.contestacao_id !== "undefined") {
        setLastCaseId(String(backendData.contestacao_id));
      }

      setLoading(false);
      setSubmitted(true);
      setShowResultModal(true);
      setAutomationStatus({ webhook: 100, ia: 86, validacao: 92 });

      setFeedback({
        variant: "success",
        text: "Contestação gerada a partir da petição inicial. Revise antes de protocolar.",
      });
      await loadDashboardData({ silent: true });
      setCurrentPage("dashboard");
    } catch (error) {
      setLoading(false);
      setAutomationStatus({ webhook: 42, ia: 0, validacao: 0 });
      await loadDashboardData({ silent: true });
      setFeedback({
        variant: "danger",
        text:
          error instanceof Error
            ? error.message
            : "Não foi possível gerar a contestação a partir da petição.",
      });
    }
  };

  // PR5 HiL: o usuario revisou os dados extraidos no modal e clicou Confirmar.
  // Reenviamos para /confirmar-extracao com os dados corrigidos (workflow n8n
  // pula o Claude Extrator graças à flag dados_extraidos_pre_validados).
  const handleConfirmarExtracao = async (dadosCorrigidos) => {
    if (!revisaoData?.contestacao_id) return;
    setRevisaoLoading(true);
    setRevisaoError("");

    try {
      const accessToken = await getSupabaseAccessToken();
      const response = await fetch(confirmarExtracaoUrl(revisaoData.contestacao_id), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          dados_extraidos: dadosCorrigidos,
          pontos_contestante: pontosContestante.trim() || null,
          modelo_base_base64: revisaoData.modelo_base_base64 || null,
        }),
      });

      if (!response.ok) {
        const msg = await getApiErrorMessage(response, `Falha HTTP ${response.status}`);
        throw new Error(msg);
      }

      const data = await response.json().catch(() => ({}));
      const minuta = data?.minuta || {};
      const engine = data?.engine_ia || {};
      const arquivoB64 = data?.arquivo_editado_base64 || "";
      const arquivoNome = data?.arquivo_editado_nome || "contestacao.docx";

      // Atualiza form e draft com a minuta gerada com dados corrigidos.
      setForm((prev) => ({
        ...prev,
        processo: dadosCorrigidos.numero_processo || prev.processo,
        autor: dadosCorrigidos.autor || prev.autor,
        reu: dadosCorrigidos.reu || prev.reu,
        tipoAcao: dadosCorrigidos.tipo_acao || prev.tipoAcao,
        pedidoAutor: minuta.tese_central || prev.pedidoAutor,
        fatos: dadosCorrigidos.fatos_resumo || prev.fatos,
      }));

      const impugPedidos = minuta.impugnacao_pedidos && typeof minuta.impugnacao_pedidos === "object"
        ? Object.entries(minuta.impugnacao_pedidos)
            .map(([pedido, resposta]) => `${pedido}\n${resposta}`)
            .join("\n\n")
        : null;
      const partesMinuta = [
        minuta.tese_central && `TESE CENTRAL\n${minuta.tese_central}`,
        minuta.preliminares && `PRELIMINARES\n${minuta.preliminares}`,
        minuta.merito && `MERITO\n${minuta.merito}`,
        impugPedidos && `IMPUGNACAO DOS PEDIDOS\n${impugPedidos}`,
        minuta.fundamentos && `FUNDAMENTOS\n${minuta.fundamentos}`,
        minuta.pedidos && `PEDIDOS\n${minuta.pedidos}`,
      ].filter(Boolean);
      if (partesMinuta.length > 0) {
        setLiveDraft(partesMinuta.join("\n\n"));
        setLiveDraftTouched(true);
      }

      setIaResult({
        engine,
        riscos: Array.isArray(minuta.riscos) ? minuta.riscos : [],
        arquivoB64,
        arquivoNome,
        defesasConsultadas: 0,
        citacoesIncertas: Array.isArray(data?.citacoes_incertas) ? data.citacoes_incertas : [],
        citacoesVerificadas: Array.isArray(data?.citacoes_verificadas) ? data.citacoes_verificadas : [],
        contradicoes: Array.isArray(data?.contradicoes) ? data.contradicoes : [],
      });
      autoDownloadDocx(arquivoB64, arquivoNome);
      setLastCaseId(String(data?.contestacao_id || revisaoData.contestacao_id));

      setShowRevisaoModal(false);
      setRevisaoData(null);
      setSubmitted(true);
      setShowResultModal(true);
      setAutomationStatus({ webhook: 100, ia: 86, validacao: 92 });
      setFeedback({
        variant: "success",
        text: "Contestação gerada com os dados revisados. Pronta para download.",
      });
      await loadDashboardData({ silent: true });
      setCurrentPage("dashboard");
    } catch (error) {
      setRevisaoError(
        error instanceof Error ? error.message : "Falha ao confirmar revisão.",
      );
    } finally {
      setRevisaoLoading(false);
    }
  };

  const handleSubmit = async (event) => {
    // Valida formulario, serializa arquivo em base64 e envia payload completo ao backend.
    event.preventDefault();

    // Guard contra double-submit: ignora cliques enquanto request anterior nao terminou.
    if (loading) return;

    // Roteamento por modo: "peticao" usa pipeline diferente.
    if (modo === "peticao") {
      return handleSubmitPeticao();
    }

    if (!authUser) {
      setFeedback({
        variant: "warning",
        text: "Faça login para enviar casos ao backend.",
      });
      openAuthModal("login");
      return;
    }

    const errors = validateForm();

    if (Object.keys(errors).length) {
      setFormErrors(errors);
      setSubmitted(false);
      setFeedback({
        variant: "danger",
        text: "Revise os campos obrigatorios antes de enviar.",
      });
      return;
    }

    setLoading(true);
    setSubmitted(false);
    setFeedback(null);
    setLastCaseId(null);
    setAutomationStatus({ webhook: 100, ia: 32, validacao: 18 });
    setProgresso({ ativo: true, segundos: 0 });

    try {
      const accessToken = await getSupabaseAccessToken();
      if (isSupabaseConfigured && !accessToken) {
        clearSession();
        setAuthUser(null);
        openAuthModal("login");
        setFeedback({
          variant: "warning",
          text: "Sua sessão expirou. Faça login novamente para continuar.",
        });
        setLoading(false);
        return;
      }

      const arquivoConteudoBase64 = await readFileAsBase64(uploadedFile);
      // PR10: peca base do escritorio (papel timbrado/estilo) tambem no modo manual.
      // O backend extrai o texto e injeta como modelo_mae_texto no payload do n8n.
      const modeloBaseBase64Manual = modeloBaseFile
        ? await readFileAsBase64(modeloBaseFile)
        : null;
      const payload = {
        numero_processo: form.processo.trim(),
        autor: form.autor.trim(),
        reu: form.reu.trim(),
        // PR6 P2.2: subtipo (quando preenchido) e mais especifico que o ramo
        // generico — alimenta o RAG semantico para busca mais precisa.
        tipo_acao: (form.subtipoAcao || form.tipoAcao || "").trim(),
        fatos: form.fatos.trim(),
        pedido_autor: form.pedidoAutor.trim(),
        arquivo_base: uploadedFile?.name || "",
        arquivo_base_nome: uploadedFile?.name || "",
        arquivo_base_mime_type: uploadedFile?.type || "application/octet-stream",
        arquivo_base_tamanho_bytes: uploadedFile?.size || 0,
        arquivo_base_conteudo_base64: arquivoConteudoBase64,
        modelo_base_base64: modeloBaseBase64Manual,
        modelo_base_nome: modeloBaseFile?.name || null,
        texto_editado_ao_vivo: (liveDraft.trim() || generatedDraftText).trim(),
      };

      const response = await fetch(AGENT_API_URL, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorMessage = await getApiErrorMessage(
          response,
          `Falha HTTP ${response.status}.`,
        );

        if (response.status === 401) {
          clearSession();
          setAuthUser(null);
          openAuthModal("login");
          throw new Error("Sessão expirada ou token inválido. Faça login novamente.");
        }
        throw new Error(errorMessage);
      }

      const backendData = await response.json().catch(() => ({}));
      const workflowData =
        backendData && typeof backendData === "object" && backendData.workflow
          ? backendData.workflow
          : {};
      const suggestedDraft =
        typeof workflowData?.minuta?.texto_base === "string"
          ? workflowData.minuta.texto_base
          : "";

      if (suggestedDraft.trim()) {
        setLiveDraft(suggestedDraft.trim());
        setLiveDraftTouched(true);
      }

      if (typeof backendData?.id_caso === "string" && backendData.id_caso.trim()) {
        setLastCaseId(backendData.id_caso.trim());
      }

      const engine = workflowData?.engine_ia || {};
      const riscos = Array.isArray(workflowData?.minuta?.riscos) ? workflowData.minuta.riscos : [];
      const arquivoB64 = typeof workflowData?.arquivo_editado_base64 === "string" ? workflowData.arquivo_editado_base64 : "";
      const arquivoNome = workflowData?.arquivo_editado_nome || "contestacao.txt";
      const defesasConsultadas = workflowData?.defesas_anteriores?.consultadas ?? 0;
      setIaResult({ engine, riscos, arquivoB64, arquivoNome, defesasConsultadas });
      autoDownloadDocx(arquivoB64, arquivoNome);

      setLoading(false);
      setSubmitted(true);
      setShowResultModal(true);
      setAutomationStatus({ webhook: 100, ia: 86, validacao: 92 });

      setFeedback({
        variant: "success",
        text: "Defesa gerada e pronta para revisão.",
      });
      await loadDashboardData({ silent: true });
      setCurrentPage("dashboard");
    } catch (error) {
      setLoading(false);
      setAutomationStatus({ webhook: 42, ia: 0, validacao: 0 });
      await loadDashboardData({ silent: true });
      setFeedback({
        variant: "danger",
        text:
          error instanceof Error
            ? error.message
            : "Não foi possível enviar para o agente de IA. Verifique backend e autenticação.",
      });
    }
  };

  const triggerBlobDownload = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleDownloadDoc = () => {
    if (!submitted) {
      setFeedback({
        variant: "warning",
        text: "Envie o caso para automação antes de baixar o documento.",
      });
      return;
    }

    const baseName = normalizeFileName(form.processo || lastCaseId || "defesa");
    const safeProcesso = escapeHtml(form.processo || "");
    const safeAutor = escapeHtml(form.autor || "");
    const safeReu = escapeHtml(form.reu || "");
    const safeTipoAcao = escapeHtml(form.tipoAcao || "");
    const safeDraft = escapeHtml(liveDraft.trim() || generatedDraftText).replace(/\n/g, "<br/>");

    const docHtml = `
      <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
        <head>
          <meta charset="utf-8" />
          <title>Defesa ${safeProcesso}</title>
          <style>
            @page { size: A4; margin: 2.5cm; }
            body { font-family: 'Times New Roman', Times, serif; font-size: 12pt; line-height: 1.6; color: #000; }
            h1 { font-size: 16pt; text-align: center; margin-bottom: 24px; }
            .meta { margin-bottom: 24px; font-size: 11pt; }
            .meta strong { display: inline-block; min-width: 140px; }
            .corpo { white-space: pre-wrap; text-align: justify; }
          </style>
        </head>
        <body>
          <h1>DEFESA - MINUTA GERADA PELO SISTEMA</h1>
          <div class="meta">
            <p><strong>Processo:</strong> ${safeProcesso || "-"}</p>
            <p><strong>Autor:</strong> ${safeAutor || "-"}</p>
            <p><strong>Réu:</strong> ${safeReu || "-"}</p>
            <p><strong>Ramo do direito:</strong> ${safeTipoAcao || "-"}</p>
          </div>
          <div class="corpo">${safeDraft}</div>
        </body>
      </html>
    `;

    const blob = new Blob(["﻿", docHtml], {
      type: "application/msword;charset=utf-8",
    });
    triggerBlobDownload(blob, `${baseName}.doc`);

    setFeedback({
      variant: "success",
      text: "Download do DOCX iniciado. Verifique sua pasta de downloads.",
    });
  };

  const handleDownloadPdf = () => {
    if (!submitted) {
      setFeedback({
        variant: "warning",
        text: "Envie o caso para automação antes de gerar o PDF.",
      });
      return;
    }

    const safeProcesso = escapeHtml(form.processo || "");
    const safeAutor = escapeHtml(form.autor || "");
    const safeReu = escapeHtml(form.reu || "");
    const safeTipoAcao = escapeHtml(form.tipoAcao || "");
    const safeDraft = escapeHtml(liveDraft.trim() || generatedDraftText).replace(/\n/g, "<br/>");
    const printable = `<!doctype html>
      <html lang="pt-BR">
        <head>
          <meta charset="utf-8" />
          <title>Defesa ${safeProcesso || ""}</title>
          <style>
            @page { size: A4; margin: 2.5cm; }
            body { font-family: 'Times New Roman', Times, serif; font-size: 12pt; line-height: 1.6; color: #000; margin: 0; padding: 32px; }
            h1 { font-size: 16pt; text-align: center; margin-bottom: 24px; }
            .meta { margin-bottom: 24px; font-size: 11pt; border-bottom: 1px solid #ccc; padding-bottom: 12px; }
            .meta p { margin: 4px 0; }
            .meta strong { display: inline-block; min-width: 140px; }
            .corpo { white-space: pre-wrap; text-align: justify; }
            .actions { position: fixed; top: 12px; right: 12px; }
            .actions button { padding: 10px 16px; font-size: 14px; cursor: pointer; }
            @media print { .actions { display: none; } body { padding: 0; } }
          </style>
        </head>
        <body>
          <div class="actions">
            <button onclick="window.print()">Imprimir / Salvar como PDF</button>
          </div>
          <h1>DEFESA - MINUTA GERADA PELO SISTEMA</h1>
          <div class="meta">
            <p><strong>Processo:</strong> ${safeProcesso || "-"}</p>
            <p><strong>Autor:</strong> ${safeAutor || "-"}</p>
            <p><strong>Réu:</strong> ${safeReu || "-"}</p>
            <p><strong>Ramo do direito:</strong> ${safeTipoAcao || "-"}</p>
          </div>
          <div class="corpo">${safeDraft}</div>
          <script>setTimeout(function(){ window.print(); }, 400);</script>
        </body>
      </html>`;

    const blob = new Blob([printable], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const printWindow = window.open(url, "_blank");

    if (!printWindow) {
      const link = document.createElement("a");
      link.href = url;
      link.download = `${normalizeFileName(form.processo || lastCaseId || "defesa")}.html`;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setFeedback({
        variant: "warning",
        text: "Pop-up bloqueado. Baixamos o arquivo .html — abra no navegador e use Ctrl+P para salvar como PDF.",
      });
      return;
    }

    setTimeout(() => URL.revokeObjectURL(url), 60000);
    setFeedback({
      variant: "success",
      text: "Janela de impressao aberta. Use 'Salvar como PDF' no dialogo de impressao.",
    });
  };

  const handleNavigate = (pageId) => {
    if (pageId === "dashboard" && authUser) {
      void loadDashboardData({ silent: false });
    }
    setCurrentPage(pageId);
  };

  return (
    <div className="app-shell min-vh-100">
      <AppNavbar
        currentPage={currentPage}
        onNavigate={handleNavigate}
        authUser={authUser}
        onOpenLogin={openAuthModal}
        onOpenSignup={openAuthModal}
        onLogout={handleLogout}
      />

      {currentPage === "inicio" && (
        <>
          <HeroSection onNavigate={handleNavigate} />
          <StatsSection />
        </>
      )}

      {currentPage === "painel" && (
        <MainPanelSection
          form={form}
          completion={completion}
          submitted={submitted}
          loading={loading}
          formErrors={formErrors}
          uploadError={uploadError}
          uploadedFile={uploadedFile}
          draftInfo={draftInfo}
          feedback={feedback}
          liveDraft={liveDraft}
          liveDraftTouched={liveDraftTouched}
          onChange={handleChange}
          onSubmit={handleSubmit}
          onFileSelect={handleFileSelect}
          onRemoveFile={handleRemoveFile}
          onSaveDraft={handleSaveDraft}
          onLiveDraftChange={handleLiveDraftChange}
          onResetLiveDraft={handleResetLiveDraft}
          modo={modo}
          onModoChange={handleModoChange}
          peticaoFile={peticaoFile}
          peticaoError={peticaoError}
          onPeticaoFileSelect={handlePeticaoFileSelect}
          onRemovePeticaoFile={handleRemovePeticaoFile}
          modeloBaseFile={modeloBaseFile}
          modeloBaseError={modeloBaseError}
          onModeloBaseFileSelect={handleModeloBaseFileSelect}
          onRemoveModeloBaseFile={handleRemoveModeloBaseFile}
          tipoAcaoHint={tipoAcaoHint}
          onTipoAcaoHintChange={(e) => setTipoAcaoHint(e.target.value)}
          pontosContestante={pontosContestante}
          onPontosContestanteChange={(e) => setPontosContestante(e.target.value)}
          anexosFiles={anexosFiles}
          anexosError={anexosError}
          onAdicionarAnexo={handleAdicionarAnexo}
          onRemoverAnexo={handleRemoverAnexo}
        />
      )}

      <ProgressoGeracao ativo={progresso.ativo} segundos={progresso.segundos} />

      {currentPage === "dashboard" && (
        <>
          <DashboardSection
            history={history}
            automationStatus={automationStatus}
            dashboardCards={dashboardCards}
            loading={dashboardLoading}
            onBaixarPeca={handleBaixarContestacao}
            onExcluirPeca={handleExcluirContestacao}
          />
          <section className="pb-5">
            <div className="container">
              <div className="d-flex flex-wrap gap-2">
                <Button variant="outline-secondary" onClick={() => handleNavigate("painel")}>
                  Voltar para edição
                </Button>
              </div>
            </div>
          </section>
        </>
      )}

      {currentPage === "contato" && (
        <SupportSection
          form={supportForm}
          errors={supportErrors}
          feedback={supportFeedback}
          loading={supportLoading}
          onChange={handleSupportChange}
          onSubmit={handleSupportSubmit}
        />
      )}

      <AppFooter />

      <RevisaoHumanaModal
        show={showRevisaoModal}
        onHide={() => {
          setShowRevisaoModal(false);
          setRevisaoData(null);
          setRevisaoError("");
        }}
        onConfirm={handleConfirmarExtracao}
        dadosExtraidos={revisaoData?.dados_extraidos}
        confianca={revisaoData?.dados_confianca}
        loading={revisaoLoading}
        error={revisaoError}
      />

      <AuthModal
        show={showAuthModal}
        mode={authMode}
        form={authForm}
        errors={authErrors}
        feedback={authFeedback}
        loading={authLoading}
        passwordChecks={authPasswordChecks}
        pendingConfirmEmail={pendingConfirmEmail}
        resendCooldownUntil={resendCooldownUntil}
        resendLoading={resendLoading}
        onHide={closeAuthModal}
        onModeChange={handleAuthModeChange}
        onFieldChange={handleAuthFieldChange}
        onFieldBlur={handleAuthFieldBlur}
        onSubmit={handleAuthSubmit}
        onResendConfirmation={handleResendConfirmation}
        onChangeConfirmEmail={handleChangeConfirmEmail}
      />

      <Modal
        show={showResultModal}
        onHide={() => setShowResultModal(false)}
        centered
        dialogClassName="platform-modal"
      >
        <Modal.Header closeButton>
          <Modal.Title>Defesa gerada com sucesso</Modal.Title>
        </Modal.Header>

        <Modal.Body>
          {iaResult?.riscos?.length > 0 && (
            <div className="mt-2 p-2 border border-danger rounded bg-danger bg-opacity-10">
              <small className="text-danger fw-semibold d-block mb-1">
                ⚠ Pontos de atenção — revisar antes de protocolar:
              </small>
              <ul className="mb-0 mt-1" style={{ fontSize: "0.85rem" }}>
                {iaResult.riscos.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
          {iaResult?.citacoesIncertas?.length > 0 && (
            <div className="mt-3 p-2 border border-warning rounded bg-warning bg-opacity-10">
              <small className="text-warning fw-semibold d-block mb-1">
                ⚠ Citações a revisar antes de protocolar (
                {iaResult.citacoesIncertas.length})
              </small>
              <ul className="mb-0" style={{ fontSize: "0.82rem" }}>
                {iaResult.citacoesIncertas.map((c, i) => (
                  <li key={i} className="mb-1">
                    <span className="badge bg-warning text-dark me-1">
                      {c.tipo || "incerta"}
                    </span>
                    <strong>{c.texto}</strong>
                    {c.motivo && (
                      <div className="text-muted" style={{ fontSize: "0.78rem" }}>
                        {c.motivo}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {iaResult?.contradicoes?.length > 0 && (
            <div className="mt-3 p-2 border border-danger rounded bg-danger bg-opacity-10">
              <small className="text-danger fw-semibold d-block mb-1">
                ⚠ Contradições detectadas entre petição inicial e contestação (
                {iaResult.contradicoes.length})
              </small>
              <ul className="mb-0" style={{ fontSize: "0.82rem" }}>
                {iaResult.contradicoes.map((c, i) => {
                  const badgeClass =
                    c.severidade === "alta"
                      ? "bg-danger"
                      : c.severidade === "media"
                      ? "bg-warning text-dark"
                      : "bg-secondary";
                  return (
                    <li key={i} className="mb-2">
                      <span className={`badge ${badgeClass} me-1`}>
                        {c.severidade || "baixa"}
                      </span>
                      <span className="badge bg-light text-dark border me-1">
                        {c.tipo || "outros"}
                      </span>
                      <strong>{c.descricao}</strong>
                      {(c.trecho_peticao || c.trecho_minuta) && (
                        <div
                          className="text-muted mt-1"
                          style={{ fontSize: "0.78rem" }}
                        >
                          {c.trecho_peticao && (
                            <div>
                              📄 Petição: <em>{c.trecho_peticao}</em>
                            </div>
                          )}
                          {c.trecho_minuta && (
                            <div>
                              📝 Minuta: <em>{c.trecho_minuta}</em>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {iaResult?.citacoesVerificadas?.length > 0 && (
            <p className="mt-2 mb-0 text-success" style={{ fontSize: "0.82rem" }}>
              ✓ {iaResult.citacoesVerificadas.length} citação(ões) verificada(s) pelo
              revisor IA.
            </p>
          )}
          <p className="mt-3 mb-0 text-muted" style={{ fontSize: "0.9rem" }}>
            O texto completo está disponível no dashboard para revisão e exportação.
          </p>
        </Modal.Body>

        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowResultModal(false)}>
            Fechar
          </Button>

          {iaResult?.arquivoB64 && (
            <Button
              variant="outline-light"
              onClick={() => {
                const nome = iaResult.arquivoNome || "contestacao.docx";
                const mime = nome.endsWith(".docx")
                  ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  : "text/plain;charset=utf-8";
                const blob = base64ToBlob(iaResult.arquivoB64, mime);
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download = nome;
                link.click();
                URL.revokeObjectURL(link.href);
              }}
            >
              Baixar minuta
            </Button>
          )}

          <Button
            variant="dark"
            onClick={() => {
              setShowResultModal(false);
              handleNavigate("dashboard");
            }}
          >
            Ir para dashboard
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
