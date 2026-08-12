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

/* その日の勤務を取り出す。中間解放（前半・後半に分かれる勤務）にも対応する。
   返すのは出勤の一覧。公休や時刻不明のときは空。

   【データの並び】
     出退勤「6:13/9:25 〜 14:11/21:58」は
       前半 6:13 出勤 → 9:25 退勤
       後半 14:11 出勤 → 21:58 退勤
     という意味。スラッシュの前後が「出勤/退勤」の組で、
     〜の左が前半、右が後半にあたる。

   条件で時刻が変わる勤務（近大休暇中・学校休みなど）については、
   基本の欄に載っている時刻がいちばん早いので、それをそのまま使う。
   別条件の時刻は通知の本文に添えて、本人に判断してもらう。 */
function shiftEntries(dial, dateUTC, data) {
  const types = dayType(dateUTC, data);
  let rawIn = null, rawOut = null, note = '';

  if (data.kind === 'obj') {
    const rec = data.DB[dial];
    if (!rec) return [];
    let e = null;
    for (const t of types) { if (rec[t]) { e = rec[t]; break; } }
    if (!e || !e.o || e.o === '—' || !e.o.includes('〜')) return [];
    const parts = e.o.split('〜');
    rawIn = parts[0]; rawOut = parts[1] || '';
    note = e.n || '';
  } else {
    let row = null;
    for (const t of types) {
      row = data.ROWS.find((r) => r.id === dial && r.dayType === t);
      if (row) break;
    }
    if (!row) row = data.ROWS.find((r) => r.id === dial && r.dayType === '全');
    if (!row || !row.start) return [];
    rawIn = String(row.start); rawOut = String(row.end || '');
    note = row.memo || '';
  }

  const toMin = (t) => {
    const m = String(t).trim().match(/^(\d{1,2}):(\d{2})$/);
    return m ? (+m[1]) * 60 + (+m[2]) : null;
  };
  const ins  = rawIn.split('/').map((x) => x.trim());
  const outs = rawOut.split('/').map((x) => x.trim());

  const list = [];
  if (ins.length >= 2 && outs.length >= 2) {
    // 中間解放。前半＝出勤欄の2つ、後半＝退勤欄の2つ
    const a1 = toMin(ins[0]),  a2 = toMin(ins[1]);
    const b1 = toMin(outs[0]), b2 = toMin(outs[1]);
    if (a1 !== null) list.push({ startMin: a1, text: ins[0],  endMin: a2, note, part: 0 });
    if (b1 !== null) list.push({ startMin: b1, text: outs[0], endMin: b2, note, part: 1 });
  } else {
    const a1 = toMin(ins[0]);
    if (a1 !== null) list.push({ startMin: a1, text: ins[0], endMin: toMin(outs[0]), note, part: 0 });
  }
  if (!list.length) return [];

  // 【中間解放かどうかの判定】
  // 前半の退勤から後半の出勤まで4時間以上空いていれば、いったん帰る人がいる。
  // その場合だけ後半にも通知する。4時間未満なら続きの勤務なので通知は前半だけ。
  if (list.length >= 2 && list[0].endMin !== null) {
    const restMin = list[1].startMin - list[0].endMin;
    if (restMin < 240) return [list[0]];
  }
  return list;
}

/* 備考に、出勤時刻が違う条件が書かれていないか調べる。
   例: 学園前A 31番平日は 近大通常17:09 / 休暇中18:38 で1時間半ちがう。
   誤った時刻だけを知らせると遅刻につながるので、本文に添える。 */
function altStarts(baseText, note) {
  if (!note) return [];
  const found = [...String(note).matchAll(/(\d{1,2}:\d{2})〜/g)].map((m) => m[1]);
  return [...new Set(found.filter((t) => t !== baseText))];
}

/* 次に通知すべき予定を求める。今日から14日先まで探す。
   中間解放の場合は、前半と後半それぞれが対象になる。 */
