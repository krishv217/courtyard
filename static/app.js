const choices = [
  ["Walk to lunch", "I'd like company walking to lunch."],
  ["Lunch", "I'd like company at lunch."],
  ["Cards", "I'd like to play cards."],
  ["Library", "I'd like company in the library."],
  ["Cool room", "I'd like a seat in a cool common room."],
  ["Garden", "I'd like company in the garden."],
];

const accountIds = new Set(["helen", "frank", "ruth", "doris", "leo", "mae", "samir", "walter", "staff"]);
let viewer = sessionStorage.getItem("courtyard-resident") || "helen";
if (!accountIds.has(viewer)) viewer = "helen";
let page = sessionStorage.getItem("courtyard-page") || "feed";
if (page !== "friends" && page !== "events" && page !== "messages") page = "feed";
let activeChat = null;
let pendingSuggestion = "";
let noticesOpen = false;
let feedFilter = "all";
let state = null;
let refreshGeneration = 0;
let previewTimer = 0;
let recorder = null;
let arming = false;
let listenTimer = 0;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Something went wrong");
  return payload;
}

function setStatus(message) {
  const node = document.querySelector("#status");
  if (node) node.textContent = message || "";
}

function showAccount() {
  const staff = viewer === "staff";
  document.body.classList.toggle("staff", staff);
  document.querySelector("#resident-view").hidden = staff;
  document.querySelector("#staff-view").hidden = !staff;
  document.querySelector("#resident-nav").hidden = staff;
  document.querySelector("#bell").hidden = staff;
  if (staff) noticesOpen = false;
  if (!staff) showPage(page);
}

async function refresh() {
  const generation = ++refreshGeneration;
  const next = await api(`/api/state?as=${encodeURIComponent(viewer)}`);
  if (generation !== refreshGeneration) return;
  state = next;
  showAccount();
  if (viewer === "staff") renderStaff();
  else renderResident();
}

function renderKeys() {
  const meta = state.keys.meta ? "Meta connected" : "Meta key missing";
  const grok = state.keys.grok ? "Grok connected" : "Grok key missing";
  document.querySelector("#keys").innerHTML = `
    <span class="pill ${state.keys.meta ? "on" : ""}">${meta}</span>
    <span class="pill ${state.keys.grok ? "on" : ""}">${grok}</span>
  `;
}

function personById(id) {
  return (state.residents || []).find((item) => item.id === id);
}

function avatarHtml(person) {
  const initial = person ? person.first_name.slice(0, 1) : "?";
  const hue = person && person.hue ? person.hue : "#1e4a38";
  if (person && person.portrait) {
    return `<img class="avatar" src="${escapeHtml(person.portrait)}" alt="" style="background:${escapeHtml(hue)}">`;
  }
  return `<span class="avatar" style="background:${escapeHtml(hue)}">${escapeHtml(initial)}</span>`;
}

function sharedLine(count) {
  return count === 1 ? "You've been to 1 event together" : `You've been to ${count} events together`;
}

function personRow(person, detail, actionHtml) {
  const line = detail ? `<p class="quiet">${detail}</p>` : "";
  const tastes = (person.tastes || []).slice(0, 3).join(" · ");
  const tasteLine = tastes ? `<p class="quiet">${escapeHtml(tastes)}</p>` : "";
  return `<article class="person-row">
    ${avatarHtml(person)}
    <div class="person-copy">
      <strong>${escapeHtml(person.name)}</strong>
      ${line}
      ${tasteLine}
    </div>
    <div class="person-action">${actionHtml}<button class="text-button" type="button" data-chat="${person.id}">Message</button></div>
  </article>`;
}

