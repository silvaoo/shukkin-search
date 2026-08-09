/* =========================================================
   出勤通知の送信スクリプト（5ダイヤ共通）

   GitHub Actions から5分おきに呼ばれる。
   npm でのインストールは不要。Node に最初から入っている機能だけで動く。

   やっていること:
     1. Firestore から、通知を希望している端末の一覧を読む
     2. 各アプリの index.html から勤務データをそのまま読み取る
        → データを二重に持たないので、ダイヤ改正時に直す場所が増えない
     3. いま通知すべき人がいれば、Firebase 経由で送る
     4. 使えなくなった宛先は自動で消す
   ========================================================= */

const crypto = require('crypto');

const PROJECT_ID = 'shukkin-notify';
const FS_ROOT = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;

/* 5つのアプリの情報。data は勤務データの持ち方が2通りあるため、その区別。
     'obj' … const DB={...} 形式（学園前A・北大和C・予備）
     'arr' … const 〜DaiyaData=[...] 形式（生駒・北大和B） */
const APPS = {
  a:     { name: '学園前Ａ',   repo: 'shukkin-search',        cycle: 92, kind: 'obj' },
  ikoma: { name: '生駒',       repo: 'shukkin-search-ikoma',  cycle: 59, kind: 'arr', varName: 'ikomaDaiyaData' },
  ba:    { name: '北大和Ｂ',   repo: 'shukkin-search-ba',     cycle: 27, kind: 'arr', varName: 'baDaiyaData' },
  c:     { name: '北大和Ｃ',   repo: 'shukkin-search-c',      cycle: 8,  kind: 'obj' },
  yobi:  { name: '予備',       repo: 'shukkin-search-yobi',   cycle: 25, kind: 'obj' }
};

const DWJ = ['日', '月', '火', '水', '木', '金', '土'];
const p2 = (n) => String(n).padStart(2, '0');

/* 日本時間の「いま」。GitHubのサーバーは世界標準時なので9時間ずらす */
function nowJST() {
  return new Date(Date.now() + 9 * 60 * 60 * 1000);
}
function ymd(d) {
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
}
function hhmm(d) {
  return `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}

/* ---------- 各アプリの勤務データを読み込む ---------- */
async function loadApp(code) {
  const info = APPS[code];
  const url = `https://raw.githubusercontent.com/silvaoo/${info.repo}/main/index.html`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${info.repo} の取得に失敗しました (${res.status})`);
  const html = await res.text();

  const holidays = html.match(/const HOLIDAYS\s*=\s*new Set\(\[[\s\S]*?\]\);/);
  if (!holidays) throw new Error(`${info.repo}: 祝日一覧が見つかりません`);

  let code_js;
  if (info.kind === 'obj') {
    const dbLine = html.split('\n').find((l) => l.trim().startsWith('const DB={'));
    const obon = html.match(/const OBON_DAYS\s*=\s*new Set\(\[[^\]]*\]\);/);
    if (!dbLine || !obon) throw new Error(`${info.repo}: 勤務データが見つかりません`);
    code_js = dbLine + '\n' + holidays[0] + '\n' + obon[0]
      + '\nreturn { kind:"obj", DB:DB, HOLIDAYS:HOLIDAYS, BON:OBON_DAYS };';
  } else {
    const arr = html.match(new RegExp('const ' + info.varName + '\\s*=\\s*\\[[\\s\\S]*?\\n\\s*\\];'));
    const bon = html.match(/const BON_SPECIAL_DATES\s*=\s*\[[^\]]*\];/);
    if (!arr || !bon) throw new Error(`${info.repo}: 勤務データが見つかりません`);
    code_js = arr[0] + '\n' + holidays[0] + '\n' + bon[0]
      + `\nreturn { kind:"arr", ROWS:${info.varName}, HOLIDAYS:HOLIDAYS, BON:new Set(BON_SPECIAL_DATES) };`;
  }
  const data = new Function(code_js)();
  data.cycle = info.cycle;
  data.name = info.name;
  return data;
}

/* 平日 / 土 / 日祝 の判定。アプリ側と同じ規則に揃えてある。
   生駒・北大和Bは日曜の区分名が「日」なので、両方を見る。 */
function dayType(d, data) {
  const iso = ymd(d);
  const w = d.getUTCDay();
  if (data.BON.has(iso)) return ['土'];
  if (w === 0 || data.HOLIDAYS.has(iso)) return ['日祝', '日'];
  if (w === 6) return ['土'];
  return ['平'];
}

