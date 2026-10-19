// Executa Code nodes dos workflows n8n com $helpers.httpRequest simulado.
// Sem rede e sem custo: a API do Claude e simulada e cada request e inspecionado.
// Uso (na raiz do repo): node scripts/test_n8n_workflows.mjs
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const ROOT = process.argv[2] || '.';
const wf = (f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'docs', f), 'utf8'));
const code = (f, nome) => wf(f).nodes.find((n) => n.name === nome).parameters.jsCode;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const minuta = {
  resumo_estrategico: 'r', tese_central: 'tese', preliminares: 'prel', merito: 'merito',
  fundamentos: 'art. 818 CLT', pedidos: 'improcedencia',
  litigancia_ma_fe: 'LITIG RR-20200-97.2008.5.04.0232', danos_morais: 'DANOS art. 223-G CLT',
  autenticidade_documentos: 'AUT art. 830 CLT', encerramento: 'ENC art. 767 CLT', observacoes: 'obs',
};

function claudeOk(texto, extra = {}) {
  return { statusCode: 200, body: { content: [{ type: 'text', text: texto }], usage: { input_tokens: 1_000_000, output_tokens: 1_000_000 }, stop_reason: 'end_turn', ...extra } };
}

async function rodar(arquivo, nome, envelope, env, resposta) {
  const chamadas = [];
  const $helpers = {
    httpRequest: async (opts) => {
      chamadas.push(opts);
      if (typeof resposta === 'function') return resposta(opts, chamadas.length);
      return resposta;
    },
  };
  // setTimeout instantaneo: o backoff do retry nao atrasa o teste.
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn) => realSetTimeout(fn, 0);
  try {
    const fn = new AsyncFunction('$input', '$helpers', '$env', '$vars', code(arquivo, nome));
    const out = await fn.call({}, { first: () => ({ json: envelope }), all: () => [{ json: envelope }] }, $helpers, env, undefined);
    return { out: out[0].json, chamadas };
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
}

const P = 'n8n_workflow_contestar_por_peticao.json';
const ENV = { ANTHROPIC_API_KEY: 'x', CLAUDE_MODEL: 'claude-opus-5', CLAUDE_EXTRACAO_MODEL: 'claude-sonnet-5', CLAUDE_VERIFICACAO_MODEL: 'claude-haiku-4-5' };
const bodyDe = (c) => (typeof c.body === 'string' ? JSON.parse(c.body) : c.body);
let ok = 0, falhas = 0;
const caso = async (nome, fn) => {
  try { await fn(); ok++; console.log('  ok -', nome); }
  catch (e) { falhas++; console.log('  FALHA -', nome, '|', String(e.message).split('\n')[0].slice(0, 100)); }
};

const envGerador = {
  status: 'dados_extraidos',
  dados_extraidos: { autor: 'A', reu: 'R', tipo_acao: 'Trabalhista - Horas Extras', pedidos: ['horas extras'], data_ajuizamento: '15/03/2024' },
  contexto: {},
  exemplares_fewshot: [{ tipo_acao: 'Trabalhista', tese_central: 'TESE_FEWSHOT_X', fundamentos_resumo: 'f' }],
};
const jsonMinuta = JSON.stringify(minuta);