function bindFriendButtons(root) {
  root.querySelectorAll("[data-add-friend]").forEach((button) => {
    button.addEventListener("click", () => {
      changeFriend(button.dataset.addFriend, "request").catch((error) => setStatus(error.message));
    });
  });
  root.querySelectorAll("[data-accept-friend]").forEach((button) => {
    button.addEventListener("click", () => {
      changeFriend(button.dataset.acceptFriend, "accept").catch((error) => setStatus(error.message));
    });
  });
  root.querySelectorAll("[data-unfriend]").forEach((button) => {
    button.addEventListener("click", () => {
      changeFriend(button.dataset.unfriend, "remove").catch((error) => setStatus(error.message));
    });
  });
  bindChatButtons(root);
}

function renderFriendsPage() {
  const root = document.querySelector("#page-friends");
  const incoming = state.incoming || [];
  const friends = state.friends || [];
  const outgoing = state.outgoing || [];
  const suggestions = state.suggestions || [];
  const requests = document.querySelector("#friend-requests");
  requests.innerHTML = incoming.length
    ? `<h2 class="section-title">Requests</h2>${incoming.map((item) => {
        const person = personById(item.id);
        if (!person) return "";
        return personRow(person, "Wants to be friends", `<button class="primary slim" type="button" data-accept-friend="${person.id}">Accept</button>`);
      }).join("")}`
    : "";
  const friendList = document.querySelector("#friend-list");
  friendList.innerHTML = friends.length
    ? friends.map((item) => {
        const person = personById(item.id);
        if (!person) return "";
        return personRow(person, "", `<button class="text-button" type="button" data-unfriend="${person.id}">Remove</button>`);
      }).join("")
    : `<p class="quiet">No friends yet. Accept a request, or add someone below.</p>`;
  const suggestionBox = document.querySelector("#suggestions");
  suggestionBox.innerHTML = suggestions.length
    ? suggestions.map((item) => {
        const person = personById(item.id);
        if (!person) return "";
        return personRow(person, sharedLine(item.shared), `<button class="primary slim" type="button" data-add-friend="${person.id}">Add</button>`);
      }).join("")
    : `<p class="quiet">Join a few plans. People you've been with will show up here.</p>`;
  const known = new Set([
    viewer,
    ...friends.map((item) => item.id),
    ...incoming.map((item) => item.id),
    ...suggestions.map((item) => item.id),
  ]);
  const directory = state.residents.filter((person) => !known.has(person.id));
  document.querySelector("#directory").innerHTML = directory.length
    ? directory.map((person) => {
        const waiting = outgoing.some((item) => item.id === person.id);
        const action = waiting
          ? `<span class="quiet">Request sent</span>`
          : `<button class="primary slim" type="button" data-add-friend="${person.id}">Add</button>`;
        return personRow(person, waiting ? "Waiting for them to accept" : "", action);
      }).join("")
    : `<p class="quiet">Everyone else is already a friend or a suggestion.</p>`;
  bindFriendButtons(root);
  const tab = document.querySelector('[data-page="friends"]');
  tab.innerHTML = incoming.length
    ? `Friends <span class="count">${incoming.length}</span>`
    : "Friends";
}

async function changeFriend(otherId, action) {
  state = await api("/api/friends", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer, other_id: otherId, action }),
  });
  renderResident();
}

function renderChoices() {
  document.querySelector("#choices").innerHTML = choices.map(([label, sentence]) => `
    <button class="choice" type="button" data-sentence="${escapeHtml(sentence)}">${escapeHtml(label)}</button>
  `).join("");
  document.querySelectorAll("[data-sentence]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector("#note").value = button.dataset.sentence;
      schedulePreview();
    });
  });
}

