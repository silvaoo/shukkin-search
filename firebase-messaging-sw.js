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

   【先に開いてしまう理由】
   Androidでは、いったん「開いている画面を探す」処理をはさむと、
   その間に利用者の操作から離れたとみなされ、
   アプリを開く指示が受け付けられなくなる。
   そこで、探すより先に開く指示を出しておく。 */
const APP_HOME = new URL('./', self.location.href).href;

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  // 探す前に、まず開く指示を出す
  const opening = (clients && clients.openWindow)
    ? clients.openWindow(APP_HOME)
    : Promise.resolve(null);

  event.waitUntil(
    opening.catch(function () {
      // 開けなかったときだけ、すでに開いている画面を前に出す
      return clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function (list) {
          for (const c of list) {
            if (c.url && c.url.indexOf(APP_HOME) === 0 && 'focus' in c) return c.focus();
          }
        });
    })
  );
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

/* ここから下は Firebase の部品。宛先（トークン）の発行に必要。
   読み込みに失敗しても、上の受信処理は動くようにしてある。 */
try {
  importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
  importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

  firebase.initializeApp({
    apiKey: "AIzaSyAtawIGwf6hfZU3o79JN5R83CLmTivQVIg",
    authDomain: "shukkin-notify.firebaseapp.com",
    projectId: "shukkin-notify",
    storageBucket: "shukkin-notify.firebasestorage.app",
    messagingSenderId: "587667482421",
    appId: "1:587667482421:web:080064fd0444ff49f90e7c"
  });
  firebase.messaging();
  // 表示は上の push 処理が行うので、ここでは何もしない
} catch (e) {
  // 読み込めなくても通知の表示には影響しない
}
