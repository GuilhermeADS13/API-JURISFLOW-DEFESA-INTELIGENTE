// PR23 - Aba "Listar/Editar/Excluir" dentro da pagina admin de Jurisprudencia.
// Tabela paginada com filtros, botoes editar (abre modal com JurisprudenciaForm
// em modo edit) e excluir (confirm dialog).
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Col,
  Form,
  Modal,
  Pagination,
  Row,
  Spinner,
  Table,
} from "react-bootstrap";
import { ArrowClockwise, PencilSquare, Trash } from "react-bootstrap-icons";
import {
  JURISPRUDENCIA_LISTAR_URL,
  jurisprudenciaIdUrl,
} from "../config/api";
import JurisprudenciaForm from "./JurisprudenciaForm";

const PAGE_SIZE = 25;

const TRIBUNAIS_FILTRO = ["", "TST", "STJ", "STF", "TJ-PE", "TJ-SP", "TJ-RJ"];
const AREAS_FILTRO = ["", "trabalhista", "civel", "consumidor"];

function truncar(s, n = 180) {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n)}...` : s;
}

/**
 * Lista paginada de jurisprudencia com filtros + acoes de edicao/exclusao.
 *
 * Props:
 *  - getAccessToken: () => Promise<string|null>
 */
export default function JurisprudenciaListaTab({ getAccessToken }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0); // 0-indexed
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [filtros, setFiltros] = useState({
    tribunal: "",
    area_juridica: "",
    busca: "",
  });
  // PR27 (finding #4): busca separada com debounce 300ms. Antes: cada
  // keystroke em `filtros.busca` disparava fetch. Agora: `buscaInput` reflete
  // o input imediatamente, `filtros.busca` so muda apos 300ms de idle.
  const [buscaInput, setBuscaInput] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      setFiltros((f) => (f.busca === buscaInput ? f : { ...f, busca: buscaInput }));
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [buscaInput]);

  const [editando, setEditando] = useState(null); // item completo do backend
  const [confirmandoDelete, setConfirmandoDelete] = useState(null);
  const [deletando, setDeletando] = useState(false);
  const [feedbackGlobal, setFeedbackGlobal] = useState(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const token = await getAccessToken();
      if (!token) {
        setErro("Sessao expirada. Faca login novamente.");
        setLoading(false);
        return;
      }
      // Paginacao client-side: busca TODAS as linhas do filtro de uma vez e
      // pagina no navegador — trocar de pagina fica instantaneo (sem novo
      // round-trip ao pooler, que custava ~500ms-9s por pagina).
      const params = new URLSearchParams({
        limit: "500",
        offset: "0",
      });
      if (filtros.tribunal) params.set("tribunal", filtros.tribunal);
      if (filtros.area_juridica) params.set("area_juridica", filtros.area_juridica);
      if (filtros.busca?.trim()) params.set("busca", filtros.busca.trim());

      const resp = await fetch(`${JURISPRUDENCIA_LISTAR_URL}?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 403) {
        setErro("Acesso negado: seu email nao esta na lista ADMIN_EMAILS.");
        return;
      }
      if (!resp.ok) {
        const txt = await resp.text();
        setErro(`Erro ${resp.status}: ${txt.slice(0, 160)}`);
        return;
      }
      const data = await resp.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setErro(`Falha de rede: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }, [filtros, getAccessToken]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Qualquer mudanca de filtro volta pra pagina 1 (evita pagina fora do range).
  useEffect(() => {
    setPage(0);
  }, [filtros]);

  // Fatia da pagina atual — paginacao 100% no cliente sobre `items` (ja tem tudo).
  const pageItems = items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSearch = (e) => {
    e.preventDefault();
    setPage(0);
    carregar();
  };

  const handleResetFiltros = () => {
    setFiltros({ tribunal: "", area_juridica: "", busca: "" });
    setBuscaInput("");
    setPage(0);
  };

  const handleEdit = async (item) => {
    // PR27 (finding #1): fetch completo por id ANTES de abrir modal. O endpoint
    // /listar retorna apenas 'tem_texto_integral: bool' (payload leve). Sem
    // este fetch, edit modal abriria com texto_integral vazio e um PATCH
    // apagaria o campo silenciosamente. Agora, se GET /{id} falhar,
    // caimos no item da lista com warning — melhor abrir edit incompleto
    // que quebrar o fluxo.
    try {
      const token = await getAccessToken();
      const resp = await fetch(jurisprudenciaIdUrl(item.id), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const completo = await resp.json();
        setEditando(completo);
        return;
      }
      console.warn(
        `Falha ao buscar detalhe id=${item.id} (HTTP ${resp.status}); ` +
        `abrindo com dados parciais da lista.`,
      );
    } catch (err) {
      console.warn(`Erro de rede ao buscar detalhe id=${item.id}:`, err);
    }
    setEditando(item);
  };

  const handleConfirmDelete = (item) => {
    setConfirmandoDelete(item);
  };

  const executarDelete = async () => {
    if (!confirmandoDelete) return;
    setDeletando(true);
    try {
      const token = await getAccessToken();
      const resp = await fetch(jurisprudenciaIdUrl(confirmandoDelete.id), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        const txt = await resp.text();
        setFeedbackGlobal({
          variant: "danger",
          text: `Falha ao excluir: ${txt.slice(0, 200)}`,
        });
      } else {
        setFeedbackGlobal({
          variant: "success",
          text: `id=${confirmandoDelete.id} (${confirmandoDelete.tribunal} ${confirmandoDelete.numero_processo}) removida.`,
        });
        await carregar();
      }
    } catch (err) {
      setFeedbackGlobal({
        variant: "danger",
        text: `Falha de rede: ${err.message || err}`,
      });
    } finally {
      setDeletando(false);
      setConfirmandoDelete(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      {feedbackGlobal && (
        <Alert
          variant={feedbackGlobal.variant}
          onClose={() => setFeedbackGlobal(null)}
          dismissible
        >
          {feedbackGlobal.text}
        </Alert>
      )}

      <Form onSubmit={handleSearch} className="mb-3">
        <Row className="g-2 align-items-end">
          <Col md={4}>
            <Form.Label className="small mb-1">Tribunal</Form.Label>
            <Form.Select
              size="sm"
              value={filtros.tribunal}
              onChange={(e) => setFiltros((f) => ({ ...f, tribunal: e.target.value }))}
            >
              {TRIBUNAIS_FILTRO.map((t) => (
                <option key={t} value={t}>{t || "(todos)"}</option>
              ))}
            </Form.Select>
          </Col>
          <Col md={4}>
            <Form.Label className="small mb-1">Area</Form.Label>
            <Form.Select
              size="sm"
              value={filtros.area_juridica}
              onChange={(e) => setFiltros((f) => ({ ...f, area_juridica: e.target.value }))}
            >
              {AREAS_FILTRO.map((a) => (
                <option key={a} value={a}>{a || "(todas)"}</option>
              ))}
            </Form.Select>
          </Col>
          <Col md={4}>
            <Form.Label className="small mb-1">
              Busca (numero, ementa ou relator)
            </Form.Label>
            <Form.Control
              size="sm"
              type="text"
              placeholder="ex: intervalo, Sum. 437, Min. Delgado..."
              value={buscaInput}
              onChange={(e) => setBuscaInput(e.target.value)}
            />
          </Col>
          <Col md={12} className="d-flex gap-2 justify-content-end mt-2">
            <Button
              size="sm"
              type="submit"
              variant="primary"
              disabled={loading}
            >
              Filtrar
            </Button>
            <Button
              size="sm"
              type="button"
              variant="outline-secondary"
              onClick={handleResetFiltros}
              disabled={loading}
            >
              Limpar filtros
            </Button>
            <Button
              size="sm"
              type="button"
              variant="outline-primary"
              onClick={() => carregar()}
              title="Recarregar"
              disabled={loading}
            >
              <ArrowClockwise />
            </Button>
          </Col>
        </Row>
      </Form>

      {erro && <Alert variant="danger">{erro}</Alert>}

      <div className="d-flex justify-content-between align-items-center mb-2">
        <span className="jur-resultbar">
          {loading
            ? "Carregando…"
            : `${total} resultado${total === 1 ? "" : "s"} · página ${page + 1} de ${totalPages}`}
        </span>
      </div>

      <div className="table-responsive">
        <Table striped hover size="sm">
          <thead>
            <tr>
              <th style={{ width: 64 }}>Trib.</th>
              <th style={{ width: 190 }}>Número</th>
              <th style={{ width: 110 }}>Tipo</th>
              <th>Ementa</th>
              <th style={{ width: 90 }}>Peso</th>
              <th style={{ width: 100 }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && (
              <tr>
                <td colSpan={6} className="jur-empty">
                  <Spinner size="sm" animation="border" /> Carregando...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={6} className="jur-empty">
                  Nenhum acórdão encontrado. Ajuste os filtros ou cadastre um
                  novo na aba "Adicionar novo".
                </td>
              </tr>
            )}
            {pageItems.map((item) => (
              <tr key={item.id}>
                <td><span className="jur-trib">{item.tribunal}</span></td>
                <td><span className="jur-num">{item.numero_processo}</span></td>
                <td><span className="jur-tipo">{item.tipo_decisao}</span></td>
                <td>
                  <div className="jur-ementa" title={item.ementa}>
                    {truncar(item.ementa, 220)}
                  </div>
                </td>
                <td>
                  <span
                    className={`jur-peso ${
                      item.peso_relevancia >= 9
                        ? "jur-peso-alto"
                        : item.peso_relevancia >= 6
                          ? "jur-peso-medio"
                          : "jur-peso-baixo"
                    }`}
                    title={`Relevância ${item.peso_relevancia}/10`}
                  >
                    {item.peso_relevancia}
                  </span>
                  {item.tem_texto_integral && (
                    <span className="jur-flag jur-flag-ti" title="Texto integral disponível">
                      TI
                    </span>
                  )}
                  {!item.tem_embedding && (
                    <span className="jur-flag jur-flag-noemb" title="Sem embedding — busca semântica não retorna">
                      !
                    </span>
                  )}
                </td>
                <td>
                  <button
                    type="button"
                    className="jur-acao me-1"
                    onClick={() => handleEdit(item)}
                    title="Editar"
                  >
                    <PencilSquare size={15} />
                  </button>
                  <button
                    type="button"
                    className="jur-acao jur-acao-del"
                    onClick={() => handleConfirmDelete(item)}
                    title="Excluir"
                  >
                    <Trash size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>

      {totalPages > 1 && (
        <Pagination size="sm" className="justify-content-center">
          <Pagination.First disabled={page === 0} onClick={() => setPage(0)} />
          <Pagination.Prev
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          />
          <Pagination.Item active>{page + 1}</Pagination.Item>
          <Pagination.Next
            disabled={page + 1 >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          />
          <Pagination.Last
            disabled={page + 1 >= totalPages}
            onClick={() => setPage(totalPages - 1)}
          />
        </Pagination>
      )}

      {/* Modal edicao */}
      <Modal
        show={Boolean(editando)}
        onHide={() => setEditando(null)}
        size="lg"
        backdrop="static"
        dialogClassName="jur-modal"
        contentClassName="jur-admin"
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Editar — {editando?.tribunal} {editando?.numero_processo}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {editando && (
            <JurisprudenciaForm
              getAccessToken={getAccessToken}
              editingItem={editando}
              compact
              onSaved={() => {
                setEditando(null);
                setFeedbackGlobal({
                  variant: "success",
                  text: "Alteracoes salvas.",
                });
                carregar();
              }}
            />
          )}
        </Modal.Body>
      </Modal>

      {/* Modal confirm delete */}
      <Modal
        show={Boolean(confirmandoDelete)}
        onHide={() => setConfirmandoDelete(null)}
        centered
        dialogClassName="jur-modal"
        contentClassName="jur-admin"
      >
        <Modal.Header closeButton>
          <Modal.Title>Confirmar exclusão</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            Excluir <strong>{confirmandoDelete?.tribunal} {confirmandoDelete?.numero_processo}</strong>?
          </p>
          <p className="text-muted small mb-0">
            Esta acao remove o paradigma do RAG. Nao ha desfazer — voce
            precisaria cadastrar novamente para restaurar.
          </p>
        </Modal.Body>
        <Modal.Footer>
          <Button
            variant="outline-secondary"
            onClick={() => setConfirmandoDelete(null)}
            disabled={deletando}
          >
            Cancelar
          </Button>
          <Button variant="danger" onClick={executarDelete} disabled={deletando}>
            {deletando ? <Spinner size="sm" animation="border" /> : "Excluir"}
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
