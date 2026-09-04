// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralPt } from "./plural";

// Frozen EUROPEAN PORTUGUESE game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile peça · letter letra · rack suporte · blank peça em branco · bag saco ·
//   board = tabuleiro (the physical playing surface) AND partida (a saved game) ·
//   pass passar, noun passe · points pontos, abbreviated PTS / pts · rival = opponent adversário.
// `board` really is two words: `tabuleiro` is the surface a peça sits on, `partida` is the
// metonym for a stored game ("Partidas guardadas", "Voltar às partidas"). `passar` and `trocar`
// are different moves and keep different words. A `peça em branco` is a peça carrying no letra.
//
// pt-PT AND NOT pt-BR: the lexicon a player is judged against is pt_PT, so the chrome is too.
// Frozen Portugal computing vocabulary — utilizador (not usuário) · palavra-passe (not senha) ·
// iniciar / terminar sessão · registo, Registar (not registro, Registrar) · definições (not
// configurações) · guardar, guardada (not salvar, salvo) · retomar · arrastar e largar (not
// soltar) · atualizar · fila · sala. Also ligação (not conexão), predefinido (not padrão),
// pesquisa (not busca), em direto (not ao vivo), partilhar (not compartilhar), aspeto, distintivo.
// Progressive aspect is `estar a` + INFINITIVE and never the Brazilian gerund: "está a jogar",
// "A carregar partidas...". Clitic placement is the European one ("Esgotou-se",
// "autenticar-se", "voltares a ligar-te"), and "antes de o stream começar" stays uncontracted,
// the way Portugal writes it.
//
// Register: informal `tu` everywhere, error messages included. Never `você`, never a formal form.
// Label style: INFINITIVE for every control, action label, column heading and accessible name
// (Jogar · Passar · Trocar · Cancelar · Terminar sessão); `tu` IMPERATIVE only for prose
// sentences and hero headings (Escolhe a tua próxima partida). Never mixed inside one strip.
// `AI` is a preserved product token, so it is never rewritten to `IA`, and it takes FEMININE
// agreement throughout ("a AI", "a AI está a pensar"), matching `a inteligência artificial`.
export const ptText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Libre Tiles premium,",
  "landing.titleLine2": "humanos e AI.",
  "landing.lead":
    "Jogo de palavras open-source com emparelhamento em direto, adversários AI implacáveis, tabuleiro com acabamento premium e um histórico pronto para a tua próxima partida.",
  "landing.card.ai.title": "Duelos com AI",
  // `model` is translated here: on a landing page it is an ordinary noun, and Portuguese
  // `modelo` is unambiguous. The `chat` token below stays English because it names the
  // product's chat panel, which the player matches against `chat.title`.
  "landing.card.ai.body": "Partidas premium com escolha de modelo",
  "landing.card.queue.title": "Fila em direto",
  "landing.card.queue.body": "Sincronização em tempo real e chat",
  "landing.card.saved.title": "Partidas guardadas",
  "landing.card.saved.body": "Retomar partidas com a AI ou com humanos",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 palavras válidas",
  "auth.eyebrow": "Conta",
  "auth.heading.login": "Início de sessão",
  "auth.heading.register": "Criação de conta",
  "auth.tab.login": "Iniciar sessão",
  "auth.tab.register": "Registar",
  "auth.field.username": "Nome de utilizador",
  "auth.field.password": "Palavra-passe",
  "a11y.chatInput": "Mensagem de chat",
  "a11y.dialog.profile": "Perfil",
  "a11y.dialog.games": "Partidas guardadas",
  "a11y.dialog.blank": "Escolher uma letra",
  "a11y.dialog.rival": "Adversário indisponível",
  "a11y.status.turn": "Estado da vez",
  "a11y.status.aiThinking": "Progresso da AI",
  "a11y.rackBlank": "Peça em branco",
  "auth.submit.loading": "A iniciar sessão...",
  "auth.submit.login": "Jogar agora",
  "auth.submit.register": "Criar conta e jogar",
  "meta.title":
    "Libre Tiles — jogo de palavras na web com AI e multijogador em direto",
  "meta.description":
    "Jogo de palavras open-source com adversários AI, partidas em direto contra humanos, chat e um arrastar e largar bem afinado.",
  "error.checkFields": "Verifica os dados que enviaste.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Nome de utilizador ou palavra-passe incorretos",
  "error.sessionExpired": "A tua sessão expirou. Inicia sessão novamente.",
  "error.forbidden": "Não tens permissão para fazer isso.",
  "error.notFound": "Não encontrado.",
  "error.conflict": "Esta ação não corresponde ao estado atual da partida.",
  "error.throttled.unknown":
    "Demasiados pedidos. Aguarda um momento e tenta novamente.",
  "error.throttled.oneMinute":
    "Demasiados pedidos. Tenta novamente em cerca de um minuto.",
  "error.unavailable":
    "O serviço está temporariamente indisponível. Tenta novamente.",
  "error.generic": "Algo falhou. Tenta novamente.",
  "settings.timeout.title": "Tempo de reflexão da AI",
  "settings.timeout.30": "Leitura rápida do tabuleiro",
  "settings.timeout.60": "Pesquisa equilibrada",
  "settings.timeout.120": "Tempo de reflexão predefinido",
  "settings.timeout.180": "Ritmo de torneio",
  "settings.timeout.300": "Reflexão mais longa",
  "settings.steps.title": "Passos de pesquisa",
  "settings.steps.10": "Ferramentas rápidas",
  "settings.steps.20": "Mais tentativas",
  "settings.steps.30": "Pesquisa focada",
  "settings.steps.50": "Profundidade de pesquisa predefinida",
  "settings.steps.80": "Pressão máxima",
  "settings.board.title": "Superfície do tabuleiro",
  "settings.board.description":
    "Guardada neste dispositivo e usada no tabuleiro de jogo.",
  "settings.board.wood": "Madeira",
  "settings.board.woodDesc": "Veio clássico de nogueira",
  "settings.board.black": "Preto",
  "settings.board.blackDesc": "Laca noturna brilhante",
  "settings.board.green": "Verde",
  "settings.board.greenDesc": "Feltro escuro de torneio",
  // This badge sits beside a surface name that is feminine (Madeira) or masculine (Preto,
  // Verde), so no agreeing adjective is correct at both. An invariable phrase avoids the guess.
  "settings.board.active": "Em uso",
  "settings.toggle.on": "Ligado",
  "settings.toggle.off": "Desligado",
  "settings.shiny.title": "Efeito brilhante",
  "settings.shiny.description":
    "Desliga o brilho animado quando quiseres menos carga na GPU.",
  "settings.shiny.onDesc": "Brilho animado do tabuleiro",
  "settings.shiny.offDesc": "Menos carga na GPU",
  "settings.premium.title": "Aspeto premium",
  "settings.premium.description":
    "Luz âmbar interativa no cabeçalho da partida e no painel do suporte.",
  "settings.premium.onDesc": "Painéis interativos premium",
  "settings.premium.offDesc": "Superfícies escuras clássicas",
  "settings.backToGame": "Voltar à partida",
  "settings.error.newGame": "Não foi possível começar uma nova partida agora.",
  "settings.warn.accountSync":
    "A sincronização da conta está indisponível neste momento. As definições continuam a funcionar localmente neste dispositivo.",
  "settings.warn.rivalRepair":
    "Está selecionado um adversário gratuito neste dispositivo. A preferência da conta ainda não pôde ser reparada.",
  "settings.uiLanguage.title": "Idioma da interface",
  "settings.uiLanguage.description":
    "Menus, botões e mensagens. Aplica-se de imediato e apenas neste dispositivo.",
  // Endonyms, identical in every catalog by project rule. Never Portuguese exonyms.
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "picker.search": "Pesquisar",
  "picker.noMatch": "Sem resultados",
  "picker.uiLanguageLabel": "Idioma da interface",
  "picker.gameVariantLabel": "Variante de jogo",
  "settings.gameVariant.title": "Variante de jogo",
  "settings.gameVariant.description":
    "Peças, saco e léxico. Aplica-se apenas a NOVAS partidas e nunca altera uma partida em curso. Não é o idioma da interface.",
  // Game-variant names are translated exonyms, unlike the endonyms above. Afrikaans keeps its
  // own name: Portuguese has no settled exonym, and `afrikaans` is what Portuguese writes.
  "settings.gameVariant.english": "Inglês",
  "settings.gameVariant.slovak": "Eslovaco",
  "settings.gameVariant.czech": "Checo",
  "settings.gameVariant.polish": "Polaco",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italiano",
  "settings.gameVariant.dutch": "Neerlandês",
  "settings.gameVariant.german": "Alemão",
  "settings.gameVariant.portuguese": "Português",
  "settings.gameVariant.danish": "Dinamarquês",
  "settings.gameVariant.swedish": "Sueco",
  "settings.gameVariant.icelandic": "Islandês",
  "settings.rival.title": "O teu adversário",
  "settings.rival.description":
    "O administrador escolhe o adversário das novas partidas.",
  "nav.settings": "Definições",
  "nav.account": "Conta",
  "profile.subtitle":
    "Dados da conta e segurança da palavra-passe num só lugar.",
  "profile.email": "E-mail",
  "profile.noEmail": "Sem e-mail definido",
  "profile.memberSince": "Membro desde",
  "profile.password.subtitle":
    "Muda a tua palavra-passe sem sair da partida.",
  "profile.password.footnote":
    "Palavras-passe mais fortes tornam as contas de multijogador mais seguras.",
  "profile.field.current": "Palavra-passe atual",
  "profile.field.new": "Nova palavra-passe",
  "profile.field.confirm": "Confirmar a nova palavra-passe",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Palavra-passe atual",
  "profile.ph.new": "Pelo menos 8 caracteres",
  "profile.ph.confirm": "Repete a nova palavra-passe",
  "profile.submit": "Alterar palavra-passe",
  "profile.submitting": "A alterar...",
  "profile.error.allFields": "Preenche todos os campos da palavra-passe.",
  "profile.error.mismatch": "As novas palavras-passe não coincidem.",
  "play.title": "Escolhe a tua próxima partida",
  "play.lead":
    "Começa um duelo premium contra a AI, entra na fila em direto ou reabre uma das tuas partidas guardadas.",
  "play.ai.eyebrow": "Partida com AI",
  "play.ai.title": "Joga contra a AI",
  "play.ai.body":
    "Joga contra o adversário AI atual, com o sorteio inicial animado.",
  "play.ai.preparing": "A preparar a partida...",
  "play.rival.unavailable": "Nenhum adversário disponível",
  "play.humanQueue.eyebrow": "Fila de jogadores",
  "play.humanQueue.title": "Encontra um adversário em direto",
  "play.humanQueue.body":
    "Junta-te ao primeiro jogador em espera. Se não estiver ninguém, a tua partida fica à espera na sala.",
  "play.humanQueue.joining": "A entrar na fila...",
  "play.saved.eyebrow": "Partidas guardadas",
  "play.saved.title": "Retoma onde ficaste",
  "play.saved.note":
    "As partidas contra a AI e contra humanos partilham o mesmo histórico premium.",
  "play.error.catalogEmpty":
    "O catálogo de adversários está vazio. Preenche o catálogo gratuito para poderes jogar partidas com AI.",
  "play.error.catalogUnavailable":
    "O catálogo de adversários está indisponível neste momento. Tenta novamente dentro de um instante.",
  "play.error.variantUnavailable":
    "Não há nenhuma variante de jogo jogável disponível. A criação de partidas está bloqueada até ser possível carregar uma variante jogável.",
  "play.error.startAi": "Não foi possível começar uma partida com AI.",
  "play.error.joinQueue": "Não foi possível entrar na fila de jogadores.",
  "play.error.loadGames": "Não foi possível carregar as tuas partidas.",
  "history.filter.ai": "AI",
  "history.filter.human": "Humanos",
  "history.filter.all": "Todas",
  "history.sort.recent": "Recentes",
  "history.refresh": "Atualizar",
  "history.loading": "A carregar partidas",
  "history.empty.title": "Ainda não há partidas neste filtro",
  "history.empty.body":
    "Começa uma nova partida e ela aparecerá aqui, com paginação premium, distintivos de resultado e ligações rápidas para retomar.",
  "history.noneYet": "Ainda não há partidas guardadas",
  // Also the fallback for a missing username in ProfileModal, not only for a missing date, so
  // it takes the unmarked masculine rather than agreeing with `data`.
  "history.unknownDate": "Desconhecido",
  "history.col.rival": "Adversário",
  "history.col.mode": "Modo",
  "history.col.result": "Resultado",
  "history.col.score": "Pontos",
  "history.col.moves": "Jogadas",
  "history.col.updated": "Atualizada",
  // The eight outcome badges are NOUNS or invariable phrases, so none of them has to agree
  // with `partida` in one call site and `resultado` in another.
  "history.outcome.waiting": "À espera",
  "history.outcome.active": "Em curso",
  "history.outcome.won": "Vitória",
  "history.outcome.lost": "Derrota",
  "history.outcome.draw": "Empate",
  "history.outcome.gaveUp": "Desistência",
  "history.outcome.abandoned": "Abandono",
  "history.outcome.unknown": "Desconhecido",
  "history.mode.ai": "Duelo com AI",
  "history.mode.human": "Duelo com humanos",
  "history.hint.waitingRoom": "Sala de espera",
  "history.hint.boardReady": "Partida pronta",
  "history.endReason.bagEmpty": "Saco e suporte vazios",
  "history.endReason.noMoves": "Sem jogadas possíveis",
  "history.endReason.sixZero": "Seis jogadas sem pontos",
  "history.endReason.gaveUp": "Por desistência",
  "history.endReason.queueCancelled": "Fila cancelada",
  "history.open": "Abrir",
  "history.current": "Atual",
  // Pagination is a pair of ordinals in Portuguese, so these two are the one place the
  // infinitive label style would be wrong.
  "history.prev": "Anterior",
  "history.next": "Seguinte",
  "history.modal.subtitle":
    "Revê partidas antigas, alterna entre partidas com AI e com humanos e volta rapidamente ao jogo.",
  "queue.title": "À espera de um adversário",
  "queue.body":
    "A tua partida está pronta. Começa assim que outro jogador entrar.",
  "queue.leave": "Sair da fila",
  "queue.leaving": "A sair da fila...",
  "queue.error.dropped": "A ligação em tempo real caiu.",
  "queue.error.enter": "Não foi possível entrar na sala de espera.",
  "queue.error.leave": "Não foi possível sair da fila.",
  "draw.eyebrow": "Sorteio inicial",
  "draw.title": "Quem abre a partida",
  "draw.subtitle":
    "Começa quem tirar a peça mais próxima de A. Uma peça em branco ganha sempre.",
  "draw.side.you": "Tu",
  "draw.side.ai": "AI",
  "draw.pending": "A tirar peças do saco...",
  // The frozen term is `peça em branco`, but this caption is rendered directly under the peça
  // it describes, in a very narrow tracked pill, so the noun would be redundant there.
  "draw.blankCaption": "em branco",
  "draw.result.youStart": "Começas tu",
  "draw.result.aiStart": "Começa a AI",
  "draw.reason.blankYou": "A tua peça em branco ganha o sorteio.",
  "draw.reason.blankAi": "A AI tirou a peça em branco.",
  "draw.reason.bothBlank": "As duas peças estão em branco, por isso começas tu.",
  "controls.play": "Jogar",
  "controls.pass": "Passar",
  "controls.exchange": "Trocar",
  "controls.confirmExchange": "Confirmar troca",
  "controls.cancel": "Cancelar",
  "board.pts": "PTS",
  "board.pinchToZoom": "Zoom com dois dedos",
  "board.dragToPan": "Arrastar para mover",
  "board.hide": "Ocultar",
  "board.reset": "Repor",
  "rack.empty": "Não há peças no suporte",
  "blank.chooseLetter": "Escolher uma letra para a peça em branco",
  "chat.title": "Chat da partida",
  "chat.empty": "Ainda não há mensagens.",
  "chat.you": "Tu",
  "chat.unavailable": "Chat indisponível",
  "chat.placeholder": "Escreve algo",
  "chat.send": "Enviar",
  "game.lexicon.collins2019": "Não está no Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Não está no léxico eslovaco",
  "game.lexicon.czech": "Não está no léxico checo",
  "game.lexicon.polish": "Não está no léxico polaco",
  // The adjectives agree with `léxico`, which is masculine. `afrikaans` is invariable in
  // Portuguese and is the one row that carries a language name instead of an adjective.
  "game.lexicon.afrikaans": "Não está no léxico afrikaans",
  "game.lexicon.italian": "Não está no léxico italiano",
  "game.lexicon.dutch": "Não está no léxico neerlandês",
  "game.lexicon.german": "Não está no léxico alemão",
  "game.lexicon.portuguese": "Não está no léxico português",
  "game.lexicon.danish": "Não está no léxico dinamarquês",
  "game.lexicon.swedish": "Não está no léxico sueco",
  "game.lexicon.icelandic": "Não está no léxico islandês",
  "game.lexicon.unknown": "Não está no léxico do jogo",
  "game.blocker.auth.title": "Falhou a autenticação do adversário",
  "game.blocker.auth.body":
    "Este adversário gratuito não conseguiu autenticar-se. Muda para outro adversário gratuito ou tenta novamente mais tarde.",
  "game.blocker.rate.title": "O adversário atingiu o limite",
  "game.blocker.rate.body":
    "Este adversário gratuito atingiu o limite de pedidos. Muda para outro adversário gratuito ou tenta novamente mais tarde.",
  "game.blocker.unavail.title": "O adversário está indisponível",
  "game.blocker.unavail.body":
    "Este adversário gratuito está temporariamente indisponível. Muda para outro adversário gratuito ou tenta novamente mais tarde.",
  "game.blocker.badge.auth": "Autenticação",
  "game.blocker.badge.rate": "Limite atingido",
  "game.blocker.badge.unavail": "Indisponível",
  "game.blocker.close": "Fechar",
  "game.blocker.openSettings": "Abrir as definições",
  "game.toast.invalidPlacement": "Colocação inválida",
  "game.toast.invalidWords": "Palavras inválidas",
  "game.toast.moveRejected": "Jogada rejeitada",
  "game.toast.exchangeRejected": "Troca rejeitada",
  "game.toast.passRejected": "Passe rejeitado",
  "game.toast.chatOffline": "O chat está offline",
  "game.toast.aiPasses": "A AI passou a vez",
  "game.toast.aiExchanged": "A AI trocou peças",
  "game.toast.aiExchangedBody": "A AI renovou o suporte e gastou a vez.",
  "game.toast.aiPassedBody":
    "Não encontrou nenhuma jogada válida — é a tua vez!",
  // The call site composes these two into `[before] <span>{score}</span> [points]`, with the
  // score fixed in the middle. Portuguese wants verb, then number, then noun, so it costs
  // nothing here.
  "game.aiPlayedFor.before": "A AI marcou",
  "game.aiPlayedFor.points": "pts",
  "game.aWord": "uma palavra",
  "game.status.selectExchange": "Escolhe as peças a trocar",
  "game.status.aiMoveReady": "Jogada da AI pronta",
  "game.status.aiThinking": "A AI está a pensar",
  "game.status.yourTurn": "É a tua vez",
  "game.status.waitingForAi": "À espera da AI",
  "game.opponentFallback": "Adversário",
  "game.waitingSlot": "À espera",
  "game.sessionExpired": "Sessão expirada",
  "game.lastError": "Último erro:",
  "game.newGame": "Nova partida",
  "game.starting": "A começar...",
  "game.victory": "Vitória!",
  "game.draw": "Empate!",
  "game.gameOver": "Fim da partida",
  "game.giveUp.ai": "Desistir desta partida? A AI será declarada vencedora.",
  "game.giveUp.human":
    "Desistir desta partida? O teu adversário será declarado vencedor.",
  "game.gaveUp": "Desististe da partida.",
  "game.error.giveUp": "Não foi possível desistir desta partida",
  "game.error.newGame": "Não foi possível começar uma nova partida",
  "game.error.loadGames": "Não foi possível carregar as partidas.",
  "game.password.updated": "Palavra-passe alterada.",
  "game.password.failed": "Não foi possível alterar a palavra-passe.",
  "game.ai.noRival": "Não há nenhum adversário gratuito elegível disponível.",
  "game.ai.timeout": "Esgotou-se o tempo de reflexão da AI.",
  "game.ai.moveFailed": "A jogada da AI falhou",
  "game.ws.syncFailed": "Falhou a sincronização em tempo real",
  "game.ws.connectFailed": "Falhou a ligação em tempo real",
  "game.ws.authExpired":
    "A autenticação em tempo real expirou. Atualiza a página para voltares a ligar-te.",
  "game.ws.invalidSession":
    "Esta sessão em tempo real não é válida. Atualiza a página para voltares a ligar-te.",
  "game.ws.unavailable":
    "O serviço em tempo real está indisponível. Tenta novamente.",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in that fixed order.
  // Portuguese wants exactly that order, so "Repor zoom" needs no workaround.
  "board.zoomNoun": "zoom",
  "header.giveUp": "Desistir",
  "header.givingUp": "A desistir...",
  "header.giveUpTooltip": "Desistir da partida atual",
  "header.logout": "Terminar sessão",
  "header.loggingOut": "A terminar sessão...",
  "header.backToBoards": "Voltar às partidas",
  "header.profile": "Perfil",
  "header.games": "Partidas",
  "overlay.aiThinking": "AI a pensar",
  "overlay.searching": "A procurar jogadas...",
  "overlay.best": "Melhor",
  "overlay.bestBadge": "MELHOR",
  "overlay.filtering":
    "A filtrar jogadas fracas ou inválidas antes de mostrar uma jogada a sério...",
};

