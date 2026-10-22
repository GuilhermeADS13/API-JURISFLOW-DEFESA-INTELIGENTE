// Hero principal da landing com proposta de valor e chamadas para acao.
import React from "react";
import { Button, Col, Container, Row } from "react-bootstrap";

// As 4 etapas sao uma sequencia real do pipeline — por isso numeradas.
const ETAPAS = [
  {
    titulo: "Leitura da petição inicial",
    texto: "PDF ou DOCX. Partes, pedidos e valores são extraídos automaticamente.",
  },
  {
    titulo: "Defesas que o escritório já fez",
    texto: "Busca nos casos já contestados para manter a tese e a estratégia da casa.",
  },
  {
    titulo: "Redação com citações conferidas",
    texto: "Cada artigo e súmula citado é conferido; o que ficar incerto vem sinalizado.",
  },
  {
    titulo: "Word no modelo do escritório",
    texto: "Timbre, fonte e espaçamento do seu modelo, pronto para revisar.",
  },
];

/**
 * Folha ilustrativa da peca gerada, no mesmo formato do Word exportado
 * (Arial justificado, secoes "I – ...", numeracao "01.-").
 */
function FolhaContestacao() {
  return (
    <figure className="folha-wrap mb-0">
      <div
        className="folha"
        role="img"
        aria-label="Exemplo ilustrativo de contestação trabalhista gerada pelo JurisFlow"
      >
        <div className="folha-timbre" aria-hidden="true">
          <span className="folha-monograma" />
          Timbre do seu escritório
        </div>

        <div aria-hidden="true">
          <p className="folha-enderecamento">
            Excelentíssimo(a) Senhor(a) Juiz(a) da __ª Vara do Trabalho de ________
          </p>
          <p className="folha-processo">Processo nº 0000000-00.2026.5.00.0000</p>

          <p>
            <strong>EMPRESA RÉ LTDA.</strong>, já qualificada nos autos da reclamação
            trabalhista movida por <strong>RECLAMANTE</strong>, vem apresentar
          </p>
          <p className="folha-titulo-peca">CONTESTAÇÃO</p>

          <p className="folha-secao">I – PRELIMINARES</p>
          <p className="folha-item">01.- Da inépcia do pedido de horas extras</p>
          <p>
            A inicial não indica o valor do pedido, como exige o{" "}
            <mark className="folha-citacao">art. 840, § 1º, da CLT</mark>
            <span className="folha-selo">conferida</span>
          </p>
          <span className="folha-linha" />
          <span className="folha-linha folha-linha-curta" />

          <p className="folha-secao">II – MÉRITO</p>
          <span className="folha-linha" />
          <span className="folha-linha" />
          <span className="folha-linha folha-linha-media" />
        </div>
      </div>
      <figcaption className="folha-legenda">Exemplo ilustrativo de minuta.</figcaption>
    </figure>
  );
}

/**
 * Secao inicial de apresentacao do produto e atalhos para as telas principais.
 */
export default function HeroSection({ onNavigate }) {
  return (
    <section id="inicio" className="hero-section py-5">
      <Container>
        <Row className="align-items-center g-4 g-lg-5">
          <Col lg={6} className="hero-copy">
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

          <Col lg={6}>
            <FolhaContestacao />
          </Col>
        </Row>

        <h2 className="visually-hidden">Como a contestação é montada</h2>
        <ol className="etapas-faixa">
          {ETAPAS.map(({ titulo, texto }, i) => (
            <li key={titulo}>
              <span className="etapa-numero" aria-hidden="true">
                {i + 1}
              </span>
              <div>
                <div className="etapa-titulo">{titulo}</div>
                <p className="etapa-texto mb-0">{texto}</p>
              </div>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
