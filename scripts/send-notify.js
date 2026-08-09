/* =========================================================
   出勤通知の送信スクリプト（学園前Aダイヤ）

   GitHub Actions から定期的に呼ばれる。
   npm でのインストールは一切不要。Node に最初から入っている機能だけで動く。

   やっていること:
     1. index.html から勤務データ(DB)と祝日一覧をそのまま読み取る
        → データを二重に持たないので、ダイヤ改正のとき修正箇所が増えない
     2. notify-targets.json に登録された人ごとに、次の出勤時刻を計算
     3. いま送るべき人がいれば、Firebase 経由で通知を送る
   ========================================================= */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.join(__dirname, '..');
const PROJECT_ID = 'shukkin-notify';

/* 日本時間の「いま」を求める。
   GitHub のサーバーは世界標準時で動いているため、9時間ずらす必要がある。 */
function nowJST() {
  const d = new Date();
  return new Date(d.getTime() + 9 * 60 * 60 * 1000);
}
function fmtJST(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} `
       + `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/* ---------- index.html から勤務データを取り出す ---------- */
function loadShiftData() {
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  const dbLine = html.split('\n').find((l) => l.startsWith('const DB={'));
  const holidays = html.match(/const HOLIDAYS=new Set\(\[[\s\S]*?\]\);/);
  const obon = html.match(/const OBON_DAYS=new Set\(\[[^\]]*\]\);/);
  if (!dbLine || !holidays || !obon) throw new Error('index.html から勤務データを読み取れませんでした');

  const sandbox = {};
  const code = dbLine + '\n' + holidays[0] + '\n' + obon[0]
    + '\nreturn { DB: DB, HOLIDAYS: HOLIDAYS, OBON_DAYS: OBON_DAYS };';
  return new Function(code)();
}

/* 平日 / 土 / 日祝 の判定。アプリ側と同じ規則で揃えてある */
function dayType(d, data) {
  const p = (n) => String(n).padStart(2, '0');
  const iso = `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
  const w = d.getUTCDay();
  if (data.OBON_DAYS.has(iso)) return '土';
  if (w === 0 || data.HOLIDAYS.has(iso)) return '日祝';
  if (w === 6) return '土';
  return '平';
}

/* 基準日と基準番号から、対象日のダイヤ番号を出す。
   番号は1日ごとに1つ進み、92日で一巡する。 */
function dialFor(dateUTC, baseDateStr, baseDial) {
  const base = new Date(baseDateStr + 'T00:00:00Z');
  const diff = Math.round((dateUTC - base) / 86400000);
  return ((baseDial - 1 + diff) % 92 + 92) % 92 + 1;
}

/* その日の出勤時刻を取り出す。公休や時刻不明のものは null */
function shiftStart(dial, dateUTC, data) {
  const rec = data.DB[dial];
  if (!rec) return null;
  const e = rec[dayType(dateUTC, data)];
  if (!e || !e.o || e.o === '—' || !e.o.includes('〜')) return null;
  const st = e.o.split('〜')[0].split('/')[0].trim();
  const m = st.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  return { h: +m[1], m: +m[2], text: st, note: e.n || '' };
}

/* 備考欄に、出勤時刻が違う条件が書かれていないか調べる。
   例: 31番平日は「近大通常17:09 / 休暇中18:38」で1時間半ちがう。
   誤った時刻だけを知らせると遅刻につながるため、本文に添える。 */
function altStarts(baseText, note) {
  if (!note) return [];
  const found = [...note.matchAll(/(\d{1,2}:\d{2})〜/g)].map((m) => m[1]);
  return [...new Set(found.filter((t) => t !== baseText))];
}

/* 次に通知すべき時刻を求める。今日から14日先まで探す */
function nextPlan(target, data, now) {
  for (let i = 0; i <= 14; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    d.setUTCDate(d.getUTCDate() + i);
    const dial = dialFor(d, target.baseDate, target.baseDial);
    const st = shiftStart(dial, d, data);
    if (!st) continue;
    const start = new Date(d.getTime() + (st.h * 60 + st.m) * 60000);
    const notify = new Date(start.getTime() - target.lead * 60000);
    if (notify.getTime() + 30 * 60000 < now.getTime()) continue;   // 30分以上前は見送る
    return { date: d, dial, start, notify, startText: st.text, note: st.note };
  }
  return null;
}

/* ---------- Firebase に送るための認証 ---------- */
async function getAccessToken(sa) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'RS256', typ: 'JWT' };
  const claim = {
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/firebase.messaging',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600
  };
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const unsigned = `${b64(header)}.${b64(claim)}`;
  const sig = crypto.createSign('RSA-SHA256').update(unsigned).sign(sa.private_key, 'base64url');
  const jwt = `${unsigned}.${sig}`;

  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt
    })
  });
  const j = await res.json();
  if (!j.access_token) throw new Error('認証に失敗しました: ' + JSON.stringify(j));
  return j.access_token;
}

/* 1件送る。data だけを送り、通知の表示は端末側の firebase-messaging-sw.js に任せる
   （通知が二重に出るのを防ぐため） */
async function sendOne(accessToken, token, title, body) {
  const res = await fetch(
    `https://fcm.googleapis.com/v1/projects/${PROJECT_ID}/messages:send`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: {
          token,
          data: { title, body, tag: 'shukkin-notify' },
          webpush: { headers: { Urgency: 'high', TTL: '1800' } }
        }
      })
    }
  );
  const text = await res.text();
  return { ok: res.ok, status: res.status, body: text };
}

