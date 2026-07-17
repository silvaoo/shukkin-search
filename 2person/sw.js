/* =========================================================
   出退勤検索くん (学園前Aダイヤ 2人用) - Service Worker
   目的:
   1. PWAとして「インストール可能」にする(Android Chromeの
      インストールバナー/プロンプトは、有効なfetchハンドラを持つ
      Service Workerが登録されていることが条件のひとつ)
   2. オフラインでも開けるように主要ファイルをキャッシュする
   3. デプロイ更新時に「新しいバージョンがあります」を検知できるようにする
   ========================================================= */

// キャッシュ名にバージョンを入れておき、更新のたびにこの値を変えることで
// 新しいService Workerが「更新あり」と判定されるようにする
const CACHE_VERSION = 'a2-shukkin-v8';
const CACHE_FILES = [
    './',
    './index.html',
    './manifest.json'
];

// インストール時: 主要ファイルをキャッシュに保存
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_VERSION).then((cache) => cache.addAll(CACHE_FILES))
    );
    // ここでは skipWaiting() を呼ばない。
    // 呼ぶと新しい版が即座に切り替わってしまい、更新バナーや通知を出す間がなくなるため。
    // 利用者がバナーをタップした時に SKIP_WAITING メッセージで切り替える。
});

// 有効化時: 古いバージョンのキャッシュを削除
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

// fetch時: キャッシュを優先しつつ、なければネットワークから取得(オフライン対応)
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    event.respondWith(
        caches.match(event.request).then((cached) => {
            const networkFetch = fetch(event.request)
                .then((res) => {
                    // 取得できたら最新版をキャッシュに保存し直す(次回更新検知のため)
                    if (res && res.status === 200) {
                        const resClone = res.clone();
                        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, resClone));
                    }
                    return res;
                })
                .catch(() => cached);
            return cached || networkFetch;
        })
    );
});

// index.html側からの「新バージョンをすぐ有効化して」という指示を受け取る
self.addEventListener('message', (event) => {
    if (event.data === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
