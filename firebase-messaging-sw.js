/* =========================================================
   出退勤検索くん (学園前Ａダイヤ) - プッシュ通知の受信

   ファイル名は firebase-messaging-sw.js から変えてはいけない。
   Firebase がこの名前で探しに来るため。

   【この作りにしている理由】
   通知が届いたのに中身が表示されず、アプリ名だけの空の通知が
   出てしまうことがあった。原因は、外部から読み込む Firebase の
   部品が読めなかったときに、表示処理ごと止まってしまうこと。

   そこで、外部の部品に頼らない受信処理を先に登録しておく。
   これなら読み込みが失敗しても、通知の中身は必ず表示される。
   ========================================================= */

const NOTIFY_ICON  = './icons/icon-192.png';

/* 届いた中身から、表示する内容を取り出す */
function pickContent(raw) {
  let d = {};
  try {
    const j = (raw && typeof raw.json === 'function') ? raw.json() : null;
    if (j) d = j.data || j.notification || j || {};
  } catch (e) {
    try { d = { body: raw.text() }; } catch (e2) { d = {}; }
  }
  return {
    title: d.title || '🚌 出退勤検索くん',
    body:  d.body  || 'お知らせがあります',
    tag:   d.tag   || 'shukkin-push'
  };
}

/* 【本命】通知が届いたときの処理。外部の部品を使わないので確実に動く */
self.addEventListener('push', function (event) {
  const c = pickContent(event.data);
  event.waitUntil(
    self.registration.showNotification(c.title, {
      body: c.body,
      icon: NOTIFY_ICON,
      badge: NOTIFY_ICON,
      tag: c.tag,              // 同じ内容が重なったら1件にまとめる
      renotify: true,
      requireInteraction: false,
      vibrate: [200, 100, 200]
    })
  );
});

/* 通知をタップしたらアプリを開く

   【開く場所を絶対の住所で持つ理由】
   このワーカーは通知専用の区画に置いてある。
   そのため './' と書くと、アプリのトップではなく
   区画の中（存在しない場所）を指してしまう。
   ワーカー自身の住所から、アプリのトップを組み立てる。

   【必ず新しく開く理由】
   すでに開いている画面を前に出す作りにしていたが、
   端末によっては画面の住所が読めないことがあり、
   よその画面（他のダイヤのアプリや管理ページ）を
   前に出してしまう事故が起きた。
   迷いようのない形にして、いつでもこのアプリを開く。
   すでに開いていれば、その画面が前に出る。 */
const APP_HOME = new URL('./', self.location.href).href;

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  // この下で読み込んでいる Firebase の部品も、独自にタップ処理を持っている。
  // そちらは「住所のいちばん上（silvaoo.github.io）」を開こうとするため、
  // Androidでは同じ住所にある別のアプリ（管理ページなど）が
  // 立ち上がってしまうことがあった。
  // ここで後続の処理を止めて、必ずこのアプリを開くようにする。
  if (event.stopImmediatePropagation) event.stopImmediatePropagation();

  if (clients.openWindow) {
    event.waitUntil(clients.openWindow(APP_HOME));
  }
});

/* 新しい版を入れたら、すぐ入れ替わるようにする。

   【clients.claim() は呼ばない】
   呼ぶとこの通知用ワーカーがページの制御を奪い、
   本体側が「新しい版が来た」と誤って判断して更新バナーが出続ける。
   通知を受け取るだけなら、ページの制御を持つ必要はない。

   【skipWaiting() は呼ぶ】
   呼ばないと古い版が居座り、直したはずの動きが反映されない。
   通知の受信とタップの処理しか持たないので、
   途中で入れ替わっても困ることはない。 */
self.addEventListener('install', function () {
  self.skipWaiting();
});

/* 【Firebase の部品はあえて読み込まない】

   以前はここで firebase-messaging-compat.js を読み込んでいたが、
   あの部品は自前でタップ処理を持っており、
   「住所のいちばん上（silvaoo.github.io）」を開こうとする。
   そのため、同じ住所にある別のアプリ（管理ページなど）が
   立ち上がってしまうことがあった。

   通知の受け取りは上の push 処理で自前に行っており、
   宛先（トークン）の発行はアプリ本体側が担っているので、
   このワーカーの中で Firebase を動かす必要はない。 */