function renderFence(decision, original) {
  const fence = document.querySelector("#fence");
  if (!decision || !original.trim()) {
    fence.innerHTML = "";
    return;
  }
  const withheld = decision.withheld.length
    ? `<div class="chips">${decision.withheld.map((item) => `<span class="chip">Kept private: ${escapeHtml(item)}</span>`).join("")}</div>`
    : `<p class="quiet">Nothing private was found in this note.</p>`;
  let shared = `<div class="shared"><strong>This one stays with the front desk.</strong><p>${escapeHtml(decision.summary || "A neighbor will not be sent.")}</p></div>`;
  const cards = decision.cards || (decision.card ? [decision.card] : []);
  if (decision.kind === "plan" && cards.length) {
    const reach = currentAudience() === "friends" ? "Only friends can see this." : "Anyone at Sunrise Court can join.";
    shared = cards.map((card) => `<div class="shared"><strong>${escapeHtml(card.activity)}</strong><p>${escapeHtml(card.place)} at ${escapeHtml(card.time)}. ${reach}</p></div>`).join("");
  } else if (decision.kind === "dropped") {
    shared = `<div class="shared"><strong>Nothing goes on the board.</strong><p>The note did not ask for company in a shared room.</p></div>`;
  }
  fence.innerHTML = `<h2>What others can see</h2>${withheld}${shared}`;
}

function currentAudience() {
  const toggle = document.querySelector("#audience-toggle");
  return toggle && toggle.getAttribute("aria-checked") === "true" ? "friends" : "everyone";
}

function setAudience(friendsOnly) {
  const toggle = document.querySelector("#audience-toggle");
  const caption = document.querySelector("#audience-caption");
  if (!toggle) return;
  toggle.setAttribute("aria-checked", friendsOnly ? "true" : "false");
  if (caption) caption.textContent = friendsOnly ? "Friends only" : "Open to everyone";
}

