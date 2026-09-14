"use strict";

/*
 * Área administrativa do Sá Conecta.
 *
 * Este arquivo controla o login, a sessão e a revisão dos contatos.
 * A senha é enviada somente no login. Depois disso, o navegador usa
 * um cookie HttpOnly criado pelo servidor e um token de proteção CSRF.
 */

const selecionar = (seletor) => document.querySelector(seletor);
let tokenCsrf = "";


// Funções auxiliares

function mostrarMensagem(elemento, mensagem, tipo = "error") {
  elemento.textContent = mensagem;
  elemento.dataset.kind = tipo;
  elemento.hidden = !mensagem;
}

function criarElemento(tag, texto, classe = "") {
  const elemento = document.createElement(tag);
  elemento.textContent = texto;
  elemento.className = classe;
  return elemento;
}

async function consultarApi(caminho, metodo = "GET", dados) {
  const controlador = new AbortController();
  const limite = setTimeout(() => controlador.abort(), 20000);

  try {
    const cabecalhos = { "X-Requested-With": "SaConecta" };

    if (dados !== undefined) {
      cabecalhos["Content-Type"] = "application/json";
    }
    if (tokenCsrf && metodo !== "GET") {
      cabecalhos["X-CSRF-Token"] = tokenCsrf;
    }

    const resposta = await fetch(caminho, {
      method: metodo,
      headers: cabecalhos,
      credentials: "same-origin",
      cache: "no-store",
      signal: controlador.signal,
      body: dados === undefined ? undefined : JSON.stringify(dados),
    });

    const resultado = await resposta.json();

    // Se a sessão expirou no painel, volta imediatamente para o login.
    if (resposta.status === 401 && document.body.dataset.page === "admin") {
      selecionar("#records").replaceChildren();
      location.replace("/admin/login");
      throw new Error("Sessão encerrada. Entre novamente.");
    }

    if (!resposta.ok) {
      const mensagem = typeof resultado.detail === "string"
        ? resultado.detail
        : "Confira os campos obrigatórios, o telefone com DDD e os limites de tamanho.";
      throw new Error(mensagem);
    }

    return resultado;
  } catch (erro) {
    const falhaDeConexao = ["AbortError", "TypeError", "SyntaxError"]
      .includes(erro.name);

    if (falhaDeConexao) {
      const mensagem = metodo === "GET"
        ? "Não foi possível carregar os dados. Confira o servidor e tente atualizar a lista."
        : "Não foi possível confirmar a ação. Atualize a lista antes de tentar novamente; a alteração pode ter sido salva.";
      throw new Error(mensagem);
    }
    throw erro;
  } finally {
    clearTimeout(limite);
  }
}


// Página de login

if (document.body.dataset.page === "login") {
  selecionar("#login-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();

    const botaoEntrar = selecionar("#login-submit");
    if (botaoEntrar.disabled) return;

    botaoEntrar.disabled = true;
    mostrarMensagem(selecionar("#login-error"), "");

    try {
      await consultarApi("/api/admin/login", "POST", {
        username: selecionar("#username").value,
        password: selecionar("#password").value,
      });

      selecionar("#password").value = "";
      location.replace("/admin");
    } catch (erro) {
      mostrarMensagem(selecionar("#login-error"), erro.message);
    } finally {
      botaoEntrar.disabled = false;
    }
  });
} else {
  iniciarPainelAdministrativo();
}


// Painel administrativo