export const ptFn: { [K in FnKey]: (typeof enFn)[K] } = {
  // The three counted-noun sites below take four arguments. The second slot covers ZERO too and
  // not only one — CLDR pt makes 0 singular, so a passed turn reads "0 ponto" — and the fourth
  // slot is reachable only at exact millions, where Portuguese repeats the third slot's word.
  "a11y.rackTile": (p) =>
    `Peça ${p.letter}, ${p.points} ` +
    pluralPt(p.points, "ponto", "pontos", "pontos"),
  // Colon-labels, so no adjective has to agree with an arbitrary count.
  "overlay.stats.tried": (p) => `Tentadas: ${p.count}`,
  "overlay.stats.valid": (p) => `Válidas: ${p.count}`,
  "overlay.stats.rejected": (p) => `Rejeitadas: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Demasiados pedidos. Tenta novamente em cerca de ${p.minutes} ` +
    pluralPt(p.minutes, "minuto", "minutos", "minutos") +
    ".",
  // `winner` and `loser` receive tile letters, never a person. A bare letter's gender is not
  // settled in Portuguese, so this uses the invariable `mais perto de` rather than an adjective.
  "draw.reason.closer": (p) =>
    `${p.winner} está mais perto de A do que ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `Seleção: ${p.count} ` + pluralPt(p.count, "peça", "peças", "peças"),
  "game.ai.exploring": (p) => `A procurar palavras válidas com ${p.model}...`,
  "game.ai.attempt": (p) => `Tentativa ${p.index}/${p.total} · ${p.label}`,
  "game.toast.aiPlayedWord": (p) => `A AI jogou ${p.word}`,
  "game.status.opponentPlaying": (p) => `${p.name} está a jogar`,
  // Two full forms, never a suffix trick, and the adjective agrees in number.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Palavras inválidas!" : "Palavra inválida!",
  "game.ai.routeFailed": (p) => `A chamada à AI falhou (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `A chamada à AI falhou (${p.status}) antes de o stream começar.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `A chamada à AI falhou (${p.status}): ${p.preview}`,
  "play.humanQueue.queueFor": (p) => `Fila: ${p.variant}`,
  "queue.room": (p) => `Sala ${p.code}`,
  "history.pageOf": (p) => `Página ${p.page} de ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `A mostrar ${p.from}-${p.to} de ${p.total}`,
  "picker.flagAlt": (p) => `Bandeira: ${p.language}`,
};