function nameList(names) {
  if (names.length <= 1) return names[0] || "Someone";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

function planBucket(plan) {
  const friendIds = new Set((state.friends || []).map((item) => item.id));
  const withFriend = plan.resident_ids.some((id) => friendIds.has(id));
  if ((plan.audience || "everyone") === "friends" || withFriend) return "friends";
  return "community";
}

function visiblePlans() {
  const plans = [...state.plans].reverse();
  if (viewer === "staff" || feedFilter === "all") return plans;
  return plans.filter((plan) => planBucket(plan) === feedFilter);
}

function inviteBlock(plan) {
  if (viewer === "staff" || !plan.resident_ids.includes(viewer)) return "";
  const going = new Set(plan.resident_ids);
  const invited = new Set(plan.invited || []);
  const friends = (state.friends || []).filter((item) => !going.has(item.id) && !invited.has(item.id));
  const invitedNames = (plan.invited_names || []).join(", ");
  if (!friends.length && !invitedNames) return "";
  const waiting = invitedNames ? `<p class="quiet">Invited ${escapeHtml(invitedNames)}</p>` : "";
  const buttons = friends.map((item) => `
    <button class="text-button" type="button" data-invite="${plan.id}" data-friend="${item.id}">Invite ${escapeHtml(item.name)}</button>
  `).join("");
  const picker = buttons ? `<div class="invite-list">${buttons}</div>` : "";
  return `<div class="invite">${waiting}${picker}</div>`;
}

function renderPlans(target, plans, mine = false) {
  if (!plans.length) {
    const empty = target.id === "yours"
      ? "You haven't signed up for anything yet."
      : target.id === "staff-plans"
      ? "Nothing posted yet."
      : feedFilter === "friends"
        ? "Nothing from friends yet. Open plans are under Community."
        : feedFilter === "community"
          ? "No open plans yet. Post one, or check Friends."
          : "Nothing posted yet. Share a walk, lunch, or cards and it will show up here.";
    target.innerHTML = `<p class="quiet empty">${empty}</p>`;
    return;
  }
  target.innerHTML = plans.map((plan) => {
    const host = personById(plan.resident_ids[0]);
    const inPlan = plan.resident_ids.includes(viewer);
    const grouped = plan.resident_ids.length >= 2;
    const friendsOnly = (plan.audience || "everyone") === "friends";
    const badge = friendsOnly ? "Friends only" : "Open";
    const others = plan.names.slice(1);
    const withLine = others.length ? `<p class="quiet">With ${escapeHtml(nameList(others))}</p>` : "";
    const room = plan.image
      ? `<div class="room"><img alt="Painting of the ${escapeHtml(plan.place)}" src="/api/plans/${plan.id}/image"></div>`
      : `<div class="room" data-place="${escapeHtml(plan.place)}"><span>${escapeHtml(plan.place)}</span></div>`;
    const hostId = plan.resident_ids[0];
    const join = viewer !== "staff" && !inPlan
      ? `<button class="primary slim" type="button" data-join="${plan.id}">Join</button>`
      : "";
    const cancel = mine && inPlan
      ? `<button class="ghost slim" type="button" data-cancel="${plan.id}">${hostId === viewer ? "Cancel event" : "Leave"}</button>`
      : "";
    const hear = grouped
      ? `<button class="hear" type="button" data-hear="${plan.id}" aria-label="Hear"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4h3l4 3V7L7 10H4z"/><path d="M16 9.5a3.5 3.5 0 010 5"/><path d="M18.5 7.5a6.5 6.5 0 010 9"/></svg></button>`
      : "";
    const line = plan.line ? `<p class="post-line">${escapeHtml(plan.line)}</p>` : `<p class="post-line">${escapeHtml(plan.names[0] || "Someone")} wants company for ${escapeHtml(plan.activity.toLowerCase())}.</p>`;
    return `<article class="post">
      ${avatarHtml(host)}
      <div class="post-body">
        <div class="post-head">
          <button class="text-button name-button" type="button" data-chat="${hostId}">${escapeHtml(host ? host.name : plan.names[0] || "Resident")}</button>
          <span class="badge">${escapeHtml(badge)}</span>
        </div>
        <p class="post-meta">${escapeHtml(plan.activity)} · ${escapeHtml(plan.place)} · ${escapeHtml(plan.time)}</p>
        ${withLine}
        ${line}
        ${room}
        ${mine ? inviteBlock(plan) : ""}
        <div class="actions">${join}${hear}${cancel}</div>
      </div>
    </article>`;
  }).join("");
  target.querySelectorAll("[data-join]").forEach((button) => {
    button.addEventListener("click", () => joinPlan(button.dataset.join));
  });
  bindChatButtons(target);
  target.querySelectorAll("[data-hear]").forEach((button) => {
    button.addEventListener("click", () => hearPlan(button.dataset.hear));
  });
  target.querySelectorAll("[data-cancel]").forEach((button) => {
    button.addEventListener("click", () => cancelPlan(button.dataset.cancel));
  });
  target.querySelectorAll("[data-invite]").forEach((button) => {
    button.addEventListener("click", () => {
      inviteFriend(button.dataset.invite, button.dataset.friend).catch((error) => setStatus(error.message));
    });
  });
}

function paintComposerAvatar() {
  const person = personById(viewer);
  const node = document.querySelector("#composer-avatar");
  if (!node || !person) return;
  if (person.portrait) {
    node.textContent = "";
    node.style.backgroundColor = person.hue;
    node.style.backgroundImage = `url("${person.portrait}")`;
    node.style.backgroundSize = "cover";
    node.style.backgroundPosition = "center";
    return;
  }
  node.textContent = person.first_name.slice(0, 1);
  node.style.backgroundImage = "none";
  node.style.backgroundColor = person.hue;
}

function showPage(next) {
  page = next === "friends" || next === "events" || next === "messages" ? next : "feed";
  sessionStorage.setItem("courtyard-page", page);
  document.querySelector("#page-feed").hidden = page !== "feed";
  document.querySelector("#page-events").hidden = page !== "events";
  document.querySelector("#page-friends").hidden = page !== "friends";
  document.querySelector("#page-messages").hidden = page !== "messages";
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.classList.toggle("selected", tab.dataset.page === page);
  });
}

