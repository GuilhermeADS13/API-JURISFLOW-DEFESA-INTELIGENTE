// Hero principal da landing com proposta de valor e chamadas para acao.
import React from "react";
import { Badge, Button, Card, Col, Container, Row } from "react-bootstrap";
import {
  Activity,
  ArrowRight,
  FileEarmarkArrowUp,
  FileEarmarkRuled,
  FileEarmarkCheck,
  Search,
  ShieldCheck,
} from "react-bootstrap-icons";

/**
 * Secao inicial de apresentacao do produto e atalhos para as telas principais.
 */
export default function HeroSection({ onNavigate }) {
  return (
    <section id="inicio" className="hero-section py-5">
      <Container>
        <Row className="align-items-center g-4 g-lg-5">
          <Col lg={7} className="hero-copy">
            <Badge className="hero-kicker mb-3">Automacao juridica de defesas</Badge>

            <h1 className="hero-title mb-3">
              Organize o envio para o agente de IA e acompanhe a edicao da defesa em tempo real.
            </h1>

            <p className="hero-lead mb-4">
              A plataforma foi simplificada para fluxo direto: preencher dados,
              anexar a peca base, editar ao vivo e enviar para automacao com seguranca.
            </p>

            <div className="d-flex flex-wrap gap-2 mb-4">
              <Button
                variant="dark"
                size="lg"
                className="hero-primary-btn"
                onClick={() => onNavigate("painel")}
              >
                Abrir formulario IA
              </Button>

              <Button
                variant="outline-dark"
                size="lg"
                className="hero-secondary-btn"
                onClick={() => onNavigate("dashboard")}
              >
                Ver dashboard
              </Button>
            </div>

            <div className="d-flex flex-wrap gap-2 mb-4">
              <span className="trust-pill">Formulario unico e objetivo</span>
              <span className="trust-pill">Edicao ao vivo da defesa</span>
              <span className="trust-pill">Historico claro no dashboard</span>
            </div>

            <div className="hero-proof-grid">
              <div className="proof-card">
                <div className="proof-title">Fluxo direto para IA</div>
                <p className="mb-0">
                  Dados essenciais, upload da peca base e envio para automacao no mesmo ambiente.
                </p>
              </div>

              <div className="proof-card">
                <div className="proof-title">Dashboard simples</div>
                <p className="mb-0">
                  Indicadores claros e leitura facil para acompanhar cada defesa processada.
                </p>
              </div>
            </div>
          </Col>

          <Col lg={5}>
            <Card className="hero-console border-0">
              <Card.Body className="p-4 p-lg-4">
                <div className="console-topbar mb-4">
                  <div>
                    <small className="console-eyebrow d-block">Workspace juridico em tempo real</small>
                    <h2 className="h5 mb-1">Painel de automacao de defesas</h2>
                    <p className="text-secondary small mb-0">
                      Etapas do processamento da defesa com visao objetiva.
                    </p>
                  </div>
                  <div className="console-score">
                    <strong>~5min</strong>
                    <span>tempo medio</span>
                  </div>
                </div>

                <div className="d-grid gap-3">
                  <div className="feature-row">
                    <div className="feature-icon">
                      <FileEarmarkArrowUp />
                    </div>
                    <div>
                      <div className="fw-semibold">Upload da peticao</div>
                      <small className="text-secondary">
                        PDF ou DOCX — os dados do processo sao extraidos automaticamente
                      </small>
                    </div>
                    <span className="feature-state">Step 01</span>
                  </div>

                  <div className="feature-row">
                    <div className="feature-icon">
                      <Search />
                    </div>
                    <div>
                      <div className="fw-semibold">Busca por defesa similar</div>
                      <small className="text-secondary">
                        Consulta semantica nos casos anteriores do escritorio
                      </small>
                    </div>
                    <span className="feature-state">Step 02</span>
                  </div>

                  <div className="feature-row">
                    <div className="feature-icon">
                      <ShieldCheck />
                    </div>
                    <div>
                      <div className="fw-semibold">Geracao com citacoes verificadas</div>
                      <small className="text-secondary">
                        Cada jurisprudencia e artigo sao checados antes da entrega
                      </small>
                    </div>
                    <span className="feature-state">Step 03</span>
                  </div>

                  <div className="feature-row">
                    <div className="feature-icon">
                      <FileEarmarkCheck />
                    </div>
                    <div>
                      <div className="fw-semibold">Download no estilo do escritorio</div>
                      <small className="text-secondary">
                        Fonte, espacamento e cabecalho copiados do modelo enviado
                      </small>
                    </div>
                    <span className="feature-state">Step 04</span>
                  </div>
                </div>

                <div className="console-mini-grid mt-4">
                  <div className="console-mini-card">
                    <Activity className="console-mini-icon" />
                    <div className="console-mini-value">~5min</div>
                    <div className="console-mini-label">fluxos rapidos</div>
                  </div>
                  <div className="console-mini-card">
                    <FileEarmarkRuled className="console-mini-icon" />
                    <div className="console-mini-value">DOCX</div>
                    <div className="console-mini-label">pronto pra baixar</div>
                  </div>
                </div>

                <div className="console-footer mt-3 pt-3">
                  <span>Formulario, IA e dashboard conectados no mesmo fluxo</span>
                  <ArrowRight />
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
