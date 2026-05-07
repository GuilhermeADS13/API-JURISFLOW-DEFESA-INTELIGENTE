// Painel de entrada do caso: formulario, upload e edicao ao vivo da minuta.
import React, { useRef, useState } from "react";
import {
  Alert,
  Button,
  ButtonGroup,
  Card,
  Col,
  Container,
  Form,
  ProgressBar,
  Row,
} from "react-bootstrap";
import { CheckCircle, FileEarmarkText, Paperclip, Upload, XCircle } from "react-bootstrap-icons";
import { agentRules, legalBranches } from "../data/mockData";

/**
 * Formata tamanho do arquivo para exibicao amigavel ao usuario.
 */
function fileSizeLabel(file) {
  if (!file) return "";
  const size = file.size / 1024;
  if (size < 1024) return `${size.toFixed(1)} KB`;
  return `${(size / 1024).toFixed(2)} MB`;
}

/**
 * Painel principal de entrada do caso, upload e edicao ao vivo da defesa.
 */
export default function MainPanelSection({
  form,
  completion,
  submitted,
  loading,
  formErrors,
  uploadError,
  uploadedFile,
  draftInfo,
  feedback,
  liveDraft,
  liveDraftTouched,
  onChange,
  onSubmit,
  onFileSelect,
  onRemoveFile,
  onSaveDraft,
  onLiveDraftChange,
  onResetLiveDraft,
  // Guia Tecnico v2: modo "peticao" (props opcionais — fallback para "manual")
  modo = "manual",
  onModoChange,
  peticaoFile,
  peticaoError,
  onPeticaoFileSelect,
  onRemovePeticaoFile,
  modeloBaseFile,
  modeloBaseError,
  onModeloBaseFileSelect,
  onRemoveModeloBaseFile,
  tipoAcaoHint,
  onTipoAcaoHintChange,
  pontosContestante,
  onPontosContestanteChange,
  // Guia Tecnico v3 / PR5 multi-docs: lista de anexos opcionais.
  anexosFiles = [],
  anexosError,
  onAdicionarAnexo,
  onRemoverAnexo,
}) {
  const fileInputRef = useRef(null);
  const peticaoInputRef = useRef(null);
  const modeloBaseInputRef = useRef(null);
  const anexosInputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [draggingPeticao, setDraggingPeticao] = useState(false);
  const [draggingModelo, setDraggingModelo] = useState(false);

  const openPicker = () => {
    fileInputRef.current?.click();
  };

  const handleFileInput = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    onFileSelect(file);
    event.target.value = "";
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onFileSelect(file);
  };

  const openPeticaoPicker = () => peticaoInputRef.current?.click();
  const handlePeticaoInput = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    onPeticaoFileSelect?.(file);
    event.target.value = "";
  };
  const handlePeticaoDrop = (event) => {
    event.preventDefault();
    setDraggingPeticao(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onPeticaoFileSelect?.(file);
  };

  const openModeloBasePicker = () => modeloBaseInputRef.current?.click();
  const handleModeloBaseInput = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    onModeloBaseFileSelect?.(file);
    event.target.value = "";
  };
  const handleModeloBaseDrop = (event) => {
    event.preventDefault();
    setDraggingModelo(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onModeloBaseFileSelect?.(file);
  };

  const uploadValidation = uploadError || formErrors.upload;
  const peticaoValidation = peticaoError || formErrors.peticao;

  return (
    <section id="painel" className="py-5">
      <Container>
        <Row className="g-4">
          <Col lg={7}>
            <Card className="panel-card panel-entry-primary border-0 h-100">
              <Card.Body className="p-4 p-lg-5">
                <div className="mb-3">
                  <ButtonGroup className="mb-3">
                    <Button
                      variant={modo === "manual" ? "dark" : "outline-dark"}
                      onClick={() => onModoChange?.("manual")}
                      disabled={loading}
                    >
                      Preencher manualmente
                    </Button>
                    <Button
                      variant={modo === "peticao" ? "dark" : "outline-dark"}
                      onClick={() => onModoChange?.("peticao")}
                      disabled={loading}
                    >
                      Enviar peticao inicial
                    </Button>
                  </ButtonGroup>
                  <h2 className="h3 mb-2">
                    {modo === "peticao"
                      ? "Geracao automatica a partir da peticao"
                      : "Formulario para envio ao agente de IA"}
                  </h2>
                  <p className="text-secondary mb-0">
                    {modo === "peticao"
                      ? "Anexe a peticao inicial — o sistema extrai os dados e gera a contestacao."
                      : "Preencha os dados do caso, anexe a peca base e envie para automacao."}
                  </p>
                </div>

                {modo === "manual" && (
                  <div className="mb-4">
                    <div className="d-flex justify-content-between small text-secondary mb-2">
                      <span>Preenchimento do caso</span>
                      <span>{completion}%</span>
                    </div>
                    <ProgressBar now={completion} />
                  </div>
                )}

                {feedback && <Alert variant={feedback.variant}>{feedback.text}</Alert>}

                {submitted && (
                  <Alert variant="success" className="d-flex align-items-center gap-2">
                    <CheckCircle /> Defesa enviada com sucesso para o agente de IA.
                  </Alert>
                )}

                {modo === "peticao" && (
                  <Form
                    onSubmit={(event) => {
                      event.preventDefault();
                      onSubmit?.(event);
                    }}
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      className={`upload-box ${draggingPeticao ? "is-dragging" : ""} ${
                        peticaoFile ? "has-file" : ""
                      }`}
                      onClick={openPeticaoPicker}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") openPeticaoPicker();
                      }}
                      onDragOver={(event) => {
                        event.preventDefault();
                        setDraggingPeticao(true);
                      }}
                      onDragLeave={(event) => {
                        event.preventDefault();
                        setDraggingPeticao(false);
                      }}
                      onDrop={handlePeticaoDrop}
                    >
                      <FileEarmarkText size={28} className="mb-2" />
                      <div className="fw-semibold">Peticao inicial (obrigatorio)</div>
                      <small className="text-secondary">
                        Arraste ou clique para anexar PDF, DOC ou DOCX (ate 20 MB).
                      </small>
                    </div>
                    <input
                      ref={peticaoInputRef}
                      type="file"
                      accept=".pdf,.doc,.docx"
                      className="d-none"
                      onChange={handlePeticaoInput}
                    />
                    {peticaoFile && (
                      <div className="upload-file-summary mt-2">
                        <div className="d-flex align-items-center gap-2">
                          <Paperclip />
                          <div>
                            <div className="fw-semibold">{peticaoFile.name}</div>
                            <small className="text-secondary">{fileSizeLabel(peticaoFile)}</small>
                          </div>
                        </div>
                        <Button
                          variant="link"
                          className="upload-remove p-0"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            onRemovePeticaoFile?.();
                          }}
                        >
                          <XCircle /> Remover
                        </Button>
                      </div>
                    )}
                    {peticaoValidation && (
                      <div className="upload-feedback-error">{peticaoValidation}</div>
                    )}

                    <Form.Group className="mt-4">
                      <Form.Label>Modelo base do escritorio (opcional)</Form.Label>
                      <div
                        role="button"
                        tabIndex={0}
                        className={`upload-box ${draggingModelo ? "is-dragging" : ""} ${
                          modeloBaseFile ? "has-file" : ""
                        }`}
                        onClick={openModeloBasePicker}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") openModeloBasePicker();
                        }}
                        onDragOver={(event) => {
                          event.preventDefault();
                          setDraggingModelo(true);
                        }}
                        onDragLeave={(event) => {
                          event.preventDefault();
                          setDraggingModelo(false);
                        }}
                        onDrop={handleModeloBaseDrop}
                      >
                        <Upload size={28} className="mb-2" />
                        <small className="text-secondary">
                          Arraste ou clique para anexar um .docx com placeholders Jinja2.
                        </small>
                      </div>
                      <input
                        ref={modeloBaseInputRef}
                        type="file"
                        accept=".docx"
                        className="d-none"
                        onChange={handleModeloBaseInput}
                      />
                      {modeloBaseFile && (
                        <div className="upload-file-summary mt-2">
                          <div className="d-flex align-items-center gap-2">
                            <Paperclip />
                            <div>
                              <div className="fw-semibold">{modeloBaseFile.name}</div>
                              <small className="text-secondary">{fileSizeLabel(modeloBaseFile)}</small>
                            </div>
                          </div>
                          <Button
                            variant="link"
                            className="upload-remove p-0"
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              onRemoveModeloBaseFile?.();
                            }}
                          >
                            <XCircle /> Remover
                          </Button>
                        </div>
                      )}
                      {modeloBaseError && (
                        <div className="upload-feedback-error">{modeloBaseError}</div>
                      )}
                    </Form.Group>

                    <Row className="g-3 mt-1">
                      <Col md={6}>
                        <Form.Group>
                          <Form.Label>Tipo de acao (dica para a IA)</Form.Label>
                          <Form.Control
                            value={tipoAcaoHint || ""}
                            onChange={onTipoAcaoHintChange}
                            placeholder="Ex.: Trabalhista — Horas Extras"
                          />
                        </Form.Group>
                      </Col>
                      <Col xs={12}>
                        <Form.Group>
                          <Form.Label>Pontos especificos para atacar (opcional)</Form.Label>
                          <Form.Control
                            as="textarea"
                            rows={4}
                            value={pontosContestante || ""}
                            onChange={onPontosContestanteChange}
                            placeholder="Ex.: prescricao bienal, ausencia de prova testemunhal, valor da causa irreal"
                          />
                        </Form.Group>
                      </Col>
                    </Row>

                    {/* PR5 multi-docs: anexos opcionais (max 5, total 50MB) */}
                    <Form.Group className="mt-4">
                      <Form.Label>
                        Anexos da peticao (opcional — contratos, e-mails, laudos)
                      </Form.Label>
                      <div className="d-flex align-items-center gap-2 flex-wrap">
                        <Button
                          type="button"
                          variant="outline-dark"
                          size="sm"
                          disabled={loading || anexosFiles.length >= 5}
                          onClick={() => anexosInputRef.current?.click()}
                        >
                          <Paperclip className="me-1" /> Adicionar anexo
                        </Button>
                        <small className="text-secondary">
                          {anexosFiles.length}/5 anexos · PDF, DOC ou DOCX (max 20MB cada)
                        </small>
                      </div>
                      <input
                        ref={anexosInputRef}
                        type="file"
                        accept=".pdf,.doc,.docx"
                        className="d-none"
                        multiple
                        onChange={(event) => {
                          const files = Array.from(event.target.files || []);
                          for (const f of files) onAdicionarAnexo?.(f);
                          event.target.value = "";
                        }}
                      />
                      {anexosFiles.length > 0 && (
                        <ul className="list-unstyled mt-2 mb-0">
                          {anexosFiles.map((f, idx) => (
                            <li
                              key={`${f.name}-${idx}`}
                              className="upload-file-summary mt-2"
                            >
                              <div className="d-flex align-items-center gap-2">
                                <Paperclip />
                                <div>
                                  <div className="fw-semibold">{f.name}</div>
                                  <small className="text-secondary">{fileSizeLabel(f)}</small>
                                </div>
                              </div>
                              <Button
                                type="button"
                                variant="link"
                                className="upload-remove p-0"
                                onClick={() => onRemoverAnexo?.(idx)}
                              >
                                <XCircle /> Remover
                              </Button>
                            </li>
                          ))}
                        </ul>
                      )}
                      {anexosError && (
                        <div className="upload-feedback-error">{anexosError}</div>
                      )}
                    </Form.Group>

                    <div className="d-flex flex-wrap gap-2 mt-4">
                      <Button type="submit" variant="dark" disabled={loading}>
                        {loading ? "Processando..." : "Gerar contestacao automaticamente"}
                      </Button>
                    </div>
                  </Form>
                )}

                {modo === "manual" && (
                <Form onSubmit={onSubmit}>
                  <Row className="g-3">
                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Numero do processo</Form.Label>
                        <Form.Control
                          name="processo"
                          value={form.processo}
                          onChange={onChange}
                          placeholder="0001234-56.2026.8.00.0000"
                          isInvalid={Boolean(formErrors.processo)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.processo}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Cliente ou parte</Form.Label>
                        <Form.Control
                          name="cliente"
                          value={form.cliente}
                          onChange={onChange}
                          placeholder="Nome da parte"
                          isInvalid={Boolean(formErrors.cliente)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.cliente}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Ramo do direito</Form.Label>
                        <Form.Select
                          name="tipoAcao"
                          value={form.tipoAcao}
                          onChange={onChange}
                          isInvalid={Boolean(formErrors.tipoAcao)}
                        >
                          <option value="">Selecione o ramo</option>
                          {legalBranches.map((branch) => (
                            <option key={branch} value={branch}>
                              {branch}
                            </option>
                          ))}
                        </Form.Select>
                        <Form.Control.Feedback type="invalid">
                          {formErrors.tipoAcao}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Tese principal</Form.Label>
                        <Form.Control
                          name="tese"
                          value={form.tese}
                          onChange={onChange}
                          placeholder="Ex.: ausencia de responsabilidade"
                          isInvalid={Boolean(formErrors.tese)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.tese}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col xs={12}>
                      <Form.Group>
                        <Form.Label>Observacoes para o agente</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={4}
                          name="observacoes"
                          value={form.observacoes}
                          onChange={onChange}
                          placeholder="Contexto do caso e orientacoes para a defesa."
                          isInvalid={Boolean(formErrors.observacoes)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.observacoes}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col xs={12}>
                      <div
                        role="button"
                        tabIndex={0}
                        className={`upload-box ${dragging ? "is-dragging" : ""} ${
                          uploadedFile ? "has-file" : ""
                        }`}
                        onClick={openPicker}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") openPicker();
                        }}
                        onDragOver={(event) => {
                          event.preventDefault();
                          setDragging(true);
                        }}
                        onDragLeave={(event) => {
                          event.preventDefault();
                          setDragging(false);
                        }}
                        onDrop={handleDrop}
                      >
                        <Upload size={28} className="mb-2" />
                        <div className="fw-semibold">Upload da peça base</div>
                        <small className="text-secondary">
                          Arraste ou clique para anexar DOCX, DOC ou PDF.
                        </small>
                      </div>

                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".doc,.docx,.pdf"
                        className="d-none"
                        onChange={handleFileInput}
                      />

                      {uploadedFile && (
                        <div className="upload-file-summary mt-2">
                          <div className="d-flex align-items-center gap-2">
                            <Paperclip />
                            <div>
                              <div className="fw-semibold">{uploadedFile.name}</div>
                              <small className="text-secondary">{fileSizeLabel(uploadedFile)}</small>
                            </div>
                          </div>

                          <Button
                            variant="link"
                            className="upload-remove p-0"
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              onRemoveFile();
                            }}
                          >
                            <XCircle /> Remover
                          </Button>
                        </div>
                      )}

                      {uploadValidation && <div className="upload-feedback-error">{uploadValidation}</div>}
                    </Col>
                  </Row>

                  <div className="d-flex flex-wrap gap-2 mt-4">
                    <Button type="submit" variant="dark" disabled={loading}>
                      {loading ? "Processando..." : "Enviar para IA"}
                    </Button>

                    <Button
                      type="button"
                      variant="outline-dark"
                      disabled={loading}
                      onClick={onSaveDraft}
                    >
                      Salvar rascunho
                    </Button>
                  </div>

                  {draftInfo && <div className="draft-info mt-3">{draftInfo}</div>}
                </Form>
                )}
              </Card.Body>
            </Card>
          </Col>

          <Col lg={5}>
            <div className="d-grid gap-4 h-100">
              <Card className="dashboard-card panel-entry-secondary border-0">
                <Card.Body className="p-4">
                  <h3 className="h5 mb-2">Edicao ao vivo da defesa</h3>
                  <p className="text-secondary small mb-3">
                    Ajuste o texto livremente antes de exportar.
                  </p>

                  <Form.Group>
                    <Form.Control
                      as="textarea"
                      rows={16}
                      value={liveDraft}
                      onChange={onLiveDraftChange}
                      className="live-editor-area"
                      placeholder="A defesa editada em tempo real sera exibida aqui."
                    />
                  </Form.Group>

                  <div className="d-flex justify-content-between align-items-center mt-3 gap-2 flex-wrap">
                    <Button variant="outline-dark" size="sm" onClick={onResetLiveDraft}>
                      Atualizar com texto gerado
                    </Button>
                    <small className="text-secondary">
                      {liveDraftTouched ? "Edicao manual ativa" : "Texto sincronizado com o formulario"}
                    </small>
                  </div>
                </Card.Body>
              </Card>

              <Card className="side-info-card panel-entry-tertiary border-0">
                <Card.Body className="p-4">
                  <h3 className="h5 mb-3">Regras do agente juridico</h3>
                  <div className="agent-rule-list">
                    {agentRules.map((rule) => (
                      <div key={rule} className="rule-item">
                        <span className="rule-marker" />
                        <span>{rule}</span>
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