/* 基準日と基準番号から、対象日のダイヤ番号を出す */
function dialFor(dateUTC, baseDateStr, baseDial, cycle) {
  const base = new Date(baseDateStr + 'T00:00:00Z');
  const diff = Math.round((dateUTC - base) / 86400000);
  return ((baseDial - 1 + diff) % cycle + cycle) % cycle + 1;
}

/* その日の出勤時刻を取り出す。公休や時刻不明は null */
function shiftStart(dial, dateUTC, data) {
  const types = dayType(dateUTC, data);
  let raw = null, note = '';

  if (data.kind === 'obj') {
    const rec = data.DB[dial];
    if (!rec) return null;
    let e = null;
    for (const t of types) { if (rec[t]) { e = rec[t]; break; } }
    if (!e || !e.o || e.o === '—' || !e.o.includes('〜')) return null;
    raw = e.o.split('〜')[0];
    note = e.n || '';
  } else {
    let row = null;
    for (const t of types) {
      row = data.ROWS.find((r) => r.id === dial && r.dayType === t);
      if (row) break;
    }
    if (!row) row = data.ROWS.find((r) => r.id === dial && r.dayType === '全');
    if (!row || !row.start) return null;
    raw = String(row.start);
    note = row.memo || '';
  }

  // 中間解放（例 6:20/11:56）は最初の出勤時刻を使う
  const st = raw.split('/')[0].trim();
  const m = st.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;                      // 「公休」などはここで除かれる
  return { h: +m[1], m: +m[2], text: st, note };
}

/* 備考に、出勤時刻が違う条件が書かれていないか調べる。
   例: 学園前A 31番平日は 近大通常17:09 / 休暇中18:38 で1時間半ちがう。
   誤った時刻だけを知らせると遅刻につながるので、本文に添える。 */
function altStarts(baseText, note) {
  if (!note) return [];
  const found = [...String(note).matchAll(/(\d{1,2}:\d{2})〜/g)].map((m) => m[1]);
  return [...new Set(found.filter((t) => t !== baseText))];
}

/* 次に通知すべき予定を求める。今日から14日先まで探す */
function nextPlan(t, data, now) {
  for (let i = 0; i <= 14; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    d.setUTCDate(d.getUTCDate() + i);
    const dial = dialFor(d, t.baseDate, t.baseDial, data.cycle);
    const st = shiftStart(dial, d, data);
    if (!st) continue;
    const start = new Date(d.getTime() + (st.h * 60 + st.m) * 60000);
    const notify = new Date(start.getTime() - t.lead * 60000);
    if (notify.getTime() + 30 * 60000 < now.getTime()) continue;
    return { date: d, dial, start, notify, startText: st.text, note: st.note };
  }
  return null;
}

/* ---------- Google の認証 ---------- */
async function getAccessToken(sa) {
  const now = Math.floor(Date.now() / 1000);
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const unsigned = b64({ alg: 'RS256', typ: 'JWT' }) + '.' + b64({
    iss: sa.client_email,
    // 通知の送信と、登録一覧の読み書きの両方に使う
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
    const url = `${FS_ROOT}/notifyTargets?pageSize=300`
              + (pageToken ? `&pageToken=${encodeURIComponent(pageToken)}` : '');
    const res = await fetch(url, { headers: { Authorization: `Bearer ${at}` } });
    if (!res.ok) throw new Error('登録一覧を読めません: ' + res.status + ' ' + (await res.text()).slice(0, 200));
    const j = await res.json();
    for (const d of (j.documents || [])) {
      const f = d.fields || {};
      const id = d.name.split('/').pop();
      const v = {
        id,
        app: f.app && f.app.stringValue,
        token: f.token && f.token.stringValue,
        baseDate: f.baseDate && f.baseDate.stringValue,
        baseDial: f.baseDial && parseInt(f.baseDial.integerValue),
        lead: f.lead && parseInt(f.lead.integerValue)
      };
      if (v.app && v.token && v.baseDate && v.baseDial && v.lead) out.push(v);
    }
    pageToken = j.nextPageToken || '';
    if (!pageToken) break;
  }
  return out;
}

/* 使えなくなった宛先を消す */
async function deleteTarget(at, id) {
  try {
    await fetch(`${FS_ROOT}/notifyTargets/${id}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${at}` }
    });
  } catch (e) { /* 消せなくても致命的ではない */ }
}