console.log('Gerador');
await caso('opus-5 nao recebe temperature; custo usa US$5/25', async () => {
  const { out, chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, ENV, claudeOk(jsonMinuta));
  const b = bodyDe(chamadas[0]);
  assert.equal('temperature' in b, false);
  assert.equal(out.engine_ia.custo_estimado_usd, 30); // 1M in * 5 + 1M out * 25
});
await caso('haiku-4-5 (aceita) ainda recebe temperature', async () => {
  const { chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, { ...ENV, CLAUDE_MODEL: 'claude-haiku-4-5' }, claudeOk(jsonMinuta));
  assert.equal(bodyDe(chamadas[0]).temperature, 0.12);
});
await caso('sonnet-5-5 / haiku-5-5 / opus-4-8 nao recebem temperature', async () => {
  for (const m of ['claude-sonnet-5-5', 'claude-haiku-5-5', 'claude-opus-4-8', 'claude-opus-5-5']) {
    const { chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, { ...ENV, CLAUDE_MODEL: m }, claudeOk(jsonMinuta));
    assert.equal('temperature' in bodyDe(chamadas[0]), false, m);
  }
});
await caso('few-shot sai do system e vai pra mensagem do caso', async () => {
  const { chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, ENV, claudeOk(jsonMinuta));
  const b = bodyDe(chamadas[0]);
  assert.equal(b.system[0].text.includes('TESE_FEWSHOT_X'), false);
  assert.ok(JSON.stringify(b.messages).includes('TESE_FEWSHOT_X'));
});
await caso('regra de numeracao nao se contradiz mais', async () => {
  const { chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, ENV, claudeOk(jsonMinuta));
  const linha = bodyDe(chamadas[0]).system[0].text.split('\n').find((l) => l.includes('NUMERACAO DE PARAGRAFOS'));
  assert.ok(linha.includes('NAO numere'));
  assert.equal(/use APENAS UMA numeracao/.test(linha), false);
});
await caso('timeout do cliente NAO repete a geracao (1 chamada)', async () => {
  const { out, chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, ENV, () => {
    const e = new Error('timeout of 480000ms exceeded'); e.code = 'ECONNABORTED'; throw e;
  });
  assert.equal(chamadas.length, 1);
  assert.match(out.engine_ia.api_error, /HTTP 408/);
});
await caso('529 rapido continua sendo repetido (3 chamadas)', async () => {
  const { chamadas } = await rodar(P, 'Claude Gerador de Contestacao', envGerador, ENV, { statusCode: 529, body: { error: 'overloaded' } });
  assert.equal(chamadas.length, 3);
});

const comDefesa = (caso, numeroAtual = '0001111-11.2026.5.06.0001') => ({
  ...envGerador,
  dados_extraidos: { ...envGerador.dados_extraidos, numero_processo: numeroAtual },
  defesas_anteriores: { casos: [{ tese_central: 'TESE_DO_RAG_X', fundamentos_curtos: 'f', ...caso }] },
});
const textoUser = (chamadas) => JSON.stringify(bodyDe(chamadas[0]).messages);
await caso('tese do RAG pouco parecida vira REFERENCIA (nao copia literal)', async () => {
  const { out, chamadas } = await rodar(P, 'Claude Gerador de Contestacao', comDefesa({ similaridade_semantica: 0.55 }), ENV, claudeOk(jsonMinuta));
  assert.equal(out.engine_ia.tese_rag.modo, 'referencia');
  assert.ok(textoUser(chamadas).includes('CASO APENAS PARECIDO'));
  assert.equal(textoUser(chamadas).includes('REPLIQUE LITERALMENTE'), false);
});
await caso('lexical-only (sem cosseno) tambem vira REFERENCIA', async () => {
  const { out } = await rodar(P, 'Claude Gerador de Contestacao', comDefesa({ similaridade_semantica: null, similarity: 1.0 }), ENV, claudeOk(jsonMinuta));
  assert.equal(out.engine_ia.tese_rag.modo, 'referencia');
});
await caso('caso quase identico (cosseno >= 0.80) mantem tese literal', async () => {
  const { out, chamadas } = await rodar(P, 'Claude Gerador de Contestacao', comDefesa({ similaridade_semantica: 0.91 }), ENV, claudeOk(jsonMinuta));
  assert.equal(out.engine_ia.tese_rag.modo, 'literal');
  assert.ok(textoUser(chamadas).includes('REPLIQUE LITERALMENTE'));
});
await caso('mesmo processo mantem tese literal mesmo sem cosseno', async () => {
  const { out } = await rodar(P, 'Claude Gerador de Contestacao', comDefesa({ numero_processo: '0001111-11.2026.5.06.0001', similaridade_semantica: null }), ENV, claudeOk(jsonMinuta));
  assert.equal(out.engine_ia.tese_rag.modo, 'literal');
});

