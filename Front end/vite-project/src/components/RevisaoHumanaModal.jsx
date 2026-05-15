// Modal de revisao humana (PR5 HiL — Guia Tecnico v3 secao 2.1).
// Quando dados_confianca da IA fica abaixo do limiar, este modal aparece com
// os campos extraidos editaveis. Apos o advogado revisar, o frontend chama
// /confirmar-extracao para regenerar a minuta com os dados validados.
import React, { useState } from "react";
import { Alert, Button, Form, Modal, Spinner } from "react-bootstrap";

function dadosToFormState(dados) {
  return {
    autor: dados?.autor || "",
    reu: dados?.reu || "",
    numero_processo: dados?.numero_processo || "",
    tipo_acao: dados?.tipo_acao || "",
    vara: dados?.vara || "",
    fatos_resumo: dados?.fatos_resumo || "",
    pedidos: Array.isArray(dados?.pedidos)
      ? dados.pedidos.join("\n")
      : String(dados?.pedidos || ""),
    valor_total: dados?.valores?.total_estimado || "",
  };
}

export default function RevisaoHumanaModal({
  show,
  onHide,
  onConfirm,
  dadosExtraidos,
  confianca,
  loading,
  error,
}) {
  const [form, setForm] = useState(() => dadosToFormState(dadosExtraidos));
  // `touched` esta declarado mas atualmente nao e lido pela UI — guardado
  // como hook para uso futuro (ex: avisar usuario que ha alteracao nao salva
  // ao fechar o modal). Eslint disable enquanto isso.
  // eslint-disable-next-line no-unused-vars
  const [touched, setTouched] = useState(false);

  // Re-sync form quando dadosExtraidos mudar (caso o usuario abra outro caso).
  React.useEffect(() => {
    setForm(dadosToFormState(dadosExtraidos));
    setTouched(false);
  }, [dadosExtraidos]);

  const handleChange = (campo) => (e) => {
    setForm((prev) => ({ ...prev, [campo]: e.target.value }));
    setTouched(true);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (loading) return;
    const dadosCorrigidos = {
      ...dadosExtraidos,
      autor: form.autor.trim(),
      reu: form.reu.trim(),
      numero_processo: form.numero_processo.trim() || null,
      tipo_acao: form.tipo_acao.trim(),
      vara: form.vara.trim() || null,
      fatos_resumo: form.fatos_resumo.trim(),
      pedidos: form.pedidos
        .split("\n")
        .map((p) => p.trim())
        .filter(Boolean),
      valores: {
        ...(dadosExtraidos?.valores || {}),
        total_estimado: form.valor_total.trim() || null,
      },
      // Confianca passa a ser maxima porque o humano validou.
      confianca: 1.0,
    };
    onConfirm(dadosCorrigidos);
  };

  const confiancaLabel =
    typeof confianca === "number" ? confianca.toFixed(2) : "baixa";

  return (
    <Modal show={show} onHide={onHide} centered size="lg" backdrop="static">
      <Modal.Header closeButton>
        <Modal.Title>Revisao necessaria antes de gerar a contestacao</Modal.Title>
      </Modal.Header>

      <Form onSubmit={handleSubmit}>
        <Modal.Body>
          <Alert variant="warning" className="mb-3">
            A IA teve <strong>baixa confianca ({confiancaLabel})</strong> ao extrair
            os dados desta peticao. Revise e corrija os campos abaixo antes de
            gerar a minuta final.
          </Alert>

          {error && <Alert variant="danger">{error}</Alert>}

          <Form.Group className="mb-3">
            <Form.Label>Autor (reclamante)</Form.Label>
            <Form.Control
              value={form.autor}
              onChange={handleChange("autor")}
              required
              disabled={loading}
            />
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>Reu (reclamado)</Form.Label>
            <Form.Control
              value={form.reu}
              onChange={handleChange("reu")}
              disabled={loading}
            />
          </Form.Group>

          <div className="row g-2">
            <div className="col-md-6">
              <Form.Group className="mb-3">
                <Form.Label>Numero do processo (CNJ)</Form.Label>
                <Form.Control
                  value={form.numero_processo}
                  onChange={handleChange("numero_processo")}
                  placeholder="0001234-56.2026.8.00.0000"
                  disabled={loading}
                />
              </Form.Group>
            </div>
            <div className="col-md-6">
              <Form.Group className="mb-3">
                <Form.Label>Vara / tribunal</Form.Label>
                <Form.Control
                  value={form.vara}
                  onChange={handleChange("vara")}
                  disabled={loading}
                />
              </Form.Group>
            </div>
          </div>

          <Form.Group className="mb-3">
            <Form.Label>Tipo de acao</Form.Label>
            <Form.Control
              value={form.tipo_acao}
              onChange={handleChange("tipo_acao")}
              required
              disabled={loading}
            />
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>Resumo dos fatos (na voz do autor)</Form.Label>
            <Form.Control
              as="textarea"
              rows={5}
              value={form.fatos_resumo}
              onChange={handleChange("fatos_resumo")}
              disabled={loading}
            />
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>Pedidos do autor (1 por linha)</Form.Label>
            <Form.Control
              as="textarea"
              rows={4}
              value={form.pedidos}
              onChange={handleChange("pedidos")}
              disabled={loading}
              placeholder={"Horas extras\nAdicional noturno\n..."}
            />
          </Form.Group>

          <Form.Group className="mb-1">
            <Form.Label>Valor da causa (opcional)</Form.Label>
            <Form.Control
              value={form.valor_total}
              onChange={handleChange("valor_total")}
              placeholder="R$ 27.598,41"
              disabled={loading}
            />
          </Form.Group>
        </Modal.Body>

        <Modal.Footer>
          <Button variant="outline-secondary" onClick={onHide} disabled={loading}>
            Cancelar
          </Button>
          <Button type="submit" variant="dark" disabled={loading || !form.autor || !form.tipo_acao}>
            {loading ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Gerando...
              </>
            ) : (
              "Confirmar e gerar contestacao"
            )}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