function renderNotices() {
  const bell = document.querySelector("#bell");
  const panel = document.querySelector("#notices");
  if (!bell || !panel) return;
  const items = state.notifications || [];
  const unread = items.filter((item) => !item.read).length;
  bell.innerHTML = unread ? `Notices <span class="count">${unread}</span>` : "Notices";
  bell.setAttribute("aria-expanded", noticesOpen ? "true" : "false");
  panel.hidden = !noticesOpen || viewer === "staff";
  if (!noticesOpen) return;
  const rows = items.length
    ? items.map((item) => `
        <button class="notice ${item.read ? "" : "unread"}" type="button" data-read="${item.id}">
          ${escapeHtml(item.text)}
        </button>
      `).join("")
    : `<p class="quiet notice-empty">No notices yet.</p>`;
  const clear = unread ? `<button class="text-button notice-clear" type="button" id="mark-read">Mark all read</button>` : "";
  panel.innerHTML = `${rows}${clear}`;
  panel.querySelectorAll("[data-read]").forEach((button) => {
    button.addEventListener("click", () => {
      markRead(button.dataset.read).catch((error) => setStatus(error.message));
    });
  });
  const mark = panel.querySelector("#mark-read");
  if (mark) {
    mark.addEventListener("click", () => {
      markRead().catch((error) => setStatus(error.message));
    });
  }
}

function setComposerOpen(open) {
  document.querySelector("#composer-open").hidden = open;
  document.querySelector("#composer-body").hidden = !open;
  if (open) document.querySelector("#note").focus();
}

function myPlans() {
  return [...state.plans].reverse().filter((plan) => plan.resident_ids.includes(viewer));
}

function bindChatButtons(root) {
  if (!root) return;
  root.querySelectorAll("[data-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      openChat(button.dataset.chat).catch((error) => setStatus(error.message));
    });
  });
}

async function openChat(otherId) {
  if (!otherId || otherId === viewer) return;
  if (otherId !== activeChat) pendingSuggestion = "";
  activeChat = otherId;
  showPage("messages");
  state = await api("/api/messages/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer, other_id: otherId }),
  });
  renderResident();
}

async function sendChat(text, kind) {
  const body = { resident_id: viewer, other_id: activeChat, text };
  if (kind) body.kind = kind;
  state = await api("/api/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  renderResident();
}

async function askChatAgent(text) {
  setStatus("Grok is thinking of something you could send.");
  const payload = await api("/api/messages/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer, other_id: activeChat, text }),
  });
  pendingSuggestion = payload.suggestion || "";
  setStatus("");
  const field = document.querySelector("#chat-text");
  if (field) field.blur();
  renderMessages();
}