console.log('Extrator');
await caso('prompt sem comentario de codigo e sem temperature no sonnet-5', async () => {
  const envE = { status: 'ok', contexto: { texto_peticao: 'x'.repeat(100) } };
  const { chamadas } = await rodar(P, 'Claude Extrator', envE, ENV, claudeOk('{"autor":"A","confianca":0.9}'));
  const b = bodyDe(chamadas[0]);
  assert.equal(JSON.stringify(b.messages).includes('PR18_DADOS_REU'), false);
  assert.equal('temperature' in b, false);
});

console.log('Self-Correction');
await caso('verifica litigancia, danos morais, autenticidade e encerramento', async () => {
  const { chamadas } = await rodar(P, 'Self-Correction Citacoes', { status: 'ok', minuta }, ENV, claudeOk('{"citacoes":[]}'));
  const texto = JSON.stringify(bodyDe(chamadas[0]).messages);
  for (const s of ['LITIG RR-20200', 'DANOS', 'AUT art. 830', 'ENC art. 767']) assert.ok(texto.includes(s), s);
});

console.log('Detector');
await caso('resposta truncada vira erro explicito, nao "sem contradicoes"', async () => {
  const { out, chamadas } = await rodar(P, 'Detector de Contradicoes', { status: 'ok', minuta, dados_extraidos: {} }, ENV,
    claudeOk('{"contradicoes":[{"tipo":"data"', { stop_reason: 'max_tokens' }));
  assert.equal(bodyDe(chamadas[0]).max_tokens, 4000);
  const det = Object.values(out).find((v) => v && typeof v === 'object' && 'api_error' in v && 'provider' in v && v !== out.engine_ia);
  assert.match(String(det && det.api_error), /truncada/);
});
await caso('Detector nao trata a defesa negando fatos do autor como erro', async () => {
  const { chamadas } = await rodar(P, 'Detector de Contradicoes', { status: 'ok', minuta, dados_extraidos: {} }, ENV, claudeOk('{"contradicoes":[]}'));
  const sistema = JSON.stringify(bodyDe(chamadas[0]).system);
  assert.ok(sistema.includes('NAO e erro'));
  assert.ok(sistema.includes('PEDIDO DO AUTOR SEM IMPUGNACAO'));
});

for (const [arquivo, nome, envelope] of [
  ['n8n_workflow_editar_contestacao.json', 'Agente Claude (Modo Extracao)', { status: 'ok', contexto: {}, texto_documento: 'x'.repeat(200), instrucoes: 'trocar autor' }],
  ['n8n_workflow_contestacao_claude.json', 'Agente IA Claude Anthropic', { status: 'ok', dados: { numero_processo: '1', autor: 'A', reu: 'R', tipo_acao: 'Trabalhista' }, contexto: {} }],
]) {
  console.log(nome);
  await caso('opus-5 nao recebe temperature (antes: HTTP 400 sempre)', async () => {
    const { chamadas } = await rodar(arquivo, nome, envelope, ENV, claudeOk('{}'));
    assert.ok(chamadas.length >= 1, 'chamou a API');
    assert.equal('temperature' in bodyDe(chamadas[0]), false);
  });
  await caso('haiku-4-5 continua recebendo temperature', async () => {
    const { chamadas } = await rodar(arquivo, nome, envelope, { ...ENV, CLAUDE_MODEL: 'claude-haiku-4-5' }, claudeOk('{}'));
    assert.ok('temperature' in bodyDe(chamadas[0]));
  });
}
console.log(`\n${ok} casos passaram, ${falhas} falharam`);
process.exitCode = falhas ? 1 : 0;
