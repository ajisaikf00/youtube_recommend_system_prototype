// UI層: 自動再生 / 無限スクロール / 進捗バー / ログイン表示
// 計測層: play / complete / skip / like / purchase / win-lose イベントをサーバーへ送信
// ※ 概念説明用の架空・簡略化されたフロントエンドです。

const state = {
  userId: null,
  page: 0,
  loading: false,
  cards: [], // 表示中のカード要素（自動再生の"次へ"用）
};

const feedEl = document.getElementById("feed");
const sentinelEl = document.getElementById("sentinel");
const cardTemplate = document.getElementById("card-template");

// ---------- ログイン表示 ----------

document.getElementById("login-btn").addEventListener("click", async () => {
  const select = document.getElementById("user-select");
  const userId = select.value;
  if (!userId) return;

  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  const data = await res.json();

  state.userId = data.user_id;
  document.getElementById("login-status").textContent =
    `ログイン中: ${select.options[select.selectedIndex].text}`;
  document.getElementById("app").classList.remove("hidden");

  loadFeed();
  refreshDebug();
});

document.getElementById("refresh-debug").addEventListener("click", refreshDebug);

async function refreshDebug() {
  if (!state.userId) return;
  const res = await fetch(`/api/debug/user/${state.userId}`);
  const data = await res.json();
  document.getElementById("debug-content").textContent = JSON.stringify(data, null, 2);
}

// ---------- 無限スクロール ----------

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting && !state.loading) {
      loadFeed();
    }
  });
});
observer.observe(sentinelEl);

async function loadFeed() {
  if (!state.userId || state.loading) return;
  state.loading = true;
  sentinelEl.textContent = "読み込み中...";

  const res = await fetch(`/api/feed?page=${state.page}`);
  const data = await res.json();
  state.page += 1;

  data.items.forEach((video) => renderCard(video));

  if (data.battle) {
    showBattle(data.battle.a, data.battle.b);
  }

  state.loading = false;
  sentinelEl.textContent = "スクロールすると次の動画が読み込まれます";
}

// ---------- カード描画 & 計測イベント送信 ----------

function renderCard(video) {
  const node = cardTemplate.content.cloneNode(true);
  const card = node.querySelector(".video-card");
  card.dataset.id = video.id;
  card.dataset.category = video.category;
  // デモ用に再生時間を1/5に短縮（実際の秒数を待つと体験しづらいため）
  card.dataset.duration = Math.max(4, Math.round(video.duration_sec / 5));

  card.querySelector(".video-title").textContent = video.title;
  card.querySelector(".video-meta").textContent =
    `${video.category} ・ ${video.duration_sec}秒 ・ score=${video.score.toFixed(3)}`;

  card.querySelector(".btn-play").addEventListener("click", () => startPlayback(card));
  card.querySelector(".btn-like").addEventListener("click", () => onLike(card));
  card.querySelector(".btn-skip").addEventListener("click", () => onSkip(card));
  card.querySelector(".btn-purchase").addEventListener("click", () => onPurchase(card));

  feedEl.appendChild(node);
  state.cards.push(card);
}

function sendEvent(videoId, type, value = null) {
  fetch("/api/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, type, value }),
  }).then(refreshDebug);
}

// ---------- 再生 / 進捗バー / 自動再生 ----------

function startPlayback(card) {
  if (card.dataset.playing === "1") return;
  card.dataset.playing = "1";
  card.dataset.progress = card.dataset.progress || "0";

  sendEvent(Number(card.dataset.id), "play");

  const fill = card.querySelector(".progress-fill");
  const durationMs = Number(card.dataset.duration) * 1000;
  const stepMs = 100;

  const timer = setInterval(() => {
    if (card.dataset.playing !== "1") {
      clearInterval(timer);
      return;
    }
    let progress = Number(card.dataset.progress) + (stepMs / durationMs) * 100;
    progress = Math.min(progress, 100);
    card.dataset.progress = String(progress);
    fill.style.width = progress + "%";

    if (progress >= 100) {
      clearInterval(timer);
      onComplete(card);
    }
  }, stepMs);
  card.dataset.timerId = String(timer);
}

function stopPlayback(card) {
  card.dataset.playing = "0";
  if (card.dataset.timerId) clearInterval(Number(card.dataset.timerId));
}

function onComplete(card) {
  stopPlayback(card);
  card.classList.add("completed");
  sendEvent(Number(card.dataset.id), "complete");
  runAutoplayCountdown(card);
}

function onSkip(card) {
  stopPlayback(card);
  sendEvent(Number(card.dataset.id), "skip", Number(card.dataset.progress || 0));
  goToNextCard(card);
}

function onLike(card) {
  card.classList.toggle("liked");
  sendEvent(Number(card.dataset.id), "like");
}

function onPurchase(card) {
  sendEvent(Number(card.dataset.id), "purchase");
  const btn = card.querySelector(".btn-purchase");
  btn.textContent = "✅ 購入イベント送信済み";
  btn.disabled = true;
}

// 「区切りよく終わらせず、やめる側にだけ能動的コストを課す」自動再生の演出
function runAutoplayCountdown(card) {
  const overlay = card.querySelector(".autoplay-overlay");
  const countdownEl = overlay.querySelector(".countdown");
  overlay.classList.remove("hidden");

  let remaining = 5;
  countdownEl.textContent = remaining;
  const interval = setInterval(() => {
    remaining -= 1;
    countdownEl.textContent = remaining;
    if (remaining <= 0) {
      clearInterval(interval);
      overlay.classList.add("hidden");
      goToNextCard(card);
    }
  }, 1000);

  // ユーザーがスキップ等で介入したらカウントダウンを止められるように保持
  card.dataset.autoplayInterval = String(interval);
}

function goToNextCard(card) {
  const idx = state.cards.indexOf(card);
  const next = state.cards[idx + 1];
  if (next) {
    next.scrollIntoView({ behavior: "smooth", block: "center" });
    startPlayback(next);
  }
  // 次がまだ読み込まれていなければ、無限スクロールが読み込むのを待つ
}

// ---------- 勝敗（バトルUI） ----------

function showBattle(a, b) {
  const modal = document.getElementById("battle-modal");
  const [btnA, btnB] = modal.querySelectorAll(".battle-choice");
  btnA.textContent = `${a.title}\n(${a.category})`;
  btnB.textContent = `${b.title}\n(${b.category})`;
  modal.classList.remove("hidden");

  const cleanup = () => {
    modal.classList.add("hidden");
    btnA.replaceWith(btnA.cloneNode(true));
    btnB.replaceWith(btnB.cloneNode(true));
  };

  modal.querySelectorAll(".battle-choice")[0].onclick = () => {
    reportBattle(a.id, b.id);
    cleanup();
  };
  modal.querySelectorAll(".battle-choice")[1].onclick = () => {
    reportBattle(b.id, a.id);
    cleanup();
  };
}

function reportBattle(winnerId, loserId) {
  fetch("/api/battle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ winner_id: winnerId, loser_id: loserId }),
  }).then(refreshDebug);
}