function renderMessages() {
  const root = document.querySelector("#page-messages");
  if (!root) return;
  const field = document.querySelector("#chat-text");
  if (field && document.activeElement === field) return;
  const threads = state.threads || [];
  const unread = threads.reduce((sum, thread) => sum + (thread.unread || 0), 0);
  const tab = document.querySelector('[data-page="messages"]');
  if (tab) tab.innerHTML = unread ? `Messages <span class="count">${unread}</span>` : "Messages";
  const list = threads.map((thread) => `
    <button class="thread ${thread.peer_id === activeChat ? "selected" : ""}" type="button" data-chat="${thread.peer_id}">
      <strong>${escapeHtml(thread.peer_name)}</strong>
      <span class="quiet">${escapeHtml(thread.last || "No messages yet")}</span>
    </button>
  `).join("");
  const thread = threads.find((item) => item.peer_id === activeChat);
  const peer = activeChat ? personById(activeChat) : null;
  const peerTastes = peer && peer.tastes && peer.tastes.length
    ? `<p class="quiet taste-line">${escapeHtml(peer.tastes.join(" · "))}</p>`
    : "";
  const bubbles = thread
    ? thread.messages.map((message) => {
        if (message.kind === "event") return `<p class="event-line">${escapeHtml(message.text)}</p>`;
        const mine = message.sender_id === viewer ? "mine" : "";
        const fromGrok = message.kind === "suggestion" || message.kind === "agent";
        const label = fromGrok ? `<span class="grok-label">Suggested by Grok</span>` : "";
        return `<p class="bubble ${mine}${fromGrok ? " suggestion" : ""}">${label}${escapeHtml(message.text)}</p>`;
      }).join("")
    : `<p class="quiet">Choose a neighbor, or tap a profile. Joining or canceling a plan leaves a message here.</p>`;
  const suggestion = pendingSuggestion
    ? `<aside class="suggestion-card">
        <p class="suggestion-label">Grok suggests</p>
        <p class="suggestion-body">${escapeHtml(pendingSuggestion)}</p>
        <div class="actions">
          <button class="ghost slim" type="button" id="suggestion-skip">Not now</button>
          <button class="primary slim" type="button" id="suggestion-send">Send</button>
        </div>
      </aside>`
    : "";
  const composer = activeChat
    ? `${suggestion}
      <form class="chat-form" id="chat-form">
        <button class="spark" type="button" id="chat-agent" aria-label="Ask Grok for a suggestion">✦</button>
        <textarea id="chat-text" rows="1" placeholder="Message"></textarea>
        <button class="send-round" type="submit" aria-label="Send">↑</button>
      </form>`
    : "";
  const people = (state.residents || []).filter((person) => person.id !== viewer);
  const known = new Set(threads.map((thread) => thread.peer_id));
  const picker = people.map((person) => `
    <button class="thread" type="button" data-chat="${person.id}">
      <strong>${escapeHtml(person.name)}</strong>
      <span class="quiet">${known.has(person.id) ? "Already chatting" : "Start a conversation"}</span>
    </button>
  `).join("");
  root.innerHTML = `
    <div class="message-head">
      <h2>Messages</h2>
      <button class="primary slim" type="button" id="new-chat">New conversation</button>
    </div>
    <div class="new-chat-list" id="new-chat-list" hidden>${picker}</div>
    <div class="thread-list">${list || `<p class="quiet">No conversations yet. Start one with New conversation.</p>`}</div>
    <div class="chat">${peerTastes}${bubbles}</div>
    ${composer}
  `;
  bindChatButtons(root);
  const newChat = document.querySelector("#new-chat");
  const newList = document.querySelector("#new-chat-list");
  if (newChat && newList) {
    newChat.addEventListener("click", () => {
      newList.hidden = !newList.hidden;
      newChat.textContent = newList.hidden ? "New conversation" : "Close";
    });
  }
  const form = document.querySelector("#chat-form");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const field = document.querySelector("#chat-text");
      const text = field.value.trim();
      if (!text) return;
      sendChat(text).catch((error) => setStatus(error.message));
    });
  }
  const agent = document.querySelector("#chat-agent");
  if (agent) {
    agent.addEventListener("click", () => {
      const field = document.querySelector("#chat-text");
      askChatAgent(field.value.trim()).catch((error) => setStatus(error.message));
    });
  }
  const skip = document.querySelector("#suggestion-skip");
  if (skip) {
    skip.addEventListener("click", () => {
      pendingSuggestion = "";
      renderMessages();
    });
  }
  const useSuggestion = document.querySelector("#suggestion-send");
  if (useSuggestion) {
    useSuggestion.addEventListener("click", () => {
      const text = pendingSuggestion;
      pendingSuggestion = "";
      sendChat(text, "suggestion").catch((error) => setStatus(error.message));
    });
  }
}

function renderResident() {
  paintComposerAvatar();
  renderFriendsPage();
  renderMessages();
  renderNotices();
  renderPlans(document.querySelector("#plans"), visiblePlans());
  renderPlans(document.querySelector("#yours"), myPlans(), true);
  renderKeys();
}

function renderStaff() {
  const alerts = document.querySelector("#alerts");
  alerts.innerHTML = state.alerts.length
    ? state.alerts.map((alert) => `<article class="alert"><strong>${escapeHtml(alert.name)}</strong><p>${escapeHtml(alert.summary)}</p></article>`).join("")
    : `<p class="quiet">No one has asked for an in-person check.</p>`;
  renderPlans(document.querySelector("#staff-plans"), [...state.plans].reverse());
  renderKeys();
  const notes = document.querySelector("#notes");
  notes.innerHTML = state.notes.length
    ? state.notes.map((note) => {
        const kept = note.withheld.length ? note.withheld.join(", ") : "nothing sensitive";
        const card = note.card ? `${note.card.activity} in the ${note.card.place}` : note.summary || "Not posted";
        return `<article class="note-row"><strong>${escapeHtml(note.name)}</strong><p>${escapeHtml(card)}</p><p class="quiet">Withheld: ${escapeHtml(kept)}</p></article>`;
      }).join("")
    : `<p class="quiet">No notes yet.</p>`;
}

