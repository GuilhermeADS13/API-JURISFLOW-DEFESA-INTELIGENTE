// Secao de dashboard com indicadores de automacao e historico de contestacoes.
import React from "react";
import { Badge, Card, Col, Container, ProgressBar, Row, Table } from "react-bootstrap";
import StatusBadge from "./ui/StatusBadge";

/**
 * Dashboard com cards de indicadores, barras de status e historico de casos.
 */
export default function DashboardSection({
  history,
  automationStatus,
  dashboardCards = [],
  loading = false,
}) {
  return (
    <section id="dashboard" className="py-5">
      <Container>
        <div className="dashboard-simple-header dashboard-entry-header mb-4">
          <Badge className="section-badge mb-2">Dashboard</Badge>
          <h2 className="fw-bold mb-1">Dashboard informativo para os advogados</h2>
          <p className="text-secondary mb-0">
            Veja o status da automacao e o historico das defesas em uma unica tela.
          </p>
        </div>

        <Row className="g-3 mb-4 dashboard-entry-stats">
          {dashboardCards.map((card) => (
            <Col md={6} lg={3} key={card.label} className="dashboard-entry-stat-col">
              <Card className="dashboard-card dashboard-entry-stat-card border-0 h-100">
                <Card.Body className="p-4">
                  <div className="stat-label">{card.label}</div>
                  <div className="stat-value mb-0">{card.value}</div>
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>

        <Row className="g-4">
          <Col lg={4}>
            <Card className="dashboard-card dashboard-entry-main-card border-0 h-100">
              <Card.Body className="p-4">
                <h3 className="h5 mb-3">Status da automacao</h3>

                <div className="d-grid gap-3">
                  <div>
                    <div className="d-flex justify-content-between small mb-1">
                      <span>Recepcao do envio</span>
                      <span>{automationStatus.webhook}%</span>
                    </div>
                    <ProgressBar now={automationStatus.webhook} />
                  </div>

                  <div>
                    <div className="d-flex justify-content-between small mb-1">
                      <span>Processamento da IA</span>
                      <span>{automationStatus.ia}%</span>
                    </div>
                    <ProgressBar now={automationStatus.ia} />
                  </div>

                  <div>
                    <div className="d-flex justify-content-between small mb-1">
                      <span>Validacao de saida</span>
                      <span>{automationStatus.validacao}%</span>
                    </div>
                    <ProgressBar now={automationStatus.validacao} />
                  </div>
                </div>
              </Card.Body>
            </Card>
          </Col>

          <Col lg={8}>
            <Card className="history-card dashboard-entry-main-card dashboard-entry-history-card border-0">
              <Card.Body className="p-4">
                <h3 className="h5 mb-3">Historico das defesas</h3>

                <div className="table-responsive">
                  <Table hover align="middle" className="mb-0 dashboard-history-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Natureza do caso</th>
                        <th>Tipo</th>
                        <th>Data</th>
                        <th>Status</th>
                      </tr>
                    </thead>

                    <tbody>
                      {history.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="text-secondary">
                            {loading
                              ? "Carregando historico do banco de dados..."
                              : "Nenhum caso encontrado no banco para este usuario."}
                          </td>
                        </tr>
                      ) : (
                        history.map((item) => (
                          <tr key={item.id}>
                            <td className="fw-semibold">{item.id}</td>
                            <td>{item.naturezaCaso}</td>
                            <td>{item.tipo}</td>
                            <td>{item.data}</td>
                            <td>
                              <StatusBadge status={item.status} />
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </Table>
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
