// Secao de suporte para abertura de reclamacoes e contato com a equipe.
import React from "react";
import { Alert, Badge, Button, Card, Col, Container, Form, Row } from "react-bootstrap";
import { supportChannels, supportChecklist, supportIssueTypes } from "../data/mockData";

/**
 * Tela de suporte/contato para recebimento de reclamacoes dos clientes.
 */
export default function SupportSection({ form, errors, feedback, loading, onChange, onSubmit }) {
  return (
    <section id="contato" className="py-5">
      <Container>
        <Row className="g-4">
          {/* Coluna principal: formulario de envio da reclamacao. */}
          <Col lg={7}>
            <Card className="panel-card support-entry-primary border-0 h-100">
              <Card.Body className="p-4 p-lg-5">
                <div className="mb-4 support-head">
                  <Badge className="section-badge mb-2">Suporte</Badge>
                  <h2 className="h3 mb-2">Canal de contato para reclamacoes</h2>
                  <p className="text-secondary mb-0 support-intro-copy">
                    Registre sua reclamacao e nosso time recebe por e-mail para iniciar o tratamento.
                  </p>
                </div>

                {feedback && <Alert variant={feedback.variant}>{feedback.text}</Alert>}

                <Form onSubmit={onSubmit}>
                  <Row className="g-3">
                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Nome completo</Form.Label>
                        <Form.Control
                          name="nome"
                          value={form.nome}
                          onChange={onChange}
                          placeholder="Seu nome"
                          isInvalid={Boolean(errors.nome)}
                        />
                        <Form.Control.Feedback type="invalid">{errors.nome}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>E-mail para retorno</Form.Label>
                        <Form.Control
                          type="email"
                          name="email"
                          value={form.email}
                          onChange={onChange}
                          placeholder="contato@escritorio.com"
                          isInvalid={Boolean(errors.email)}
                        />
                        <Form.Control.Feedback type="invalid">{errors.email}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={7}>
                      <Form.Group>
                        <Form.Label>Categoria da reclamacao</Form.Label>
                        <Form.Select
                          name="categoria"
                          value={form.categoria}
                          onChange={onChange}
                          isInvalid={Boolean(errors.categoria)}
                        >
                          <option value="">Selecione a categoria</option>
                          {supportIssueTypes.map((issue) => (
                            <option key={issue} value={issue}>
                              {issue}
                            </option>
                          ))}
                        </Form.Select>
                        <Form.Control.Feedback type="invalid">{errors.categoria}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={5}>
                      <Form.Group>
                        <Form.Label>Numero do processo (opcional)</Form.Label>
                        <Form.Control
                          name="processo"
                          value={form.processo}
                          onChange={onChange}
                          placeholder="0001234-56.2026.8.00.0000"
                          isInvalid={Boolean(errors.processo)}
                        />
                        <Form.Control.Feedback type="invalid">{errors.processo}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col xs={12}>
                      <Form.Group>
                        <Form.Label>Assunto</Form.Label>
                        <Form.Control
                          name="assunto"
                          value={form.assunto}
                          onChange={onChange}
                          placeholder="Resumo curto da reclamacao"
                          isInvalid={Boolean(errors.assunto)}
                        />
                        <Form.Control.Feedback type="invalid">{errors.assunto}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col xs={12}>
                      <Form.Group>
                        <Form.Label>Descricao detalhada</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={6}
                          name="mensagem"
                          value={form.mensagem}
                          onChange={onChange}
                          className="support-message-area"
                          placeholder="Descreva o problema, impacto e contexto para o time de suporte."
                          isInvalid={Boolean(errors.mensagem)}
                        />
                        <Form.Control.Feedback type="invalid">{errors.mensagem}</Form.Control.Feedback>
                      </Form.Group>
                    </Col>
                  </Row>

                  <div className="d-flex flex-wrap gap-2 mt-4">
                    <Button type="submit" variant="dark" disabled={loading}>
                      {loading ? "Enviando..." : "Enviar reclamacao"}
                    </Button>
                  </div>
                </Form>
              </Card.Body>
            </Card>
          </Col>

          {/* Coluna lateral: orientacoes de atendimento e checklist recomendado. */}
          <Col lg={5}>
            <div className="d-grid gap-4 h-100">
              <Card className="dashboard-card support-entry-secondary border-0">
                <Card.Body className="p-4">
                  <h3 className="h5 mb-3">Como tratamos seu contato</h3>
                  <div className="support-chip-grid">
                    {supportChannels.map((item) => (
                      <div key={item} className="support-chip-item">
                        {item}
                      </div>
                    ))}
                  </div>
                </Card.Body>
              </Card>

              <Card className="side-info-card support-entry-tertiary border-0">
                <Card.Body className="p-4">
                  <h3 className="h5 mb-3">Checklist recomendado</h3>
                  <div className="agent-rule-list">
                    {supportChecklist.map((item) => (
                      <div key={item} className="rule-item">
                        <span className="rule-marker" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </Card.Body>
              </Card>
            </div>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
