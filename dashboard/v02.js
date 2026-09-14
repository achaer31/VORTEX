'use strict';
const byId = id => document.getElementById(id);
const finite = value => typeof value === 'number' && Number.isFinite(value);
const usd = value => finite(value) ? new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value) : '—';
const num = (value,digits=2) => finite(value) ? new Intl.NumberFormat('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value) : '—';
const pct = value => finite(value) ? num(value*100,2)+'%' : '—';
const text = (id,value) => {byId(id).textContent=value??'—';};
const utc = value => {const time=Date.parse(value);return Number.isFinite(time)?new Date(time).toISOString().replace('T',' · ').slice(0,22)+' UTC':'—';};
const human = value => typeof value==='string'?value.replaceAll('_',' '):'Tidak tersedia';
const MODULES = [
  ['orion','ORION','Trend multi-timeframe',20,'#287f80'],['vortex','VORTEX','Momentum RSI / MACD / ROC3',15,'#34759d'],
  ['nova','NOVA','Struktur / breakout / retest',20,'#796396'],['luna','LUNA','Sweep / rejection wick',20,'#a46088'],
  ['kira','KIRA','Kualitas volatilitas',10,'#a18538'],['atlas','ATLAS','Macro / news / session',15,'#7a8546']
];
let report=null, environment='BACKTEST', envelope=null, endpoint='', reader='', requestError='', pollTimer=null, inFlight=null;
let filters={period:'',allocation:'',risk:'',cost:''};

function cell(tag,value,className){const element=document.createElement(tag);element.textContent=value??'—';if(className)element.className=className;return element;}
function scenario(){return report?.scenarios.find(s=>Object.entries(filters).every(([key,value])=>String(s[key])===value));}
function makeOption(select,value,label){const option=cell('option',label);option.value=String(value);select.append(option);}
function initializeFilters(){
  const first=report.scenarios.find(s=>s.period==='full_descriptive'&&!String(s.allocation).includes('NONDEPLOYABLE'))||report.scenarios[0];
  for(const key of Object.keys(filters)){
    const select=byId('v02-'+key);select.replaceChildren();
    const values=[...new Set(report.scenarios.map(s=>String(s[key])))];
    values.forEach(value=>makeOption(select,value,key==='risk'?pct(Number(value)):human(value)));
    filters[key]=String(first[key]);select.value=filters[key];
    select.addEventListener('change',()=>{
      filters[key]=select.value;
      // Some profiles have one frozen risk. Preserve the chosen control and
      // select a real existing scenario, never synthesize a cross-product.
      let selected=report.scenarios.find(s=>Object.entries(filters).every(([k,v])=>String(s[k])===v));
      if(!selected)selected=report.scenarios.find(s=>String(s[key])===filters[key]&&s.period===filters.period&&s.cost===filters.cost)
        ||report.scenarios.find(s=>String(s[key])===filters[key])||first;
      for(const k of Object.keys(filters)){filters[k]=String(selected[k]);byId('v02-'+k).value=filters[k];}
      render();
    });
  }
}

function liveState(){
  if(requestError)return {valid:false,label:'DISCONNECTED',reason:requestError};
  if(!envelope)return {valid:false,label:'DISCONNECTED',reason:'Belum ada endpoint terhubung untuk '+environment+'.'};
  const snapshot=envelope.snapshot;
  if(envelope.state!=='fresh'||!snapshot)return {valid:false,label:envelope.state==='empty'?'EMPTY':'STALE',reason:'Snapshot cloud belum tersedia atau sudah kedaluwarsa.'};
  if(typeof snapshot!=='object'||!Array.isArray(snapshot.positions)||snapshot.account?.currency!=='USD'||snapshot.quote?.symbol!=='XAUUSD'||
     !finite(snapshot.account?.balance)||!finite(snapshot.account?.equity)||!finite(snapshot.quote?.bid)||
     !finite(snapshot.quote?.ask)||snapshot.quote.bid<=0||snapshot.quote.ask<snapshot.quote.bid)
    return {valid:false,label:'DISCONNECTED',reason:'Schema atau quote snapshot tidak valid.'};
  const now=Date.now(),produced=Date.parse(snapshot.producedAt),quoteTime=Date.parse(snapshot.quote?.changedAtUtc);
  if(!Number.isFinite(produced)||now-produced>90000||produced-now>30000||envelope.ageSeconds>90)
    return {valid:false,label:'STALE',reason:'Umur snapshot melewati batas 90 detik.'};
  if(!Number.isFinite(quoteTime)||now-quoteTime>10000||quoteTime-now>2000)
    return {valid:false,label:'STALE',reason:'Quote tidak segar dalam 10 detik terakhir.'};
  if(snapshot.mode!=='demo'||snapshot.status?.demoVerified!==true||snapshot.status?.terminalConnected!==true)
    return {valid:false,label:'DISCONNECTED',reason:'Identitas DEMO atau koneksi terminal belum terverifikasi.'};
  if(!snapshot.v02){
    if(environment==='PAPER')return {valid:false,label:'LEGACY',reason:'Snapshot observer lama bukan session PAPER v0.2.'};
    return {valid:true,legacy:true,label:'LEGACY OBSERVER',reason:'Quote akun DEMO segar; strategi observer v0.1. Skor v0.2 tidak tersedia.',snapshot};
  }
  if(snapshot.v02.model!=='VORTEX-XAU-EXTREME-v0.2'||snapshot.v02.environment!==environment)
    return {valid:false,label:'DISCONNECTED',reason:'Versi atau lingkungan snapshot tidak cocok dengan tab ini.'};
  if(!snapshot.v02.metrics||!snapshot.v02.engines||!Array.isArray(snapshot.v02.journal)||
     !['NORMAL','AGGRESSIVE','EXTREME','FROZEN','KILL'].includes(snapshot.v02.mode)||
     !['LONG','SHORT','WAIT'].includes(snapshot.v02.action))
    return {valid:false,label:'DISCONNECTED',reason:'Schema v0.2 belum lengkap.'};
  if(snapshot.v02.protection?.dataFresh!==true||snapshot.v02.protection?.brokerConnected!==true)
    return {valid:false,label:'STALE',reason:'Producer menyatakan data atau koneksi belum siap.'};
  return {valid:true,legacy:false,label:environment+' · FRESH',reason:'Snapshot baca-saja terautentikasi. Tidak ada kontrol eksekusi.',snapshot,v02:snapshot.v02};
}

function backtestView(){
  const s=scenario(),signal=report?.signal||{},d=report?.diagnostics||{},market=report?.market||{};
  const noTrades=s?.n_trades===0;
  const engines={};
  const direction=finite(signal.consensus)?Math.sign(signal.consensus):0;
  const thresholds={orion:70,vortex:55,nova:75,luna:55,atlas:-35};
  for(const [key] of MODULES){
    const score=signal[key];let status='INVALID';
    if(finite(score))status=key==='kira'?(score>=45&&score<85?'PASS':'FAIL'):
      direction?(score*direction>=thresholds[key]?'PASS':'FAIL'):'WAIT';
    engines[key]={score,status,reason:signal[key+'_reason']||'data_tidak_tersedia'};
  }
  const journals=[];
  if(d.missing_news_bars)journals.push({time:report.sourceAsOf,event:'INVALID',reason:`${d.missing_news_bars.toLocaleString('id-ID')} bar tanpa calendar point-in-time lengkap.`});
  if(d.missing_macro_bars)journals.push({time:report.sourceAsOf,event:'INVALID',reason:`${d.missing_macro_bars.toLocaleString('id-ID')} bar tanpa macro yang terverifikasi.`});
  for(const reason of report.promotion?.reasons||[])journals.push({time:report.sourceAsOf,event:'NO-GO',reason:human(reason)});
  return {historical:true,valid:!!s,label:report.promotion?.status||'NOT_EVALUABLE',
    reason:'Hasil penelitian tersimpan. '+(noTrades?'Tidak ada transaksi; P/L strategi belum dapat dievaluasi.':'Baca batas data dan biaya pada laporan.'),
    time:report.sourceAsOf,version:report.model,mode:signal.mode||'FROZEN',action:signal.signal===1?'LONG':signal.signal===-1?'SHORT':'WAIT',
    consensus:signal.consensus,engines,context:{session:signal.session,atr:signal.atr,nextNews:signal.next_news||null},
    quote:finite(market.bid)?{bid:market.bid,spreadPoints:market.spreadPoints,changedAtUtc:market.time||report.sourceAsOf}:null,
    metrics:{balance:s?.final_equity,equity:s?.final_equity,floatingPnl:noTrades?0:null,realizedPnl:s?.net_profit,
      dailyPnl:null,maxDrawdown:s?.max_close_sampled_drawdown,dailyDrawdown:null,freeMargin:null,usedMargin:null,
      openRisk:noTrades?0:null,lockedProfit:noTrades?0:null,currentR:null},
    starting:s?.starting_cash,protection:{confirmed:null,killSwitch:false,latencyMs:null,brokerConnected:false,dataFresh:false},
    journal:journals,positions:[],position:null,campaigns:s?.n_campaigns,adds:s?.n_adds,execution:signal.execution_valid};
}

function liveView(){
  const state=liveState();
  if(!state.valid)return {valid:false,label:state.label,reason:state.reason,mode:'FROZEN',action:'WAIT',metrics:{},engines:{},context:{},protection:{},positions:[],journal:[]};
  const snapshot=state.snapshot,v=state.v02,account=snapshot.account||{};
  return {valid:true,legacy:state.legacy,label:state.label,reason:state.reason,time:snapshot.producedAt,
    version:state.legacy?'LEGACY '+(snapshot.strategy?.version||'observer'):v.model,
    mode:v?.mode||'FROZEN',action:v?.action||'WAIT',consensus:v?.consensus,
    metrics:v?.metrics||{balance:account.balance,equity:account.equity,freeMargin:account.freeMargin,usedMargin:account.margin},
    engines:v?.engines||{},context:v?.context||{},quote:snapshot.quote,
    protection:v?.protection||{brokerConnected:true,dataFresh:true,confirmed:null,killSwitch:false},
    position:v?.position,positions:snapshot.positions||[],journal:v?.journal||[],runnerMode:snapshot.strategy?.runnerMode};
}

function renderHealth(view){
  const m=view.metrics,p=view.protection||{};
  const data=[['FREE MARGIN',usd(m.freeMargin)],['USED MARGIN',usd(m.usedMargin)],['OPEN RISK',usd(m.openRisk)],
    ['LOCKED PROFIT',usd(m.lockedProfit)],['CURRENT R',finite(m.currentR)?num(m.currentR)+'R':'—'],
    ['PROTECTION',typeof p.confirmed==='boolean'?(p.confirmed?'CONFIRMED':'NOT CONFIRMED'):'—'],
    ['LATENCY',finite(p.latencyMs)?num(p.latencyMs,0)+' ms':'—'],
    ['BROKER',view.historical?'OFFLINE TEST':view.valid?'CONNECTED':'DISCONNECTED'],
    ['KILL SWITCH',p.killSwitch===true?(view.runnerMode==='observe'?'ENTRY TERKUNCI / OBSERVER':'ACTIVE'):view.historical?'TIDAK DIAKTIFKAN':view.valid?'INACTIVE':'—']];
  const grid=byId('health-grid');grid.replaceChildren();
  for(const [label,value]of data){const box=document.createElement('div');box.className='health-item';box.append(cell('small',label),cell('strong',value));grid.append(box);}
  text('health-note',view.historical?'Biaya dan eksekusi berupa asumsi historis; latensi broker tidak diisi nol.':'Koneksi segar tidak sama dengan izin trading atau perlindungan yang terkonfirmasi.');
}

function renderEngines(view){
  const root=byId('v02-engine-grid');root.replaceChildren();
  MODULES.forEach(([key,name,role,weight,color],i)=>{
    const module=view.engines[key]||{score:null,status:'INVALID',reason:view.legacy?'observer_legacy_bukan_engine_v02':'data_belum_tersedia'};
    const card=document.createElement('article');card.className='v02-engine';card.style.setProperty('--engine-color',color);
    const header=document.createElement('header');header.append(cell('span',`M0${i+1} / ${weight}%`),cell('span',module.status,'engine-state '+String(module.status).toLowerCase()));
    const score=finite(module.score)?(module.score>0&&key!=='kira'?'+':'')+num(module.score,1):'—';
    card.append(header,cell('h3',name),cell('small',role),cell('strong',score),cell('small',key==='kira'?'QUALITY / 100':'DIRECTION / ±100'),cell('p',human(module.reason)));root.append(card);
  });
  text('v02-engine-time',(view.historical?'Snapshot historis · ':view.legacy?'v0.2 tidak tersedia · ':'Snapshot · ')+utc(view.time));
}

function renderPositions(view){
  const p=view.position||{},metrics=view.metrics,root=byId('position-summary');root.replaceChildren();
  for(const [label,value]of [['AVG ENTRY',num(p.averageEntry,3)],['TP1 / TP2',num(p.tp1,3)+' / '+num(p.tp2,3)],['RUNNER LOT',num(p.runnerLots,2)],['PYRAMID',finite(p.pyramidCount)?String(p.pyramidCount):'—']]){
    const box=document.createElement('div');box.append(cell('small',label),cell('strong',value));root.append(box);
  }
  const body=byId('positions-body');body.replaceChildren();
  for(const position of view.positions){const row=document.createElement('tr');[human(position.side),num(position.lots),num(position.openPrice,3),num(position.stopLoss,3),num(position.takeProfit,3),usd(position.profit)].forEach(value=>row.append(cell('td',value)));body.append(row);}
  if(!view.positions.length){const row=document.createElement('tr'),empty=cell('td',view.historical?'Tidak ada posisi broker pada tampilan backtest. Campaign: '+(view.campaigns??'—')+'.':view.valid?'Tidak ada posisi XAUUSD pada snapshot ini.':'Posisi tidak tersedia — belum ada koneksi terverifikasi.','empty');empty.colSpan=6;row.append(empty);body.append(row);}
  text('position-count',view.historical?'BACKTEST':view.valid?view.positions.length+' POSISI':'UNAVAILABLE');
}

function renderJournal(view){
  const root=byId('v02-journal');root.replaceChildren();
  const entries=view.journal.length?view.journal:[{time:view.time,event:'WAIT',reason:view.valid?'Tidak ada event v0.2 yang tersedia pada snapshot ini.':'Belum terhubung ke sumber data v0.2.'}];
  entries.slice(-12).forEach(event=>{const row=document.createElement('div');row.className='v02-event';row.append(cell('time',utc(event.time)),cell('b',event.event),cell('p',event.reason));root.append(row);});
  text('journal-source',view.historical?'DIAGNOSTIK LAPORAN':view.valid?'SNAPSHOT':'DISCONNECTED');
}

function renderTable(){
  if(!report)return;
  const rows=report.scenarios.filter(s=>s.period===filters.period),body=byId('v02-scenario-rows');body.replaceChildren();
  const current=scenario();
  rows.forEach(s=>{const tr=document.createElement('tr');if(s.id===current?.id)tr.className='v02-selected-row';
    [human(s.period),human(s.allocation),pct(s.risk),human(s.cost),usd(s.final_equity),usd(s.net_profit),String(s.n_campaigns??'—'),pct(s.max_close_sampled_drawdown)].forEach(value=>tr.append(cell('td',value)));
    tr.tabIndex=0;tr.setAttribute('aria-label','Pilih '+human(s.allocation)+' '+pct(s.risk)+' '+human(s.cost));
    const choose=()=>{for(const key of Object.keys(filters)){filters[key]=String(s[key]);byId('v02-'+key).value=filters[key];}render();};
    tr.addEventListener('click',choose);tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});body.append(tr);
  });
  text('scenario-count',report.scenarios.length+' SKENARIO TERSIMPAN');text('v02-table-count',rows.length+' / '+report.scenarios.length+' SKENARIO');
}

