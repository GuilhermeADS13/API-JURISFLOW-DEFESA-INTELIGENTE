// Modal de autenticacao para login e cadastro via Supabase Auth.
import React, { useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";

/**
 * Tela exibida depois que o signup retorna sem sessao (confirmacao de e-mail obrigatoria).
 * Mostra o e-mail cadastrado, conta regressiva para reenvio e opcao de trocar endereco.
 */
function ConfirmEmailScreen({
  email,
  feedback,
  resendCooldownUntil,
  resendLoading,
  onResend,
  onChangeEmail,
}) {
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    const update = () => {
      const diff = Math.max(0, Math.ceil((resendCooldownUntil - Date.now()) / 1000));
      setSecondsLeft(diff);
    };
    update();
    const id = setInterval(update, 500);
    return () => clearInterval(id);
  }, [resendCooldownUntil]);

  const canResend = secondsLeft === 0 && !resendLoading;

  return (
    <div className="confirm-email-screen">
      <div className="confirm-email-icon" aria-hidden="true">
        ✉
      </div>

      <h5 className="confirm-email-title">Verifique seu e-mail</h5>

      <p className="confirm-email-body">
        Enviamos um link de confirmacao para:
      </p>
      <p className="confirm-email-address">{email}</p>
      <p className="confirm-email-hint">
        Abra o e-mail e clique em <strong>Confirmar cadastro</strong>. Depois
        volte aqui e faca login normalmente.
        <br />
        Nao encontrou? Verifique a caixa de spam.
      </p>

      {feedback && (
        <div className={`auth-feedback is-${feedback.variant}`}>
          {feedback.text}
        </div>
      )}

      <Button
        variant="dark"
        className="w-100 auth-submit-btn mb-2"
        disabled={!canResend}
        onClick={onResend}
      >
        {resendLoading
          ? "Reenviando..."
          : secondsLeft > 0
          ? `Reenviar e-mail (${secondsLeft}s)`
          : "Reenviar e-mail de confirmacao"}
      </Button>

      <button type="button" className="auth-change-email-link" onClick={onChangeEmail}>
        Usar outro e-mail
      </button>
    </div>
  );
}

/**
 * Modal de autenticacao (login/cadastro) com validacao visual em tempo real.
 * Quando `pendingConfirmEmail` estiver preenchido, exibe a tela de confirmacao.
 */
export default function AuthModal({
  show,
  mode,
  form,
  errors,
  feedback,
  loading,
  passwordChecks,
  pendingConfirmEmail,
  resendCooldownUntil,
  resendLoading,
  onHide,
  onModeChange,
  onFieldChange,
  onFieldBlur,
  onSubmit,
  onResendConfirmation,
  onChangeConfirmEmail,
}) {
  const isSignup = mode === "signup";
  const showConfirmScreen = Boolean(pendingConfirmEmail);

  return (
    <Modal show={show} onHide={onHide} centered dialogClassName="auth-modal">
      <Modal.Header closeButton>
        <Modal.Title>
          {showConfirmScreen
            ? "Confirme seu e-mail"
            : isSignup
            ? "Crie sua conta"
            : "Entre na plataforma"}
        </Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {showConfirmScreen ? (
          <ConfirmEmailScreen
            email={pendingConfirmEmail}
            feedback={feedback}
            resendCooldownUntil={resendCooldownUntil ?? 0}
            resendLoading={resendLoading ?? false}
            onResend={onResendConfirmation}
            onChangeEmail={onChangeConfirmEmail}
          />
        ) : (
          <>
            <div className="auth-mode-switch">
              <button
                type="button"
                className={`auth-mode-pill ${!isSignup ? "is-active" : ""}`}
                onClick={() => onModeChange("login")}
              >
                Entrar
              </button>

              <button
                type="button"
                className={`auth-mode-pill ${isSignup ? "is-active" : ""}`}
                onClick={() => onModeChange("signup")}
              >
                Criar conta
              </button>
            </div>

            <div className="auth-intro-copy">
              {isSignup
                ? "Cadastre-se para centralizar os casos, salvar rascunhos e acompanhar a automacao das defesas."
                : "Acesse sua operacao juridica para continuar os fluxos, revisar minutas e exportar as defesas."}
            </div>

            {feedback && (
              <div className={`auth-feedback is-${feedback.variant}`}>
                {feedback.text}
              </div>
            )}

            <Form onSubmit={onSubmit}>
              {isSignup && (
                <Form.Group className="mb-3">
                  <Form.Label>Nome</Form.Label>
                  <Form.Control
                    name="name"
                    value={form.name}
                    onChange={onFieldChange}
                    onBlur={onFieldBlur}
                    placeholder="Seu nome ou o nome do escritorio"
                    isInvalid={Boolean(errors.name)}
                  />
                  <Form.Control.Feedback type="invalid">{errors.name}</Form.Control.Feedback>
                </Form.Group>
              )}

              <Form.Group className="mb-3">
                <Form.Label>E-mail</Form.Label>
                <Form.Control
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={onFieldChange}
                  onBlur={onFieldBlur}
                  placeholder="voce@escritorio.com"
                  autoComplete={isSignup ? "email" : "username"}
                  isInvalid={Boolean(errors.email)}
                />
                <Form.Control.Feedback type="invalid">{errors.email}</Form.Control.Feedback>
              </Form.Group>

              <Form.Group className="mb-3">
                <Form.Label>Senha</Form.Label>
                <Form.Control
                  type="password"
                  name="password"
                  value={form.password}
                  onChange={onFieldChange}
                  onBlur={onFieldBlur}
                  placeholder={isSignup ? "Crie uma senha forte" : "Digite sua senha"}
                  autoComplete={isSignup ? "new-password" : "current-password"}
                  isInvalid={Boolean(errors.password)}
                />
                <Form.Control.Feedback type="invalid">{errors.password}</Form.Control.Feedback>

                {isSignup && (
                  <div className="d-grid gap-1 mt-2">
                    <small className={passwordChecks?.minLength ? "text-success" : "text-secondary"}>
                      Minimo de 8 caracteres
                    </small>
                    <small className={passwordChecks?.hasUppercase ? "text-success" : "text-secondary"}>
                      Pelo menos 1 letra maiuscula
                    </small>
                    <small className={passwordChecks?.hasLowercase ? "text-success" : "text-secondary"}>
                      Pelo menos 1 letra minuscula
                    </small>
                    <small className={passwordChecks?.hasNumber ? "text-success" : "text-secondary"}>
                      Pelo menos 1 numero
                    </small>
                    <small className={passwordChecks?.hasSymbol ? "text-success" : "text-secondary"}>
                      Pelo menos 1 simbolo
                    </small>
                  </div>
                )}
              </Form.Group>

              <Button type="submit" variant="dark" className="w-100 auth-submit-btn" disabled={loading}>
                {loading ? "Processando..." : isSignup ? "Criar conta e entrar" : "Entrar com e-mail"}
              </Button>
            </Form>

            <div className="auth-footer-note">
              {isSignup
                ? "Ao criar sua conta, voce libera o acesso ao workspace de automacao de defesas."
                : "Sem conta ainda? Troque para Criar conta e habilite seu acesso em segundos."}
            </div>
          </>
        )}
      </Modal.Body>
    </Modal>
  );
}