function nextPlan(t, data, now) {
  for (let i = 0; i <= 14; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    d.setUTCDate(d.getUTCDate() + i);
    const dial = dialFor(d, t.baseDate, t.baseDial, data.cycle);
    const list = shiftEntries(dial, d, data);
    for (const e of list) {
      const start  = new Date(d.getTime() + e.startMin * 60000);
      const notify = new Date(start.getTime() - t.lead * 60000);
      if (notify.getTime() + 30 * 60000 < now.getTime()) continue;   // 済んだものは飛ばす
      return {
        date: d, dial, start, notify,
        startText: e.text, note: e.note,
        part: e.part, total: list.length
      };
    }
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
        lead: f.lead && parseInt(f.lead.integerValue),
        // 最後に送った勤務の目印。同じ勤務に何度も送らないために使う
        lastSent: (f.lastSent && f.lastSent.stringValue) || ''
      };
      if (v.app && v.token && v.baseDate && v.baseDial && v.lead) out.push(v);
    }
    pageToken = j.nextPageToken || '';
    if (!pageToken) break;
  }
  return out;
}

/* 使えなくなった宛先を消す */
/* 「この勤務にはもう送った」という印を残す。
   5分おきに動くので、印がないと同じ勤務に何度も送ってしまう。
   実際、1回のはずが13回届いてしまった。 */
async function markSent(at, id, key) {
  try {
    await fetch(`${FS_ROOT}/notifyTargets/${id}?updateMask.fieldPaths=lastSent`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields: { lastSent: { stringValue: key } } })
    });
  } catch (e) { /* 記録に失敗しても送信自体は済んでいる */ }
}

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
async function sendOne(at, token, title, body, tag) {
  const res = await fetch(`https://fcm.googleapis.com/v1/projects/${PROJECT_ID}/messages:send`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        token,
        data: { title, body, tag: tag || 'shukkin-notify' },
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

    // 【送るかどうかの判定】
    // GitHub の定期実行は「5分おき」と書いても実際は25〜55分に1回しか動かない。
    // そのため予定時刻ぴったりを狙うと取りこぼす。
    // 次に動くまでに予定時刻が来てしまう人は、少し早めでも今のうちに送る。
    // 遅れて届くより、早めに届くほうが実害がないため。
    // この勤務を表す目印。日付・番号・前半後半で1つに決まる
    const sentKey = ymd(plan.date) + '-' + plan.dial + '-' + plan.part;

    // すでに送ってあれば、もう送らない
    if (!isTest && t.lastSent === sentKey) {
      console.log(`- ${who}: ${planStr}（送信済み）`);
      skipped++;
      continue;
    }

    // 予定より少し早めでも送る（次に動くまでに時刻が来てしまう人を拾うため）。
    // 遅れて届いたぶんは「あと◯分」の表示で本人が判断できる。
    const diffMin = (now.getTime() - plan.notify.getTime()) / 60000;
    const shouldSend = diffMin >= -20 && diffMin < 45;
    if (!isTest && !shouldSend) {
      console.log(`- ${who}: ${planStr}（まだ / 差${diffMin.toFixed(0)}分）`);
      skipped++;
      continue;
    }

    // 出勤まで実際にあと何分かを、送る時点で計算し直す。
    // 早めに送った場合でも、書いてある残り時間が正しくなる。
    const restMin = Math.max(0, Math.round((plan.start.getTime() - now.getTime()) / 60000));
    const restText = restMin >= 60
      ? `あと${Math.floor(restMin / 60)}時間${restMin % 60 ? (restMin % 60) + '分' : ''}`
      : `あと${restMin}分`;
    // 中間解放の勤務は、前半・後半のどちらかが分かるようにする
    const partText = plan.total >= 2 ? (plan.part === 0 ? '【前半】' : '【後半】') : '';
    let body = `${plan.date.getUTCMonth() + 1}/${plan.date.getUTCDate()}`
      + `(${DWJ[plan.date.getUTCDay()]}) ${plan.dial}番ダイヤ${partText}\n`
      + `出勤 ${plan.startText}（${restText}）`;
    const alts = altStarts(plan.startText, plan.note);
    if (alts.length) body += `\n※条件により ${alts.join('／')} の場合あり`;

    // 同じ勤務の通知が2回送られても、端末側で1件にまとまるようにする
    const tag = 'shukkin-' + sentKey;
    const r = await sendOne(at, t.token, '🚌 まもなく出勤です', body, tag);
    if (r.ok) {
      console.log(`✅ ${who}: 送信  ${planStr}`);
      if (!isTest) await markSent(at, t.id, sentKey);   // もう送ったと記録する
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