function render(){
  const historical=environment==='BACKTEST';
  const unavailable={valid:false,label:'BACKTEST BELUM TERSEDIA',reason:'Laporan v0.2 belum dapat dibaca.',metrics:{},engines:{},context:{},protection:{},positions:[],journal:[],mode:'FROZEN',action:'WAIT'};
  const view=historical?(report?backtestView():unavailable):liveView();
  byId('scenario-controls').hidden=!historical;byId('v02-register').hidden=!historical;
  document.querySelectorAll('[data-env]').forEach(b=>{const active=b.dataset.env===environment;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});
  text('health-badge',view.label);byId('health-badge').className='badge '+(historical?'stale':view.valid&&!view.legacy?'live':view.label==='STALE'?'stale':'offline');
  text('source-time',utc(view.time));text('version-note',view.version||'v0.2 · tidak tersedia');text('status-reason',view.reason);
  byId('status-banner').firstElementChild.textContent=view.valid?view.action:'WAIT';
  const m=view.metrics;
  for(const [id,key]of [['m-balance','balance'],['m-equity','equity'],['m-floating','floatingPnl'],['m-realized','realizedPnl'],['m-daily','dailyPnl']])text(id,usd(m[key]));
  text('m-dd',pct(m.maxDrawdown));text('m-daily-dd',pct(m.dailyDrawdown));text('m-initial',usd(view.starting));text('balance-basis',historical?'SIMULASI':environment);
  text('quote-bid',num(view.quote?.bid,3));text('quote-basis',historical?'BID BAR HISTORIS':view.valid?'BID SNAPSHOT':'BID / UNAVAILABLE');
  text('quote-ask',num(view.quote?.ask,3));text('quote-spread',finite(view.quote?.ask)&&finite(view.quote?.bid)?num(view.quote.ask-view.quote.bid,3)+' USD':finite(view.quote?.spreadPoints)?view.quote.spreadPoints+' points / bar':'Spread tidak tersedia');
  text('quote-time',utc(view.quote?.changedAtUtc));text('context-session',human(view.context.session));text('context-atr','ATR '+num(view.context.atr,3));text('context-news',view.context.nextNews||'Data news belum tersedia');
  text('v02-consensus',finite(view.consensus)?(view.consensus>0?'+':'')+num(view.consensus,1):'—');text('v02-mode',view.mode);text('v02-action',view.valid?view.action:'WAIT');text('decision-source',historical?'HISTORIS':view.legacy?'LEGACY':environment);
  text('decision-note',historical?'Skor pada akhir dataset; filter memilih hasil skenario. KIRA adalah kualitas, bukan suara bullish.':view.legacy?'Snapshot lama dapat menyediakan quote akun DEMO; skor dan keputusan v0.2 tetap tidak tersedia.':'Lima modul memberi arah; KIRA menilai kualitas. Izin eksekusi tidak dikendalikan halaman ini.');
  renderHealth(view);renderEngines(view);renderPositions(view);renderJournal(view);if(historical)renderTable();
}