/* ---------- 通知を1件送る ----------
   data だけを送り、表示は端末側の firebase-messaging-sw.js に任せる。
   （notification を付けると通知が二重に出るため） */
async function sendOne(at, token, title, body) {
  const res = await fetch(`https://fcm.googleapis.com/v1/projects/${PROJECT_ID}/messages:send`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        token,
        data: { title, body, tag: 'shukkin-notify' },
        webpush: { headers: { Urgency: 'high', TTL: '1800' } }
      }
    })
  });
  return { ok: res.ok, status: res.status, body: await res.text() };
}

/* ---------- 本体 ---------- */
(async function main() {
  const isTest = process.argv.includes('--test');
  const now = nowJST();

  console.log('=== 出勤通知バッチ ===');
  console.log('日本時間:', ymd(now), hhmm(now), `(${DWJ[now.getUTCDay()]})`);
  console.log('モード  :', isTest ? 'お試し（時刻に関係なく送る）' : '通常');

  const saRaw = process.env.FIREBASE_SA;
  if (!saRaw) throw new Error('FIREBASE_SA が設定されていません');
  const at = await getAccessToken(JSON.parse(saRaw));

  const targets = await loadTargets(at);
  console.log('登録数  :', targets.length, '件');

  if (!targets.length) { console.log('\n送信対象がありません'); return; }

  // 必要なアプリのデータだけ読み込む
  const used = [...new Set(targets.map((t) => t.app))].filter((a) => APPS[a]);
  const cache = {};
  for (const a of used) {
    try { cache[a] = await loadApp(a); console.log(`  ${APPS[a].name}: 読み込み完了`); }
    catch (e) { console.log(`  ${a}: 読み込み失敗 ${e.message}`); }
  }
  console.log('');

  let sent = 0, skipped = 0, failed = 0;

  for (const t of targets) {
    const data = cache[t.app];
    const who = `[${(APPS[t.app] || {}).name || t.app}] ${t.id.slice(0, 14)}…`;
    if (!data) { console.log(`- ${who}: データなし`); continue; }

    const plan = nextPlan(t, data, now);
    if (!plan) { console.log(`- ${who}: 予定なし`); skipped++; continue; }

    const planStr = `${plan.date.getUTCMonth() + 1}/${plan.date.getUTCDate()}`
      + `(${DWJ[plan.date.getUTCDay()]}) ${plan.dial}番 出勤${plan.startText}`
      + ` → 通知 ${hhmm(plan.notify)}`;

    // 予定時刻を過ぎてから15分以内なら送る
    const diffMin = (now.getTime() - plan.notify.getTime()) / 60000;
    if (!isTest && !(diffMin >= 0 && diffMin < 15)) {
      console.log(`- ${who}: ${planStr}（まだ / 差${diffMin.toFixed(0)}分）`);
      skipped++;
      continue;
    }

    const leadText = t.lead === 120 ? '2時間' : (t.lead === 60 ? '1時間' : `${t.lead}分`);
    let body = `${plan.date.getUTCMonth() + 1}/${plan.date.getUTCDate()}`
      + `(${DWJ[plan.date.getUTCDay()]}) ${plan.dial}番ダイヤ\n`
      + `出勤 ${plan.startText}（あと${leadText}）`;
    const alts = altStarts(plan.startText, plan.note);
    if (alts.length) body += `\n※条件により ${alts.join('／')} の場合あり`;

    const r = await sendOne(at, t.token, '🚌 まもなく出勤です', body);
    if (r.ok) {
      console.log(`✅ ${who}: 送信  ${planStr}`);
      sent++;
    } else {
      console.log(`❌ ${who}: 失敗 (${r.status}) ${r.body.slice(0, 160)}`);
      failed++;
      // 宛先が無効（機種変・アプリ削除など）なら登録から消す
      if (r.status === 404 || (r.status === 400 && /registration-token|INVALID_ARGUMENT/i.test(r.body))) {
        await deleteTarget(at, t.id);
        console.log('    → 使えない宛先だったので登録から削除しました');
      }
    }
  }

  console.log(`\n送信 ${sent} 件 / 見送り ${skipped} 件 / 失敗 ${failed} 件`);
})().catch((e) => {
  console.error('エラー:', e.message);
  process.exit(1);
});