/* ---------- 本体 ---------- */
(async function main() {
  const isTest = process.argv.includes('--test');
  const now = nowJST();
  const DWJ = ['日', '月', '火', '水', '木', '金', '土'];

  console.log('=== 出勤通知バッチ ===');
  console.log('日本時間:', fmtJST(now), `(${DWJ[now.getUTCDay()]})`);
  console.log('モード  :', isTest ? 'お試し送信（時刻に関係なく1件送る）' : '通常');

  const saRaw = process.env.FIREBASE_SA;
  if (!saRaw) throw new Error('FIREBASE_SA が設定されていません');
  const sa = JSON.parse(saRaw);

  const data = loadShiftData();
  const targets = JSON.parse(fs.readFileSync(path.join(ROOT, 'notify-targets.json'), 'utf8')).targets;
  console.log('登録数  :', targets.length, '件\n');

  const accessToken = await getAccessToken(sa);
  let sent = 0;

  for (const t of targets) {
    const plan = nextPlan(t, data, now);
    if (!plan) { console.log(`- ${t.label}: 予定なし`); continue; }

    const p = (n) => String(n).padStart(2, '0');
    const planStr = `${plan.date.getUTCMonth() + 1}/${plan.date.getUTCDate()}`
      + `(${DWJ[plan.date.getUTCDay()]}) ${plan.dial}番 出勤${plan.startText}`
      + ` → 通知 ${p(plan.notify.getUTCHours())}:${p(plan.notify.getUTCMinutes())}`;

    // 送るかどうかの判定。予定時刻を過ぎてから15分以内なら送る
    const diffMin = (now.getTime() - plan.notify.getTime()) / 60000;
    const shouldSend = isTest || (diffMin >= 0 && diffMin < 15);

    if (!shouldSend) {
      console.log(`- ${t.label}: ${planStr}（まだ送らない / 差 ${diffMin.toFixed(1)}分）`);
      continue;
    }

    const leadText = t.lead === 120 ? '2時間' : (t.lead === 60 ? '1時間' : `${t.lead}分`);
    const title = '🚌 まもなく出勤です';
    let body = `${plan.date.getUTCMonth() + 1}/${plan.date.getUTCDate()}`
      + `(${DWJ[plan.date.getUTCDay()]}) ${plan.dial}番ダイヤ\n`
      + `出勤 ${plan.startText}（あと${leadText}）`;

    // 条件によって出勤時刻が変わる番号は、その旨を添える
    const alts = altStarts(plan.startText, plan.note);
    if (alts.length) body += `\n※条件により ${alts.join('／')} の場合あり`;

    const r = await sendOne(accessToken, t.token, title, body);
    if (r.ok) {
      console.log(`✅ ${t.label}: 送信しました  ${planStr}`);
      sent++;
    } else {
      console.log(`❌ ${t.label}: 送信できませんでした (${r.status})`);
      console.log('   ', r.body.slice(0, 300));
      // トークンが無効な場合は、後で登録から消す必要がある
      if (r.status === 404 || r.status === 400) {
        console.log('    → この宛先はもう使えない可能性があります');
      }
    }
  }

  console.log(`\n送信件数: ${sent} 件`);
})().catch((e) => {
  console.error('エラー:', e.message);
  process.exit(1);
});
