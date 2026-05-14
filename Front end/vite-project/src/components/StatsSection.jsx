// Secao de metricas/resumo para reforcar ganhos da automacao juridica.
import React from "react";
import { Card, Col, Container, Row } from "react-bootstrap";
import { stats } from "../data/mockData";

/**
 * Exibe metricas de alto nivel da operacao em formato de cards.
 */
export default function StatsSection() {
  return (
    <section className="stats-band pb-4">
      <Container>
        <div className="stats-intro">
          <div className="section-kicker">Indicadores da plataforma</div>
          <h2 className="stats-title">Metricas da operacao de automacao de defesas</h2>
          <p className="stats-copy mb-0">
            Visao direta de tempo, capacidade e qualidade para acompanhar o desempenho
            do fluxo juridico com clareza.
          </p>
        </div>

        <Row className="g-3">
          {stats.map((item) => (
            <Col md={6} lg={3} key={item.label}>
              <Card className="stat-card border-0 h-100">
                <Card.Body className="p-4">
                  <div className="stat-label">{item.label}</div>
                  <div className="stat-value">{item.value}</div>
                  {item.detail && <p className="small mb-0 text-secondary">{item.detail}</p>}
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  );
}
