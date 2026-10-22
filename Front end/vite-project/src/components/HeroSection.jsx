// Hero principal da landing com proposta de valor e chamadas para acao.
import React from "react";
import { Button, Card, Col, Container, Row } from "react-bootstrap";
import {
  FileEarmarkArrowUp,
  FileEarmarkCheck,
  Search,
  ShieldCheck,
} from "react-bootstrap-icons";

// As 4 etapas sao uma sequencia real do pipeline — por isso numeradas.
const ETAPAS = [
  {
    icone: <FileEarmarkArrowUp />,
    titulo: "Leitura da petição inicial",
    texto: "PDF ou DOCX. Partes, pedidos e valores são extraídos automaticamente.",
  },
  {
    icone: <Search />,
    titulo: "Defesas que o escritório já fez",
    texto: "Busca nos casos já contestados para manter a tese e a estratégia da casa.",
  },
  {
    icone: <ShieldCheck />,
    titulo: "Redação com citações conferidas",
    texto: "Cada artigo e súmula citado é conferido; o que ficar incerto vem sinalizado para você.",
  },
  {
    icone: <FileEarmarkCheck />,
    titulo: "Word no modelo do escritório",
    texto: "Timbre, fonte e espaçamento do seu modelo, pronto para revisar.",
  },
];

/**
 * Secao inicial de apresentacao do produto e atalhos para as telas principais.
 */
export default function HeroSection({ onNavigate }) {
  return (
    <section id="inicio" className="hero-section py-5">
      <Container>
        <Row className="align-items-center g-4 g-lg-5">
          <Col lg={7} className="hero-copy">
            <h1 className="hero-title mb-4">
              Da petição inicial à contestação, no padrão do seu escritório.
            </h1>

            <p className="hero-lead mb-4">
              Envie a petição e receba a minuta da defesa em Word, com as preliminares,
              o mérito ponto a ponto e o timbre do escritório. Você revisa e protocola.
            </p>

            <div className="d-flex flex-wrap gap-2">
              <Button
                variant="dark"
                size="lg"
                className="hero-primary-btn"
                onClick={() => onNavigate("painel")}
              >
                Abrir formulário
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
          </Col>

          <Col lg={5}>
            <Card className="hero-console border-0">
              <Card.Body className="p-4">
                <div className="console-topbar mb-4">
                  <div>
                    <h2 className="h5 mb-1">Como a contestação é montada</h2>
                    <p className="text-secondary small mb-0">Cerca de 5 minutos por peça.</p>
                  </div>
                </div>

                <ol className="etapas-lista d-grid gap-3 mb-0 p-0">
                  {ETAPAS.map(({ icone, titulo, texto }, i) => (
                    <li className="feature-row" key={titulo}>
                      <div className="feature-icon" aria-hidden="true">
                        {icone}
                      </div>
                      <div>
                        <div className="fw-semibold">{titulo}</div>
                        <small className="text-secondary">{texto}</small>
                      </div>
                      <span className="feature-state">Etapa {i + 1}</span>
                    </li>
                  ))}
                </ol>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