async function poll(){
  if(!endpoint||!reader)return;
  if(inFlight)inFlight.abort();
  const controller=new AbortController();inFlight=controller;
  const timeout=setTimeout(()=>controller.abort(),8000);
  try{
    const response=await fetch(endpoint,{method:'GET',headers:{Authorization:'Bearer '+reader,Accept:'application/json'},cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',redirect:'error',signal:controller.signal});
    if(!response.ok)throw new Error('read_failed');
    const next=await response.json();
    if(next.schemaVersion!==1||next.mode!=='demo'||!['fresh','stale','empty'].includes(next.state))throw new Error('schema_mismatch');
    if(inFlight!==controller)return;
    envelope=next;requestError='';text('connection-message','Endpoint terhubung. Poll setiap 15 detik; quote lebih tua dari 10 detik ditandai STALE.');
  }catch(error){
    if(inFlight!==controller)return;
    requestError='Snapshot tidak dapat diverifikasi. Periksa endpoint, reader token, jaringan, atau CORS.';
    envelope=null;text('connection-message',requestError);
  }finally{clearTimeout(timeout);if(inFlight===controller)inFlight=null;render();}
}

function disconnect(){
  clearInterval(pollTimer);pollTimer=null;if(inFlight){inFlight.abort();inFlight=null;}
  endpoint='';reader='';envelope=null;requestError='';byId('reader-token').value='';
  text('connection-message','Koneksi diputus; token dihapus dari memori halaman.');render();
}

byId('connection-toggle').addEventListener('click',()=>{byId('connection-panel').hidden=!byId('connection-panel').hidden;});
byId('disconnect-button').addEventListener('click',disconnect);
byId('connect-button').addEventListener('click',()=>{
  let url;try{url=new URL(byId('endpoint').value.trim());}catch{return text('connection-message','Masukkan URL endpoint HTTPS yang valid.');}
  const token=byId('reader-token').value.trim();
  if(url.protocol!=='https:'||url.username||url.password||url.hash||url.search)return text('connection-message','Gunakan endpoint HTTPS tanpa credential, query, atau fragment pada URL.');
  if(!/^[a-f0-9]{64}$/.test(token))return text('connection-message','Reader token harus 64 karakter hex huruf kecil.');
  disconnect();endpoint=url.href;reader=token;requestError='';byId('reader-token').value='';
  if(environment==='BACKTEST')environment='DEMO';poll();pollTimer=setInterval(poll,15000);
});
document.querySelectorAll('[data-env]').forEach(button=>button.addEventListener('click',()=>{environment=button.dataset.env;render();}));
window.addEventListener('pagehide',disconnect);
setInterval(()=>{if(environment!=='BACKTEST')render();},1000);
async function init(){
  try{const response=await fetch('assets/v02.json',{cache:'no-cache'});if(!response.ok)throw new Error('missing');
    const value=await response.json();if(value.schemaVersion!==2||value.model!=='VORTEX-XAU-EXTREME-v0.2'||value.environment!=='BACKTEST'||value.liveFeed!==false||!Array.isArray(value.scenarios)||!value.scenarios.length)throw new Error('invalid');
    report=value;initializeFilters();
  }catch{report=null;}
  render();
}
init();
