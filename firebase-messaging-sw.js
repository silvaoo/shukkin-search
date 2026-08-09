/* =========================================================
   出退勤検索くん (学園前Aダイヤ) - プッシュ通知受信用 Service Worker

   これは sw.js とは別の、通知専用のファイル。
   Firebase が「firebase-messaging-sw.js」という名前で探しに来るため、
   ファイル名は変更してはいけない。

   役割:
     アプリを閉じていても、届いたプッシュ通知を画面に出す。
   ========================================================= */

// Firebase の部品を読み込む(古い書き方だが、npm不要でそのまま動く方式)
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

// このアプリがどのFirebaseプロジェクトのものかを伝える設定
firebase.initializeApp({
  apiKey: "AIzaSyAtawIGwf6hfZU3o79JN5R83CLmTivQVIg",
  authDomain: "shukkin-notify.firebaseapp.com",
  projectId: "shukkin-notify",
  storageBucket: "shukkin-notify.firebasestorage.app",
  messagingSenderId: "587667482421",
  appId: "1:587667482421:web:080064fd0444ff49f90e7c"
});

const messaging = firebase.messaging();

/* アプリを閉じている時に通知が届いた場合の処理。
   通知の中身(タイトル・本文)は送信側から渡されたものをそのまま使う。 */
messaging.onBackgroundMessage(function (payload) {
  // 【二重表示を防ぐ】
  // Firebaseの「通知メッセージ」(notification付き)は、ブラウザが自動で1件表示する。
  // ここで重ねて表示すると同じ通知が2件並ぶため、その場合は何もしない。
  // 自動で送る本番用は notification を使わず data だけで送るので、下の処理が動く。
  if (payload && payload.notification) return;

  const d = (payload && payload.data) || {};
  const title = d.title || '🚌 出退勤検索くん';
  const options = {
    body: d.body || '',
    icon: './icons/icon-192.png',
    badge: './icons/icon-192.png',
    tag: d.tag || 'shukkin-push',
    vibrate: [200, 100, 200]
  };
  return self.registration.showNotification(title, options);
});

/* 通知をタップしたらアプリを開く(既に開いていればそれを前面に出す) */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ('focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow('./');
    })
  );
});