async function schedulePreview() {
  const fence = document.querySelector("#fence");
  if (!fence) return;
  fence.dataset.live = "1";
  window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(async () => {
    const text = document.querySelector("#note").value;
    if (!text.trim()) {
      fence.innerHTML = "";
      return;
    }
    const decision = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resident_id: viewer,
        text,
        time: document.querySelector("#when").value,
        audience: currentAudience(),
      }),
    });
    renderFence(decision, text);
  }, 200);
}

async function shareNote() {
  const text = document.querySelector("#note").value.trim();
  if (!text) {
    setStatus("Write a note or choose an activity.");
    return;
  }
  setStatus("Saving…");
  const payload = await api("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resident_id: viewer,
      text,
      time: document.querySelector("#when").value,
      audience: currentAudience(),
    }),
  });
  state = payload.state;
  document.querySelector("#fence").dataset.live = "0";
  document.querySelector("#note").value = "";
  document.querySelector("#fence").innerHTML = "";
  setComposerOpen(false);
  setStatus("Posted. The private parts stayed off the feed.");
  renderResident();
  renderKeys();
}

async function cancelPlan(planId) {
  setStatus("Updating the plan…");
  state = await api(`/api/plans/${planId}/leave`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer }),
  });
  setStatus("Updated. The other people were notified.");
  renderResident();
}

async function inviteFriend(planId, friendId) {
  setStatus("Sending the invite…");
  state = await api(`/api/plans/${planId}/invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer, friend_id: friendId }),
  });
  setStatus("Invited. They'll see it in Notices.");
  renderResident();
}

async function markRead(noteId) {
  state = await api("/api/notifications/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer, id: noteId || null }),
  });
  renderResident();
}

async function joinPlan(planId) {
  setStatus("Adding you to the plan…");
  const payload = await api(`/api/plans/${planId}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resident_id: viewer }),
  });
  state = payload.state;
  setStatus("You're on the plan.");
  renderResident();
}

function hearPlan(planId) {
  const plan = state.plans.find((item) => item.id === planId);
  if (!plan) return;
  const grouped = (plan.resident_ids || []).length >= 2;
  if (plan.audio || grouped) {
    const audio = new Audio(`/api/plans/${plan.id}/audio`);
    audio.play().catch(() => speakPlan(plan));
    return;
  }
  speakPlan(plan);
}

function speakPlan(plan) {
  const utterance = new SpeechSynthesisUtterance(plan.line || `${plan.names.join(" and ")} will meet in the ${plan.place} at ${plan.time}.`);
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
  setStatus("Playing the browser voice. Add XAI_API_KEY for Grok Voice.");
}

function downsample(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples;
  const ratio = fromRate / toRate;
  const length = Math.round(samples.length / ratio);
  const result = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    result[index] = samples[Math.min(samples.length - 1, Math.round(index * ratio))];
  }
  return result;
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let index = 0; index < samples.length; index += 1, offset += 2) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };
  const silent = context.createGain();
  silent.gain.value = 0;
  source.connect(processor);
  processor.connect(silent);
  silent.connect(context.destination);
  recorder = {
    async stop() {
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      processor.disconnect();
      source.disconnect();
      silent.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const mixed = new Float32Array(length);
      let cursor = 0;
      chunks.forEach((chunk) => {
        mixed.set(chunk, cursor);
        cursor += chunk.length;
      });
      const samples = downsample(mixed, context.sampleRate, 16000);
      await context.close();
      return encodeWav(samples, 16000);
    },
  };
}

