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
import { IMaskInput } from "react-imask";
import { legalBranchGroups, subtiposAcao } from "../data/mockData";

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
  onChange,
  onSubmit,
  onFileSelect,
  onRemoveFile,
  onSaveDraft,
  // Guia Tecnico v2: modo "peticao" (props opcionais — fallback para "peticao")
  modo = "peticao",
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
  // PR15: provas embedaveis no docx final (imagens FGTS/TRCT/laudos/prints).
  embedFiles = [],
  embedError,
  onAdicionarEmbed,
  onRemoverEmbed,
  onChangeTipoEmbed,
}) {
  const fileInputRef = useRef(null);
  const peticaoInputRef = useRef(null);
  const modeloBaseInputRef = useRef(null);
  const anexosInputRef = useRef(null);
  const embedInputRef = useRef(null);
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
          {/* Editor ao vivo removido — peca final tem formatacao rica (imagens
              PR15, negritos, blockquotes) que textarea descarta. Edicao
              posterior vai pro Word. Col ocupa 100% sempre. */}
          <Col lg={12}>
            <Card className="panel-card panel-entry-primary border-0 h-100">
              <Card.Body className="p-4 p-lg-5">
                <div className="mb-3">
                  <ButtonGroup className="mb-3">
                    <Button
                      variant={modo === "peticao" ? "dark" : "outline-dark"}
                      onClick={() => onModoChange?.("peticao")}
                      disabled={loading}
                    >
                      Enviar petição inicial
                    </Button>
                    <Button
                      variant={modo === "manual" ? "dark" : "outline-dark"}
                      onClick={() => onModoChange?.("manual")}
                      disabled={loading}
                    >
                      Preencher manualmente
                    </Button>
                  </ButtonGroup>
                  <h2 className="h3 mb-2">
                    {modo === "peticao"
                      ? "Geração automática a partir da petição"
                      : "Formulário para envio ao agente de IA"}
                  </h2>
                  <p className="text-secondary mb-0">
                    {modo === "peticao"
                      ? "Anexe a petição inicial — o sistema extrai os dados e gera a contestação."
                      : "Preencha os dados do caso, anexe a peça base e envie para automação."}
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
                      <div className="fw-semibold">Petição inicial (obrigatório)</div>
                      <small className="text-secondary">
                        Arraste ou clique para anexar PDF, DOC ou DOCX (até 20 MB).
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
                      <Form.Label>Modelo base do escritório</Form.Label>
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
                          Arraste ou clique para anexar o arquivo .docx.
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
                          <Form.Label>Tipo de ação (dica para a IA)</Form.Label>
                          <Form.Control
                            value={tipoAcaoHint || ""}
                            onChange={onTipoAcaoHintChange}
                            placeholder="Ex.: Trabalhista — Horas Extras"
                          />
                        </Form.Group>
                      </Col>
                      <Col xs={12}>
                        <Form.Group>
                          <Form.Label>Pontos específicos para atacar</Form.Label>
                          <Form.Control
                            as="textarea"
                            rows={4}
                            value={pontosContestante || ""}
                            onChange={onPontosContestanteChange}
                            placeholder="Ex.: prescrição bienal, ausência de prova testemunhal, valor da causa irreal"
                          />
                        </Form.Group>
                      </Col>
                    </Row>

                    {/* PR5 multi-docs: anexos opcionais (max 5, total 50MB) */}
                    <Form.Group className="mt-4">
                      <Form.Label>
                        Documentos da petição (para a IA ler)
                      </Form.Label>
                      <small
                        className="d-block mb-2"
                        style={{ color: "rgba(255, 255, 255, 0.7)" }}
                      >
                        Contratos, e-mails, laudos e outros documentos que ajudam a IA a entender o caso. Não vão para a peça final — só servem de contexto.
                      </small>
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

                    {/* PR15: provas embedaveis no docx final (FGTS/TRCT/laudos/prints) */}
                    <Form.Group className="mt-4">
                      <Form.Label>
                        Provas para a peça
                      </Form.Label>
                      <small
                        className="d-block mb-2"
                        style={{ color: "rgba(255, 255, 255, 0.7)" }}
                      >
                        Documentos que vão aparecer dentro da contestação como prova: FGTS, TRCT, folha de ponto, laudos, prints. Selecione o tipo de cada arquivo na lista.
                      </small>
                      <div className="d-flex align-items-center gap-2 flex-wrap">
                        <Button
                          type="button"
                          variant="outline-dark"
                          size="sm"
                          disabled={loading || embedFiles.length >= 10}
                          onClick={() => embedInputRef.current?.click()}
                        >
                          <Paperclip className="me-1" /> Adicionar prova
                        </Button>
                        <small className="text-secondary">
                          {embedFiles.length}/10 provas · JPG, PNG ou PDF (max 10MB cada)
                        </small>
                      </div>
                      <input
                        ref={embedInputRef}
                        type="file"
                        accept=".jpg,.jpeg,.png,.pdf"
                        className="d-none"
                        multiple
                        onChange={(event) => {
                          const files = Array.from(event.target.files || []);
                          for (const f of files) onAdicionarEmbed?.(f, "outro");
                          event.target.value = "";
                        }}
                      />
                      {embedFiles.length > 0 && (
                        <ul className="list-unstyled mt-2 mb-0">
                          {embedFiles.map((item, idx) => (
                            <li
                              key={`${item.file.name}-${idx}`}
                              className="upload-file-summary mt-2"
                            >
                              <div className="d-flex align-items-center gap-2 flex-grow-1">
                                <Paperclip />
                                <div className="flex-grow-1">
                                  <div className="fw-semibold">{item.file.name}</div>
                                  <small className="text-secondary">
                                    {fileSizeLabel(item.file)}
                                  </small>
                                </div>
                                <Form.Select
                                  size="sm"
                                  style={{ maxWidth: 200 }}
                                  value={item.tipo}
                                  onChange={(e) =>
                                    onChangeTipoEmbed?.(idx, e.target.value)
                                  }
                                  disabled={loading}
                                >
                                  <option value="folha_ponto">Folha de Ponto</option>
                                  <option value="fgts">Extrato FGTS</option>
                                  <option value="trct">TRCT</option>
                                  <option value="laudo_pericial">Laudo Pericial</option>
                                  <option value="contrato">Contrato</option>
                                  <option value="ctps">CTPS</option>
                                  <option value="print">Print/E-mail</option>
                                  <option value="outro">Outro</option>
                                </Form.Select>
                              </div>
                              <Button
                                type="button"
                                variant="link"
                                className="upload-remove p-0"
                                onClick={() => onRemoverEmbed?.(idx)}
                              >
                                <XCircle /> Remover
                              </Button>
                            </li>
                          ))}
                        </ul>
                      )}
                      {embedError && (
                        <div className="upload-feedback-error">{embedError}</div>
                      )}
                    </Form.Group>

                    <div className="d-flex flex-wrap gap-2 mt-4">
                      <Button type="submit" variant="dark" disabled={loading}>
                        {loading ? "Processando..." : "Gerar contestação automaticamente"}
                      </Button>
                    </div>
                  </Form>
                )}

                {modo === "manual" && (
                <Form onSubmit={onSubmit}>
                  <Row className="g-3">
                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Número do processo</Form.Label>
                        <IMaskInput
                          mask="0000000-00.0000.0.00.0000"
                          name="processo"
                          value={form.processo}
                          onAccept={(value) =>
                            onChange({ target: { name: "processo", value } })
                          }
                          placeholder="0001234-56.2026.8.00.0000"
                          className={`form-control ${formErrors.processo ? "is-invalid" : ""}`}
                          inputMode="numeric"
                        />
                        {formErrors.processo && (
                          <div className="invalid-feedback d-block">
                            {formErrors.processo}
                          </div>
                        )}
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Autor da ação</Form.Label>
                        <Form.Control
                          name="autor"
                          value={form.autor}
                          onChange={onChange}
                          placeholder="Nome do reclamante / autor"
                          isInvalid={Boolean(formErrors.autor)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.autor}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col md={6}>
                      <Form.Group>
                        <Form.Label>Réu (parte que você representa)</Form.Label>
                        <Form.Control
                          name="reu"
                          value={form.reu}
                          onChange={onChange}
                          placeholder="Nome da empresa / réu"
                          isInvalid={Boolean(formErrors.reu)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.reu}
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
                          {Object.entries(legalBranchGroups).map(([grupo, ramos]) => (
                            <optgroup key={grupo} label={grupo}>
                              {ramos.map((branch) => (
                                <option key={branch} value={branch}>
                                  {branch}
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </Form.Select>
                        <Form.Control.Feedback type="invalid">
                          {formErrors.tipoAcao}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    {subtiposAcao[form.tipoAcao] && (
                      <Col md={6}>
                        <Form.Group>
                          <Form.Label>Tipo específico da ação</Form.Label>
                          <Form.Select
                            name="subtipoAcao"
                            value={form.subtipoAcao || ""}
                            onChange={onChange}
                          >
                            <option value="">Selecione o tipo (opcional)</option>
                            {subtiposAcao[form.tipoAcao].map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </Form.Select>
                          <Form.Text className="text-secondary">
                            Subtipo melhora a busca de defesas similares (RAG).
                          </Form.Text>
                        </Form.Group>
                      </Col>
                    )}

                    <Col xs={12}>
                      <Form.Group>
                        <Form.Label>Fatos narrados pelo autor</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={3}
                          name="fatos"
                          value={form.fatos}
                          onChange={onChange}
                          placeholder="Resumo dos fatos conforme a petição inicial..."
                          isInvalid={Boolean(formErrors.fatos)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.fatos}
                        </Form.Control.Feedback>
                      </Form.Group>
                    </Col>

                    <Col xs={12}>
                      <Form.Group>
                        <Form.Label>Pedidos do autor</Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={2}
                          name="pedidoAutor"
                          value={form.pedidoAutor}
                          onChange={onChange}
                          placeholder="Ex.: Horas extras, FGTS, danos morais..."
                          isInvalid={Boolean(formErrors.pedidoAutor)}
                        />
                        <Form.Control.Feedback type="invalid">
                          {formErrors.pedidoAutor}
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

                    <Col xs={12}>
                      <Form.Label>Modelo base do escritório (papel timbrado / estilo)</Form.Label>
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
                          Anexe um .docx com o cabeçalho/estilo do escritório. A IA preserva o formato.
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

        </Row>
      </Container>
    </section>
  );
}
