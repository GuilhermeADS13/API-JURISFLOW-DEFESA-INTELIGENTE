// Barra de navegacao principal com menu de paginas e estado de autenticacao.
import React from "react";
import { Button, Container, Nav, Navbar } from "react-bootstrap";

/**
 * Gera iniciais para o avatar textual no menu superior.
 */
function initialsFromName(name) {
  return (name || "JF")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

/**
 * Barra de navegacao principal com estado de autenticacao.
 */
export default function AppNavbar({
  currentPage,
  onNavigate,
  authUser,
  onOpenLogin,
  onOpenSignup,
  onLogout,
}) {
  const menuItems = [
    { id: "inicio", label: "Inicio" },
    { id: "painel", label: "Formulario IA" },
    { id: "dashboard", label: "Dashboard" },
    { id: "contato", label: "Suporte" },
  ];

  return (
    <Navbar expand="lg" className="app-navbar sticky-top">
      <Container className="nav-shell">
        <Navbar.Brand
          as="button"
          className="d-flex align-items-center gap-2 border-0 bg-transparent p-0"
          onClick={() => onNavigate("inicio")}
        >
          <span className="brand-mark">JF</span>
          <span>
            <span className="brand-name d-block">JurisFlow AI</span>
            <span className="brand-sub d-block">Automacao inteligente de defesas juridicas</span>
          </span>
        </Navbar.Brand>

        <Navbar.Toggle aria-controls="main-navbar" />

        <Navbar.Collapse id="main-navbar">
          <Nav className="nav-center mx-auto align-items-lg-center gap-lg-3">
            {menuItems.map((item) => (
              <Nav.Link
                as="button"
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`menu-link-btn ${currentPage === item.id ? "is-active" : ""}`}
              >
                {item.label}
              </Nav.Link>
            ))}
          </Nav>

          <div className="nav-actions ms-lg-3">
            {authUser ? (
              <>
                <div className="auth-user-chip">
                  <span className="auth-user-avatar">{initialsFromName(authUser.name)}</span>
                  <span className="auth-user-text">
                    <strong>Conta ativa</strong>
                    <small>{authUser.email}</small>
                  </span>
                </div>

                <Button variant="dark" size="sm" className="nav-cta auth-primary-btn" onClick={onLogout}>
                  Sair
                </Button>
              </>
            ) : (
              <>
                <Button variant="link" size="sm" className="auth-link-btn" onClick={() => onOpenLogin("login")}>
                  Entrar
                </Button>

                <Button variant="outline-dark" size="sm" className="auth-outline-btn" onClick={() => onOpenSignup("signup")}>
                  Criar conta
                </Button>
              </>
            )}
          </div>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}