function iniciarPainelAdministrativo() {
  let contatos = [];
  let filtroSelecionado = "pending";
  let contatoEmEdicao = null;
  let confirmacaoAtual = null;
  let painelOcupado = false;
  let listaCarregando = false;

  const nomesDosStatus = {
    pending: "Pendente",
    approved: "Aprovado",
    rejected: "Rejeitado",
  };

  function normalizar(valor) {
    return String(valor || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function alterarEstadoOcupado(valor) {
    painelOcupado = valor;

    document.querySelectorAll(
      "dialog button, dialog input, dialog select, dialog textarea, #logout",
    ).forEach((elemento) => {
      elemento.disabled = valor;
    });
  }

  function abrirEdicao(contato) {
    if (painelOcupado) return;

    contatoEmEdicao = contato;
    const campos = [
      "name",
      "category",
      "phone",
      "address",
      "hours",
      "description",
    ];

    campos.forEach((campo) => {
      selecionar(`#edit-${campo}`).value = contato[campo] || "";
    });

    selecionar("#edit-whatsapp").checked = Boolean(contato.whatsapp);
    selecionar("#edit-phone").required = !contato.is_demo;
    selecionar("#edit-title").textContent = `Editar contato #${contato.id}`;

    selecionar("#edit-note").textContent = contato.is_demo
      ? "Este cadastro continuará marcado como exemplo fictício."
      : `Situação: ${nomesDosStatus[contato.status]}. Salvar não altera a situação. Alterações em aprovados aparecem no catálogo.`;

    mostrarMensagem(selecionar("#edit-error"), "");
    selecionar("#edit-dialog").showModal();
  }

  function pedirConfirmacao(contato, acao) {
    if (painelOcupado) return;

    confirmacaoAtual = { contato, acao };

    const titulos = {
      approved: "Publicar este contato?",
      rejected: "Rejeitar este contato?",
      pending: "Devolver para revisão?",
      delete: "Excluir definitivamente?",
    };

    const descricoes = {
      approved: "Ele ficará visível no guia público.",
      rejected: "Ele ficará na lista de rejeitados e não aparecerá no guia.",
      pending: "Ele ficará pendente e não aparecerá no guia.",
      delete: "O cadastro será removido do banco. Esta ação não pode ser desfeita pelo painel.",
    };

    selecionar("#confirm-title").textContent = titulos[acao];
    selecionar("#confirm-description").textContent =
      `${contato.name} · protocolo ${contato.id}\n\n${descricoes[acao]}`;

    const botaoConfirmar = selecionar("#confirm-action");
    botaoConfirmar.textContent = acao === "delete"
      ? "Excluir definitivamente"
      : "Confirmar";
    botaoConfirmar.className = acao === "delete"
      ? "button danger"
      : "button primary";

    mostrarMensagem(selecionar("#confirm-error"), "");
    selecionar("#confirm-dialog").showModal();
  }

  function atualizarContadores() {
    ["pending", "approved", "rejected", "all"].forEach((status) => {
      selecionar(`#count-${status}`).textContent = contatos.filter(
        (contato) => status === "all" || contato.status === status,
      ).length;
    });
  }

  function criarCardDoContato(contato) {
    const card = criarElemento("article", "", "record");
    const cabecalho = criarElemento("div", "", "record-heading");
    const titulo = criarElemento("div", "");

    const complemento = contato.is_demo ? " · Exemplo fictício" : "";
    titulo.append(
      criarElemento("h2", contato.name),
      criarElemento(
        "p",
        `#${contato.id} · ${contato.category}${complemento}`,
        "record-meta",
      ),
    );

    const status = criarElemento(
      "span",
      nomesDosStatus[contato.status],
      "record-status",
    );
    status.dataset.status = contato.status;
    cabecalho.append(titulo, status);

    const detalhes = criarElemento("dl", "", "record-details");
    const informacoes = [
      ["Telefone", contato.phone || "Não informado"],
      ["WhatsApp", contato.whatsapp ? "Sim" : "Não informado"],
      ["Endereço", contato.address],
      ["Horário", contato.hours || "Não informado"],
      ["Descrição", contato.description],
    ];

    informacoes.forEach(([rotulo, valor]) => {
      detalhes.append(
        criarElemento("dt", rotulo),
        criarElemento("dd", valor),
      );
    });

    const acoes = criarElemento("div", "", "record-actions");
    const editar = criarElemento("button", "Editar", "button secondary");
    editar.addEventListener("click", () => abrirEdicao(contato));
    acoes.append(editar);

    const acoesDisponiveis = [
      ["approved", "Aprovar"],
      ["rejected", "Rejeitar"],
      ["pending", "Revisar"],
      ["delete", "Excluir"],
    ];

    acoesDisponiveis.forEach(([acao, rotulo]) => {
      if (contato.status === acao) return;

      const classe = acao === "approved"
        ? "button primary"
        : "button secondary";
      const botao = criarElemento("button", rotulo, classe);

      botao.setAttribute("aria-label", `${rotulo}: ${contato.name}`);
      botao.addEventListener("click", () => pedirConfirmacao(contato, acao));
      acoes.append(botao);
    });

    card.append(cabecalho, detalhes, acoes);
    return card;
  }

  function renderizarContatos() {
    atualizarContadores();

    document.querySelectorAll("[data-status].status-filter").forEach((botao) => {
      const selecionado = botao.dataset.status === filtroSelecionado;
      botao.setAttribute("aria-pressed", String(selecionado));
    });

    const busca = normalizar(selecionar("#admin-search").value.trim());
    const contatosFiltrados = contatos.filter((contato) => {
      const correspondeAoStatus = filtroSelecionado === "all"
        || contato.status === filtroSelecionado;
      const texto = normalizar([
        contato.name,
        contato.category,
        contato.phone,
        contato.address,
      ].join(" "));

      return correspondeAoStatus && texto.includes(busca);
    });

    selecionar("#records").replaceChildren(
      ...contatosFiltrados.map(criarCardDoContato),
    );

    selecionar("#admin-empty").hidden = contatosFiltrados.length !== 0;
    selecionar("#load-status").textContent = contatosFiltrados.length === 1
      ? "1 contato nesta seleção"
      : `${contatosFiltrados.length} contatos nesta seleção`;
  }

  async function carregarContatos() {
    if (listaCarregando) return;

    listaCarregando = true;
    selecionar("#reload").disabled = true;
    selecionar("#load-status").textContent = "Carregando contatos…";

    try {
      contatos = await consultarApi("/api/admin/contatos");
      renderizarContatos();
    } catch (erro) {
      selecionar("#load-status").textContent = "Lista não atualizada.";
      mostrarMensagem(selecionar("#admin-feedback"), erro.message);
    } finally {
      listaCarregando = false;
      selecionar("#reload").disabled = false;
    }
  }


  // Eventos do painel

  selecionar("#reload").addEventListener("click", () => {
    mostrarMensagem(selecionar("#admin-feedback"), "");
    carregarContatos();
  });

  selecionar("#admin-search").addEventListener("input", renderizarContatos);

  document.querySelectorAll(".status-filter").forEach((botao) => {
    botao.addEventListener("click", () => {
      filtroSelecionado = botao.dataset.status;
      renderizarContatos();
    });
  });

  document.querySelectorAll("[data-close]").forEach((botao) => {
    botao.addEventListener("click", () => {
      if (!painelOcupado) botao.closest("dialog").close();
    });
  });

  document.querySelectorAll("dialog").forEach((dialogo) => {
    dialogo.addEventListener("cancel", (evento) => {
      if (painelOcupado) evento.preventDefault();
    });
  });

  selecionar("#edit-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (painelOcupado || !contatoEmEdicao) return;

    const dados = {
      revision: contatoEmEdicao.revision,
      whatsapp: selecionar("#edit-whatsapp").checked,
    };

    ["name", "category", "phone", "address", "hours", "description"]
      .forEach((campo) => {
        dados[campo] = selecionar(`#edit-${campo}`).value;
      });

    alterarEstadoOcupado(true);
    mostrarMensagem(selecionar("#edit-error"), "");

    try {
      const resultado = await consultarApi(
        `/api/admin/contatos/${contatoEmEdicao.id}`,
        "PUT",
        dados,
      );
      selecionar("#edit-dialog").close();
      mostrarMensagem(
        selecionar("#admin-feedback"),
        resultado.message,
        "success",
      );
      await carregarContatos();
    } catch (erro) {
      mostrarMensagem(selecionar("#edit-error"), erro.message);
    } finally {
      alterarEstadoOcupado(false);
    }
  });

  selecionar("#confirm-action").addEventListener("click", async () => {
    if (painelOcupado || !confirmacaoAtual) return;

    const { contato, acao } = confirmacaoAtual;
    const excluir = acao === "delete";
    const caminho = `/api/admin/contatos/${contato.id}${excluir ? "" : "/status"}`;
    const metodo = excluir ? "DELETE" : "PATCH";
    const dados = {
      revision: contato.revision,
      ...(excluir ? {} : { status: acao }),
    };

    alterarEstadoOcupado(true);
    mostrarMensagem(selecionar("#confirm-error"), "");

    try {
      const resultado = await consultarApi(caminho, metodo, dados);
      selecionar("#confirm-dialog").close();
      mostrarMensagem(
        selecionar("#admin-feedback"),
        resultado.message,
        "success",
      );
      await carregarContatos();
    } catch (erro) {
      mostrarMensagem(selecionar("#confirm-error"), erro.message);
    } finally {
      alterarEstadoOcupado(false);
    }
  });

  selecionar("#logout").addEventListener("click", async () => {
    if (painelOcupado) return;

    alterarEstadoOcupado(true);
    try {
      await consultarApi("/api/admin/logout", "POST");
      selecionar("#records").replaceChildren();
      location.replace("/admin/login");
    } catch (erro) {
      mostrarMensagem(selecionar("#admin-feedback"), erro.message);
      alterarEstadoOcupado(false);
    }
  });


  // Inicia a sessão e carrega os dados necessários ao painel.

  async function carregarPainel() {
    try {
      const sessao = await consultarApi("/api/admin/session");
      tokenCsrf = sessao.csrf;
      selecionar("#admin-username").textContent =
        `Conectado como ${sessao.username}`;

      const categorias = await consultarApi("/api/categorias");
      categorias.forEach((nome) => {
        selecionar("#edit-category").add(new Option(nome, nome));
      });

      await carregarContatos();
    } catch (erro) {
      mostrarMensagem(selecionar("#admin-feedback"), erro.message);
      selecionar("#load-status").textContent =
        "Não foi possível iniciar o painel. Recarregue a página.";
    }
  }

  carregarPainel();
}