async function finishRecording() {
  const button = document.querySelector("#talk");
  button.classList.remove("recording");
  button.textContent = "Start talking";
  window.clearInterval(listenTimer);
  if (!recorder) return;
  const active = recorder;
  recorder = null;
  setStatus("Transcribing…");
  try {
    const wav = await active.stop();
    if (wav.size < 26000) {
      setStatus("That clip was too short. Say what you'd like to do, then tap Send what I said.");
      return;
    }
    const payload = await api("/api/notes/audio", {
      method: "POST",
      headers: {
        "Content-Type": "audio/wav",
        "X-Resident-Id": viewer,
        "X-Meet-Time": document.querySelector("#when").value,
        "X-Audience": currentAudience(),
      },
      body: wav,
    });
    state = payload.state;
    document.querySelector("#fence").dataset.live = "0";
    setStatus("Heard you. Private details stayed off the board.");
    renderResident();
  } catch (error) {
    setStatus(error.message);
  }
}

async function toggleTalk() {
  const button = document.querySelector("#talk");
  if (recorder) {
    finishRecording();
    return;
  }
  if (arming) return;
  arming = true;
  try {
    await startRecording();
    button.classList.add("recording");
    button.textContent = "Send what I said";
    const started = Date.now();
    setStatus("Listening… tap Send what I said when you are done.");
    listenTimer = window.setInterval(() => {
      const seconds = Math.round((Date.now() - started) / 1000);
      setStatus(`Listening… ${seconds}s. Tap Send what I said when you are done.`);
    }, 500);
  } catch (error) {
    setStatus("The microphone is unavailable. You can still type the note.");
  } finally {
    arming = false;
  }
}

document.querySelector("#story").addEventListener("click", async () => {
  await api("/api/demo/story", { method: "POST" });
  await refresh();
  setStatus("Loaded Helen, Frank, and Ruth.");
});

const reset = document.querySelector("#reset");
if (reset) {
  reset.addEventListener("click", async () => {
    await api("/api/demo/reset", { method: "POST" });
    await refresh();
  });
}

document.querySelector("#account").value = viewer;
document.querySelector("#account").addEventListener("change", (event) => {
  viewer = event.target.value;
  sessionStorage.setItem("courtyard-resident", viewer);
  const fence = document.querySelector("#fence");
  if (fence) fence.dataset.live = "0";
  refresh().catch((error) => setStatus(error.message));
});

if (document.querySelector("#share")) {
  renderChoices();
  document.querySelector("#share").addEventListener("click", () => {
    shareNote().catch((error) => setStatus(error.message));
  });
  document.querySelector("#note").addEventListener("input", () => {
    schedulePreview().catch((error) => setStatus(error.message));
  });
  document.querySelector("#talk").addEventListener("click", () => {
    toggleTalk();
  });
  document.querySelector("#audience-toggle").addEventListener("click", () => {
    setAudience(currentAudience() !== "friends");
    if (document.querySelector("#note").value.trim()) {
      schedulePreview().catch((error) => setStatus(error.message));
    }
  });
  document.querySelector("#bell").addEventListener("click", () => {
    noticesOpen = !noticesOpen;
    if (state) renderNotices();
  });
  document.querySelector("#composer-open").addEventListener("click", () => setComposerOpen(true));
  document.querySelector("#composer-close").addEventListener("click", () => setComposerOpen(false));
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      noticesOpen = false;
      showPage(tab.dataset.page);
      if (state) renderNotices();
    });
  });
  document.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      feedFilter = tab.dataset.feed;
      document.querySelectorAll(".filter-tab").forEach((item) => {
        item.classList.toggle("selected", item === tab);
      });
      if (state) renderPlans(document.querySelector("#plans"), visiblePlans());
    });
  });
  document.querySelector("#when").addEventListener("change", () => {
    if (document.querySelector("#note").value.trim()) {
      schedulePreview().catch((error) => setStatus(error.message));
    }
  });
}

refresh().catch((error) => setStatus(error.message));
window.setInterval(() => {
  refresh().catch(() => {});
}, 4000);
