"use strict";

/*
 * Interface pública do Sá Conecta.
 * Carrega o catálogo, aplica filtros, exibe detalhes e envia sugestões.
 * O SQLite continua sendo a fonte dos dados e é acessado apenas pelo FastAPI.
 */

// Estado da página
let categorias = [];
let estabelecimentos = [];
let carregado = false;
let carregando = false;
let enviando = false;
let envioAtual = null;


// Funções auxiliares

// Ignora acentos e maiúsculas: “saude” também encontra “Saúde”.
function normalizar(texto) {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function filtrarEstabelecimentos(lista, busca, categoria) {
  const palavras = normalizar(busca).split(/\s+/).filter(Boolean);
  return lista.filter(item => {
    const texto = normalizar([item.name, item.category, item.description, item.address].join(" "));
    return (!categoria || item.category === categoria) && palavras.every(palavra => texto.includes(palavra));
  });
}
// Usa textContent para não interpretar conteúdo de cadastros como HTML.
function elemento(tag, classe, texto) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texto !== undefined) node.textContent = texto;
  return node;
}

// Elementos usados em várias funções
const search = document.querySelector("#search");
const category = document.querySelector("#category");
const cards = document.querySelector("#cards");
const details = document.querySelector("#details-dialog");
const suggestion = document.querySelector("#suggestion-dialog");
const form = document.querySelector("#suggestion-form");
const phone = document.querySelector("#business-phone");
const status = document.querySelector("#form-status");
const submit = document.querySelector("#submit-suggestion");

// Faz uma requisição com limite de 15 segundos e padroniza as mensagens de erro.
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail :
        "Confira os campos: nome (2 a 100 caracteres), descrição (5 a 400), endereço (3 a 160), categoria, telefone e autorização.";
      throw new Error(detail);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError" || error instanceof TypeError || error instanceof SyntaxError) {
      throw new Error("Não foi possível confirmar a resposta do servidor. Confira a conexão e tente novamente sem alterar os campos.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function formatarTelefone(value) {
  const d = (value || "").replace(/\D/g, "");
  return d.length === 11 ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}` :
    d.length === 10 ? `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}` : "Não informado";
}

function abrirDetalhes(item) {
  document.querySelector("#details-title").textContent = item.name;
  document.querySelector("#details-category").textContent = item.category;
  document.querySelector("#details-description").textContent = item.description;
  const info = document.querySelector("#details-info");
  info.replaceChildren();
  [["Endereço", item.address], ["Horário", item.hours || "Não informado"], ["Telefone", formatarTelefone(item.phone)]].forEach(([rotulo, valor]) => {
    info.append(elemento("dt", "", rotulo), elemento("dd", "", valor));
  });
  document.querySelector("#details-demo").hidden = !item.is_demo;
  const actions = document.querySelector("#contact-actions");
  actions.replaceChildren();
  if (!item.is_demo && /^[0-9]{10,11}$/.test(item.phone || "")) {
    const call = elemento("a", "button secondary", "Ligar");
    call.href = `tel:+55${item.phone}`;
    actions.append(call);
    if (item.whatsapp) {
      const whatsapp = elemento("a", "button primary", "Conversar no WhatsApp");
      whatsapp.href = `https://wa.me/55${item.phone}`;
      whatsapp.target = "_blank";
      whatsapp.rel = "noopener noreferrer";
      actions.append(whatsapp);
    }
  }
  details.showModal();
}

function criarCard(item) {
  const card = elemento("article", "card");
  const top = elemento("div", "card-top");
  const initials = elemento("span", "initials", item.name.split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase());
  initials.setAttribute("aria-hidden", "true");
  top.append(initials, elemento("span", "tag", item.is_demo ? "Exemplo fictício" : "Contato local"));
  const bottom = elemento("div", "card-bottom");
  const button = elemento("button", "text-button", "Ver informações ↗");
  button.setAttribute("aria-label", `Ver informações de ${item.name}`);
  button.addEventListener("click", () => abrirDetalhes(item));
  bottom.append(button, elemento("small", "", item.is_demo ? "Sem contato real" : formatarTelefone(item.phone)));
  card.append(top, elemento("h3", "", item.name), elemento("p", "card-category", item.category), elemento("p", "card-description", item.description), elemento("p", "card-location", item.address), bottom);
  return card;
}


// Carregamento e exibição do catálogo

