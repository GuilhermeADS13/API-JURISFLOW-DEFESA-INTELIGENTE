// Rodape institucional da aplicacao com links, canais e contexto da plataforma.
import React from "react";
import { Container } from "react-bootstrap";

/**
 * Rodape institucional com resumo do produto e direcionamento de uso.
 */
export default function AppFooter() {
  return (
    <footer className="app-footer pt-5 pb-4">
      <Container>
        <div className="footer-grid">
          <div>
            <div className="d-flex align-items-center gap-2 mb-3">
              <span className="brand-mark">JF</span>
              <div>
                <div className="brand-name">JurisFlow AI</div>
                <div className="brand-sub">Plataforma de automação de Defesas Jurídicas</div>
              </div>
            </div>
            <p className="text-secondary mb-0">
              Plataforma pensada para organizar o fluxo de defesas com
              rastreabilidade, produtividade e revisão jurídica final.
            </p>
          </div>

          <div className="footer-column">
            <div className="footer-title">Produto</div>
            <span>Painel de casos</span>
            <span>Automação de Defesas</span>
            <span>Exportação Jurídica</span>
          </div>

          <div className="footer-column">
            <div className="footer-title">Operação</div>
            <span>Fluxo do agente IA</span>
            <span>Checklist de segurança</span>
            <span>Revisão humana final</span>
          </div>
        </div>

        <div className="footer-bottom">
          <span>Plataforma focada em automação de defesas com clareza operacional</span>
          <span>Fluxo direto: formulário IA, dashboard e suporte para reclamações</span>
        </div>
      </Container>
    </footer>
  );
}
