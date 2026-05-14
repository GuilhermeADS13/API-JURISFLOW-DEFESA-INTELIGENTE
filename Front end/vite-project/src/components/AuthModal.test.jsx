// Testes de componente para AuthModal (login/cadastro).
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { describe, expect, it, vi } from "vitest";
import AuthModal from "./AuthModal";

// Props minimas para renderizar o modal sem erros.
function makeProps(overrides = {}) {
  return {
    show: true,
    mode: "login",
    form: { name: "", email: "", password: "" },
    errors: { name: "", email: "", password: "" },
    feedback: null,
    loading: false,
    passwordChecks: {},
    onHide: vi.fn(),
    onModeChange: vi.fn(),
    onFieldChange: vi.fn(),
    onFieldBlur: vi.fn(),
    onSubmit: vi.fn((e) => e.preventDefault()),
    ...overrides,
  };
}

describe("AuthModal", () => {
  describe("titulo do modal", () => {
    it("exibe 'Entre na plataforma' no modo login", () => {
      render(<AuthModal {...makeProps({ mode: "login" })} />);
      expect(screen.getByText("Entre na plataforma")).toBeInTheDocument();
    });

    it("exibe 'Crie sua conta' no modo signup", () => {
      render(<AuthModal {...makeProps({ mode: "signup" })} />);
      expect(screen.getByText("Crie sua conta")).toBeInTheDocument();
    });
  });

  describe("botoes de alternancia de modo", () => {
    it("chama onModeChange('login') ao clicar em Entrar", () => {
      const onModeChange = vi.fn();
      render(<AuthModal {...makeProps({ onModeChange })} />);
      fireEvent.click(screen.getByText("Entrar"));
      expect(onModeChange).toHaveBeenCalledWith("login");
    });

    it("chama onModeChange('signup') ao clicar em Criar conta", () => {
      const onModeChange = vi.fn();
      render(<AuthModal {...makeProps({ onModeChange })} />);
      fireEvent.click(screen.getByText("Criar conta"));
      expect(onModeChange).toHaveBeenCalledWith("signup");
    });
  });

  describe("campo nome", () => {
    it("exibe campo Nome apenas no modo signup", () => {
      render(<AuthModal {...makeProps({ mode: "signup" })} />);
      // React Bootstrap Form.Label nao gera htmlFor automatico; buscamos pelo placeholder.
      expect(screen.getByPlaceholderText(/nome ou o nome/i)).toBeInTheDocument();
    });

    it("oculta campo Nome no modo login", () => {
      render(<AuthModal {...makeProps({ mode: "login" })} />);
      expect(screen.queryByPlaceholderText(/nome ou o nome/i)).not.toBeInTheDocument();
    });
  });

  describe("campos de email e senha", () => {
    it("exibe input de email em ambos os modos", () => {
      render(<AuthModal {...makeProps({ mode: "login" })} />);
      expect(screen.getByPlaceholderText("voce@escritorio.com")).toBeInTheDocument();
    });

    it("exibe input de senha no modo login", () => {
      render(<AuthModal {...makeProps({ mode: "login" })} />);
      expect(screen.getByPlaceholderText("Digite sua senha")).toBeInTheDocument();
    });

    it("exibe input de senha forte no modo signup", () => {
      render(<AuthModal {...makeProps({ mode: "signup" })} />);
      expect(screen.getByPlaceholderText("Crie uma senha forte")).toBeInTheDocument();
    });
  });

  describe("feedback", () => {
    it("nao exibe feedback quando null", () => {
      render(<AuthModal {...makeProps({ feedback: null })} />);
      expect(screen.queryByText(/erro|sucesso/i)).not.toBeInTheDocument();
    });

    it("exibe mensagem de feedback quando fornecida", () => {
      const feedback = { variant: "error", text: "Credenciais invalidas." };
      render(<AuthModal {...makeProps({ feedback })} />);
      expect(screen.getByText("Credenciais invalidas.")).toBeInTheDocument();
    });

    it("exibe feedback de sucesso", () => {
      const feedback = { variant: "success", text: "Conta criada com sucesso!" };
      render(<AuthModal {...makeProps({ feedback })} />);
      expect(screen.getByText("Conta criada com sucesso!")).toBeInTheDocument();
    });
  });

  describe("texto introdutorio", () => {
    it("exibe texto de login quando modo e login", () => {
      render(<AuthModal {...makeProps({ mode: "login" })} />);
      expect(screen.getByText(/continuar os fluxos/i)).toBeInTheDocument();
    });

    it("exibe texto de cadastro quando modo e signup", () => {
      render(<AuthModal {...makeProps({ mode: "signup" })} />);
      expect(screen.getByText(/centralizar os casos/i)).toBeInTheDocument();
    });
  });

  describe("erros de campo", () => {
    it("exibe mensagem de erro do campo email", () => {
      const errors = { name: "", email: "Informe um e-mail valido.", password: "" };
      render(<AuthModal {...makeProps({ errors })} />);
      expect(screen.getByText("Informe um e-mail valido.")).toBeInTheDocument();
    });
  });
});