function renderizar() {
  if (!carregado) return;
  const resultados = filtrarEstabelecimentos(estabelecimentos, search.value, category.value);
  cards.replaceChildren(...resultados.map(criarCard));
  document.querySelector("#result-count").textContent = `${resultados.length} ${resultados.length === 1 ? "resultado" : "resultados"}`;
  document.querySelector("#empty-state").hidden = resultados.length !== 0;
  document.querySelectorAll(".category-button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.category === category.value)));
}

async function carregarCatalogo() {
  if (carregando) return;
  carregando = true;
  carregado = false;
  submit.disabled = true;
  document.querySelector("#retry-load").disabled = true;
  document.querySelector("#load-error").hidden = true;
  document.querySelector("#empty-state").hidden = true;
  document.querySelector("#result-count").textContent = "Carregando contatos…";
  try {
    [categorias, estabelecimentos] = await Promise.all([api("/api/categorias"), api("/api/estabelecimentos")]);
    const formCategory = document.querySelector("#business-category");
    [category, formCategory].forEach(select => {
      const previous = select.value;
      select.replaceChildren(new Option(select === category ? "Todas as categorias" : "Selecione", ""));
      categorias.forEach(nome => select.add(new Option(nome, nome)));
      if (categorias.includes(previous)) select.value = previous;
    });
    document.querySelector("#category-buttons").replaceChildren();
    ["", ...categorias].forEach(nome => {
      const button = elemento("button", "category-button");
      button.type = "button";
      button.dataset.category = nome;
      button.append(elemento("span", "", nome || "Todas as categorias"), elemento("span", "category-count", String(estabelecimentos.filter(item => !nome || item.category === nome).length)));
      button.addEventListener("click", () => { category.value = nome; renderizar(); });
      document.querySelector("#category-buttons").append(button);
    });
    document.querySelector("#demo-notice").hidden = !estabelecimentos.some(item => item.is_demo);
    carregado = true;
    renderizar();
  } catch (error) {
    document.querySelector("#load-error").hidden = false;
    document.querySelector("#result-count").textContent = "Catálogo indisponível";
  } finally {
    carregando = false;
    document.querySelector("#retry-load").disabled = false;
    submit.disabled = !carregado || enviando;
  }
}


// Eventos de busca e navegação

document.querySelector("#retry-load").addEventListener(
  "click",
  carregarCatalogo
);
search.addEventListener("input", renderizar);
category.addEventListener("change", renderizar);

document.querySelector("#search-form").addEventListener("submit", event => {
  event.preventDefault();
  renderizar();
  document.querySelector("#catalogo").scrollIntoView();
});

document.querySelector("#clear-filters").addEventListener("click", () => {
  search.value = "";
  category.value = "";
  renderizar();
  search.focus();
});

document.querySelectorAll("[data-open-form]").forEach(button => {
  button.addEventListener("click", () => suggestion.showModal());
});

document.querySelectorAll("[data-close]").forEach(button => {
  button.addEventListener("click", () => button.closest("dialog").close());
});


// Validação e envio do formulário de sugestão

// O elemento dialog oferece foco modal e fechamento com Escape nativamente.
phone.addEventListener("input", () => {
  const digits = phone.value.replace(/\D/g, "");
  phone.setCustomValidity(digits.length === 10 || digits.length === 11 ? "" : "Informe 10 ou 11 dígitos, incluindo o DDD.");
});
form.querySelectorAll("input[required]:not([type='checkbox']), textarea[required]").forEach(input => {
  if (input !== phone) {
    input.addEventListener("input", () => {
      input.setCustomValidity(input.value.trim() ? "" : "Preencha este campo.");
    });
  }
});

form.addEventListener("input", () => {
  status.textContent = "";
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (enviando || !carregado || !form.reportValidity()) return;
  const fields = new FormData(form);
  const payload = {
    name: fields.get("name").trim(),
    category: fields.get("category"),
    phone: fields.get("phone"),
    address: fields.get("address").trim(),
    hours: fields.get("hours").trim(),
    description: fields.get("description").trim(),
    whatsapp: fields.get("whatsapp") === "on",
    consent: fields.get("consent") === "on"
  };
  // Guarda a chave em memória para recuperar um envio cuja resposta se perdeu.
  const signature = JSON.stringify(payload);
  if (!envioAtual || envioAtual.signature !== signature) {
    envioAtual = { signature, id: crypto.randomUUID() };
  }
  payload.request_id = envioAtual.id;
  enviando = true;
  submit.disabled = true;
  submit.textContent = "Enviando…";
  status.textContent = "";
  try {
    const receipt = await api("/api/sugestoes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    // Não apaga edições que o usuário tenha feito enquanto o envio estava em curso.
    const current = new FormData(form);
    const unchanged = ["name", "category", "phone", "address", "hours", "description", "whatsapp", "consent"].every(key => current.get(key) === fields.get(key));
    if (unchanged) {
      form.reset();
      form.querySelectorAll("input, textarea, select").forEach(input => input.setCustomValidity(""));
    }
    envioAtual = null;
    status.textContent = `Protocolo ${receipt.protocol}. ${receipt.message}`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    enviando = false;
    submit.disabled = !carregado;
    submit.textContent = "Enviar sugestão";
  }
});

// Inicia a página buscando os dados no servidor.
carregarCatalogo();
