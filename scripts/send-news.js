/* =========================================================
   お知らせの一斉送信

   営業所からの通告など、すぐ全員に伝えたいときに使う。
   GitHub の Actions 画面から手動で動かす。自動では動かない。

   誤送信を防ぐため、「本当に送る」を選ばない限り
   宛先の人数と本文を表示するだけで終わる（下書き確認）。
   ========================================================= */

const crypto = require('crypto');

const PROJECT_ID = 'shukkin-notify';
const FS_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;

const APP_NAMES = {
  a: '学園前Ａ', ikoma: '生駒', ba: '北大和Ｂ', c: '北大和Ｃ', yobi: '予備'
};

/* ---------- Google の認証 ---------- */
async function getAccessToken(sa) {
  const now = Math.floor(Date.now() / 1000);
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const unsigned = b64({ alg: 'RS256', typ: 'JWT' }) + '.' + b64({
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/firebase.messaging'
         + ' https://www.googleapis.com/auth/datastore',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now, exp: now + 3600
  });
  const sig = crypto.createSign('RSA-SHA256').update(unsigned).sign(sa.private_key, 'base64url');
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: unsigned + '.' + sig
    })
  });
  const j = await res.json();
  if (!j.access_token) throw new Error('認証に失敗しました: ' + JSON.stringify(j));
  return j.access_token;
}

/* ---------- 登録一覧を読む ---------- */
async function loadTargets(at) {
  const out = [];
  let pageToken = '';
  for (let guard = 0; guard < 20; guard++) {
    const url = `${FS_ROOT}/pushTokens?pageSize=300`
              + (pageToken ? `&pageToken=${encodeURIComponent(pageToken)}` : '');
    const res = await fetch(url, { headers: { Authorization: `Bearer ${at}` } });
    if (!res.ok) throw new Error('登録一覧を読めません: ' + res.status);
    const j = await res.json();
    for (const d of (j.documents || [])) {
      const f = d.fields || {};
      const id = d.name.split('/').pop();
      const app = f.app && f.app.stringValue;
      const token = f.token && f.token.stringValue;
      if (app && token) out.push({ id, app, token });
    }
    pageToken = j.nextPageToken || '';
    if (!pageToken) break;
  }
  return out;
}

async function deleteTarget(at, id) {
  try {
    await fetch(`${FS_ROOT}/pushTokens/${id}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${at}` }
    });
  } catch (e) { /* 消せなくても致命的ではない */ }
}

/* 通知を1件送る。表示は端末側の firebase-messaging-sw.js に任せる */
async function sendOne(at, token, title, body) {
  const res = await fetch(`https://fcm.googleapis.com/v1/projects/${PROJECT_ID}/messages:send`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        token,
        data: { title, body, tag: 'shukkin-news' },
        webpush: { headers: { Urgency: 'high', TTL: '86400' } }
      }
    })
  });
  return { ok: res.ok, status: res.status, body: await res.text() };
}

/* ---------- 本体 ---------- */
(async function main() {
  const title   = (process.env.MSG_TITLE || '').trim();
  const body    = (process.env.MSG_BODY  || '').trim();
  const appsRaw = (process.env.MSG_APPS  || '').trim();
  const confirm = (process.env.MSG_CONFIRM || '').trim() === 'true';

  console.log('=== お知らせの一斉送信 ===\n');

  if (!title) throw new Error('タイトルが空です');
  if (!body)  throw new Error('本文が空です');

  // 対象アプリ。空欄またはallなら全部
  let apps;
  if (!appsRaw || appsRaw.toLowerCase() === 'all') {
    apps = Object.keys(APP_NAMES);
  } else {
    apps = appsRaw.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean);
    const bad = apps.filter((a) => !APP_NAMES[a]);
    if (bad.length) {
      throw new Error('知らないダイヤ名です: ' + bad.join(',')
        + '\n  使えるのは: ' + Object.keys(APP_NAMES).join(' / ') + ' / all');
    }
  }

  console.log('対象ダイヤ:', apps.map((a) => APP_NAMES[a]).join('、'));
  console.log('タイトル  :', title);
  console.log('本文      :');
  body.split('\n').forEach((l) => console.log('    ' + l));
  console.log('');

  const saRaw = process.env.FIREBASE_SA;
  if (!saRaw) throw new Error('FIREBASE_SA が設定されていません');
  const at = await getAccessToken(JSON.parse(saRaw));

  const all = await loadTargets(at);
  const targets = all.filter((t) => apps.includes(t.app));

  // 内訳を出す
  console.log('宛先の内訳:');
  for (const a of Object.keys(APP_NAMES)) {
    const n = all.filter((t) => t.app === a).length;
    const mark = apps.includes(a) ? '→ 送る' : '   送らない';
    console.log(`  ${APP_NAMES[a].padEnd(6, '　')} ${String(n).padStart(4)} 件  ${mark}`);
  }
  console.log(`\n送信対象: ${targets.length} 件\n`);

  if (!confirm) {
    console.log('■ これは下書きの確認です。実際には送っていません。');
    console.log('  送る場合は「本当に送る」を選んで、もう一度実行してください。');
    return;
  }

  if (!targets.length) { console.log('送る相手がいません'); return; }

  let sent = 0, failed = 0;
  for (const t of targets) {
    const r = await sendOne(at, t.token, title, body);
    if (r.ok) { sent++; }
    else {
      failed++;
      console.log(`❌ [${APP_NAMES[t.app]}] ${t.id.slice(0, 14)}… 失敗 (${r.status})`);
      // 宛先が無効（機種変・アプリ削除など）なら登録から消す
      if (r.status === 404 || (r.status === 400 && /registration-token|INVALID_ARGUMENT/i.test(r.body))) {
        await deleteTarget(at, t.id);
        console.log('    → 使えない宛先だったので登録から削除しました');
      }
    }
  }

  console.log(`\n送信 ${sent} 件 / 失敗 ${failed} 件`);
})().catch((e) => {
  console.error('エラー:', e.message);
  process.exit(1);
});
