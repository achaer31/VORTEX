/* Historical research console. No network/broker calls beyond the local snapshot. */
'use strict';
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const count = n => new Intl.NumberFormat('id-ID').format(n);
const money = n => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',minimumFractionDigits:2}).format(n);
const price = n => new Intl.NumberFormat('en-US', {minimumFractionDigits:3,maximumFractionDigits:3}).format(n);
const signed = (n, digits=1) => `${n>0?'+':n<0?'−':''}${Math.abs(n).toFixed(digits)}`;
const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
const when = (iso,withTime=true) => `${iso.slice(8,10)} ${months[Number(iso.slice(5,7))-1]}${withTime?' · '+iso.slice(11,16):''}`;
const PERIOD_LABELS = {full:'Seluruh periode',development:'Development',validation:'Validation',holdout:'Holdout'};
const MODULES = [
  {id:'orion',name:'ORION',role:'TREND ALIGNMENT',weight:22,color:'#287f80',title:'Arah yang selaras',body:'Membaca susunan EMA 20, 50, dan 200 pada M5, M15, serta H1. Skor +100 per timeframe saat close > EMA20 > EMA50 > EMA200; −100 untuk urutan sebaliknya; selain itu 0.',formula:'ORION = rata-rata alignment M5, M15, H1'},
  {id:'vortex',name:'VORTEX',role:'MOMENTUM',weight:18,color:'#34759d',title:'Kecepatan perubahan',body:'Menggabungkan RSI14 dan ROC12 yang dinormalisasi terhadap ATR. Seluruh indikator modul ini berasal dari M5. RSI menggunakan rekursi Wilder dengan seed rata-rata 14 perubahan pertama.',formula:'rata-rata clip((RSI − 50) × 4), clip(ROC12 / (ATR / close × 100) × 50)'},
  {id:'nova',name:'NOVA',role:'PRICE STRUCTURE',weight:20,color:'#796396',title:'Posisi terhadap rentang',body:'Membandingkan close dengan high dan low 20 bar sebelumnya, tanpa memasukkan bar saat ini. Breakout atas memberi +100 dan breakout bawah −100. Di dalam rentang, skor mengikuti jarak dari titik tengah.',formula:'clip((close − titik tengah rentang) / (lebar rentang / 2) × 100)'},
  {id:'luna',name:'LUNA',role:'QUOTE ACTIVITY',weight:15,color:'#a46088',title:'Body candle & aktivitas quote',body:'Body candle dibagi ATR, lalu ditimbang oleh tick volume relatif terhadap rata-rata 20 bar sebelumnya. Ini proxy aktivitas quote; tidak mengukur taker-buy atau volume transaksi beli/jual.',formula:'clip((close − open) / ATR × 100) × min(tick volume / rata-rata sebelumnya, 1)'},
  {id:'kira',name:'KIRA',role:'VOLATILITY',weight:10,color:'#a18538',title:'Konteks volatilitas',body:'Memberi arah +100 atau −100 sesuai posisi close terhadap EMA20 ketika ATR/close berada antara 0,0003 dan 0,005. Di luar rentang, skor 0. Batas ini asumsi riset, bukan parameter yang sudah terbukti optimal.',formula:'sign(close − EMA20) × 100 jika 0,0003 ≤ ATR/close ≤ 0,005'},
  {id:'atlas',name:'ATLAS',role:'HIGHER TIMEFRAME',weight:15,color:'#7a8546',title:'Konteks yang sudah selesai',body:'Mengambil rata-rata alignment M15 dan H1 yang sudah closed pada waktu keputusan M5. Data digabung berdasarkan waktu tutup HTF sehingga bar masa depan tidak ikut dipakai. ATLAS adalah konteks, bukan pengendali risiko.',formula:'ATLAS = rata-rata alignment M15 dan H1'}
];
let data;
let state = {period:'full',risk:.03,cost:'baseline',timeframe:'M5',chartCount:100};
let visibleBars = [], hoverIndex = null;
const svg = (tag,attrs={},text='') => {
  const node=document.createElementNS(NS,tag);
  for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value));
  if(text) node.textContent=text;
  return node;
};
function selectedScenario(){return data.scenarios.find(s=>s.period===state.period&&s.risk===state.risk&&s.cost===state.cost);}

function drawVortex(){
  const root=$('vortex-svg'); root.replaceChildren();
  const g=svg('g'); root.append(g);
  g.append(svg('line',{x1:260,y1:36,x2:260,y2:324,stroke:'#c7d3cc','stroke-dasharray':'2 5','stroke-width':.6}));
  for(let i=0;i<6;i++){
    const ry=19+i*6,rx=99+i*18;
    g.append(svg('ellipse',{cx:260,cy:220,rx,ry,fill:'none',stroke:'#a6c4bc','stroke-width':.6,opacity:.55,transform:`rotate(${i%2?8:-8} 260 220)`}));
  }
  for(let strand=0;strand<11;strand++){
    let path='';
    for(let j=0;j<=260;j++){
      const t=j/260;
      const radius=13+68*Math.pow(Math.sin(Math.PI*t),.8);
      const a=t*Math.PI*13+strand*Math.PI*2/11;
      const x=260+Math.cos(a)*radius+(t-.5)*22;
      const y=70+t*218+Math.sin(a)*radius*.31;
      path+=`${j?'L':'M'}${x.toFixed(2)} ${y.toFixed(2)} `;
    }
    g.append(svg('path',{d:path,fill:'none',stroke:strand%3?'#287d99':'#1d8b85','stroke-width':strand%3?1.25:1.6,opacity:.28+strand*.035}));
  }
  for(let i=0;i<24;i++){
    const t=i/23,rx=13+68*Math.pow(Math.sin(Math.PI*t),.8);
    g.append(svg('ellipse',{cx:260+(t-.5)*22,cy:70+t*218,rx,ry:rx*.31,fill:'none',stroke:i%2?'#3186a1':'#178e83','stroke-width':.7,opacity:.38}));
  }
  g.append(svg('ellipse',{cx:260,cy:199,rx:176,ry:43,fill:'none',stroke:'#83aaa0','stroke-width':.8,class:'orbital-dash',transform:'rotate(-12 260 199)'}));
  const satellite=[{x:93,y:224},{x:427,y:166},{x:325,y:244}];
  satellite.forEach(p=>{g.append(svg('circle',{cx:p.x,cy:p.y,r:3,fill:'#6da69b'}));g.append(svg('circle',{cx:p.x,cy:p.y,r:6,fill:'none',stroke:'#a9c8bb','stroke-width':.6}));});
  g.append(svg('path',{d:'M178 126 L132 103 L103 103 M343 239 L386 257 L412 257',fill:'none',stroke:'#c1cec5','stroke-width':.7}));
  g.append(svg('text',{x:102,y:97,fill:'#92a29c','font-size':7,'font-family':'monospace'},'FIELD / 06'));
  g.append(svg('text',{x:387,y:270,fill:'#92a29c','font-size':7,'font-family':'monospace'},'AXIS / XAU'));
}

function drawCandles(){
  const root=$('candle-svg'); root.replaceChildren();
  visibleBars=data.candles[state.timeframe].slice(-state.chartCount);
  $('chart-empty').hidden=visibleBars.length>0;
  if(!visibleBars.length)return;
  const W=760,L=17,R=69,T=18,B=245,VY=264,VH=23;
  const low=Math.min(...visibleBars.map(b=>b.l)),high=Math.max(...visibleBars.map(b=>b.h));
  const pad=(high-low)*.1||1,min=low-pad,max=high+pad;
  const width=W-L-R,step=width/visibleBars.length;
  const x=i=>L+(i+.5)*step,y=v=>T+(max-v)/(max-min)*(B-T);
  for(let i=0;i<=4;i++){
    const value=max-(max-min)*i/4,yy=y(value);
    root.append(svg('line',{x1:L,y1:yy,x2:W-R+2,y2:yy,stroke:'#d7dfd4','stroke-width':.7,'stroke-dasharray':'2 4'}));
    root.append(svg('text',{x:W-R+11,y:yy+3},price(value)));
  }
  const maxV=Math.max(...visibleBars.map(b=>b.v),1);
  visibleBars.forEach((bar,i)=>{
    const xx=x(i),up=bar.c>=bar.o,color=up?'#318f80':'#b57578';
    root.append(svg('line',{x1:xx,y1:y(bar.h),x2:xx,y2:y(bar.l),stroke:color,'stroke-width':.85}));
    root.append(svg('rect',{x:xx-Math.max(.8,step*.57)/2,y:Math.min(y(bar.o),y(bar.c)),width:Math.max(.8,step*.57),height:Math.max(.9,Math.abs(y(bar.o)-y(bar.c))),fill:color,opacity:.9}));
    const vheight=bar.v/maxV*VH;
    root.append(svg('rect',{x:xx-step*.3,y:VY+VH-vheight,width:Math.max(.7,step*.6),height:vheight,fill:up?'#b4d3c4':'#d9c1bf',opacity:.7}));
  });
  for(let i=0;i<4;i++){
    const index=Math.round(i*(visibleBars.length-1)/3);
    root.append(svg('text',{x:x(index),y:307,'text-anchor':i===0?'start':i===3?'end':'middle'},when(visibleBars[index].t)));
  }
  const last=visibleBars.at(-1),lastY=y(last.c);
  root.append(svg('line',{x1:L,y1:lastY,x2:W-R+3,y2:lastY,stroke:'#549988','stroke-width':.8,'stroke-dasharray':'3 4',opacity:.65}));
  root.append(svg('rect',{x:W-R+3,y:lastY-8,width:63,height:17,rx:1,fill:'#428c7b'}));
  const lastLabel=svg('text',{x:W-R+35,y:lastY+4,'text-anchor':'middle',style:'fill:#fff;font-size:10px'},price(last.c));root.append(lastLabel);
  const hover=svg('g',{id:'chart-hover',visibility:'hidden'});
  hover.append(svg('line',{id:'crosshair-v',x1:0,y1:T,x2:0,y2:VY+VH,stroke:'#658c8a','stroke-width':.8,'stroke-dasharray':'3 3'}));
  hover.append(svg('circle',{id:'crosshair-dot',r:3,fill:'#fbfbf6',stroke:'#356f83','stroke-width':1.2}));
  root.append(hover);
  root.dataset.left=L;root.dataset.step=step;root.dataset.top=T;root.dataset.bottom=B;root.dataset.min=min;root.dataset.max=max;
  $('last-price').textContent=price(last.c);
  const change=(last.c-visibleBars[0].o)/visibleBars[0].o*100;
  $('price-change').textContent=`${signed(change,2)}% / jendela`;
  $('price-change').className=change>=0?'positive':'negative';
  $('chart-period').textContent=`${when(visibleBars[0].t,false)} — ${when(last.t,false)} · ${state.timeframe}`;
  $('range-button').textContent=`${state.chartCount} BAR`;
  hoverIndex=null;showBar(visibleBars.length-1,false);
  document.querySelectorAll('[data-timeframe]').forEach(button=>{const active=button.dataset.timeframe===state.timeframe;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});
}

function showBar(index,crosshair=true){
  const bar=visibleBars[Math.max(0,Math.min(visibleBars.length-1,index))];if(!bar)return;
  $('ohlc-bar').replaceChildren();
  const time=document.createElement('time');time.textContent=when(bar.t);time.dateTime=bar.t;$('ohlc-bar').append(time);
  for(const [label,key]of [['O','o'],['H','h'],['L','l'],['C','c']]){
    const span=document.createElement('span');span.textContent=`${label} `;const b=document.createElement('b');b.textContent=price(bar[key]);span.append(b);$('ohlc-bar').append(span);
  }
  const root=$('candle-svg'),hover=$('chart-hover');if(!hover)return;
  hover.setAttribute('visibility',crosshair?'visible':'hidden');
  if(crosshair){
    hoverIndex=index;const d=root.dataset,x=Number(d.left)+(index+.5)*Number(d.step),y=Number(d.top)+(Number(d.max)-bar.c)/(Number(d.max)-Number(d.min))*(Number(d.bottom)-Number(d.top));
    $('crosshair-v').setAttribute('x1',x);$('crosshair-v').setAttribute('x2',x);
    $('crosshair-dot').setAttribute('cx',x);$('crosshair-dot').setAttribute('cy',y);
  }
}

function drawEquity(scenario){
  const root=$('equity-svg');root.replaceChildren();
  const points=scenario.equity;if(!points.length)return;
  const values=points.map(p=>p.value),lo=Math.min(...values),hi=Math.max(...values),pad=Math.max(1,(hi-lo)*.3),min=lo-pad,max=hi+pad;
  const x=i=>18+i/(points.length-1||1)*407,y=v=>14+(max-v)/(max-min)*72;
  [30,60,90].forEach(yy=>root.append(svg('line',{x1:18,y1:yy,x2:425,y2:yy,stroke:'#d9dfd5','stroke-width':.7,'stroke-dasharray':'2 5'})));
  const line=points.map((p,i)=>`${i?'L':'M'}${x(i)} ${y(p.value)}`).join(' ');
  root.append(svg('path',{d:`${line} L425 91 L18 91 Z`,fill:'#cededb',opacity:.3}));
  root.append(svg('path',{d:line,fill:'none',stroke:'#447e99','stroke-width':1.6}));
  root.append(svg('circle',{cx:x(points.length-1),cy:y(points.at(-1).value),r:2.7,fill:'#447e99'}));
  root.append(svg('text',{x:18,y:111,fill:'#87958e','font-family':'monospace','font-size':10},when(points[0].t,false)));
  root.append(svg('text',{x:425,y:111,'text-anchor':'end',fill:'#87958e','font-family':'monospace','font-size':10},when(points.at(-1).t,false)));
}

function renderScenario(){
  const s=selectedScenario(),p=data.dataset.periods[state.period],diagnosis=data.diagnosis[state.cost];
  $('metric-equity').textContent=money(s.finalEquity);$('metric-start').textContent=money(s.startingEquity);
  $('metric-pnl').textContent=money(s.netPnl);$('metric-pnl-note').textContent=s.trades===0?'Belum ada transaksi dalam model':`${count(s.trades)} transaksi dalam model`;
  $('metric-trades').textContent=String(s.trades).padStart(2,'0');$('metric-rejected').textContent=count(s.rejected);
  $('metric-bars').textContent=count(p.bars);$('metric-range').textContent=`${when(p.first,false)} — ${when(p.last,false)} 2026 · M5`;
  $('result-message').textContent=`${count(s.rejected)} kandidat tidak muat dalam budget ${money(s.budget)} per entry pada skenario ini.`;
  $('equity-trace-value').textContent=money(s.finalEquity);$('equity-trace-change').textContent=`${PERIOD_LABELS[state.period]} / ${state.cost}`;
  $('risk-budget').textContent=money(s.budget);$('risk-needed').textContent=money(diagnosis.minimumRisk);
  $('risk-track-fill').style.width=`${Math.min(100,s.budget/diagnosis.minimumRisk*100)}%`;
  $('journal-count').textContent=`${count(s.rejected)} REJECTIONS`;
  const list=$('journal-list');list.replaceChildren();
  s.events.slice(-4).forEach(e=>{
    const row=document.createElement('div');row.className='journal-row';
    const time=document.createElement('time');time.dateTime=e.time;time.textContent=when(e.time);
    const badge=document.createElement('span');badge.textContent='DITOLAK';
    const reason=document.createElement('b');reason.textContent='Minimum lot';row.append(time,badge,reason);list.append(row);
  });
  drawEquity(s);
  document.querySelectorAll('[data-scenario]').forEach(button=>{const active=button.dataset.scenario===s.id;button.closest('tr').classList.toggle('active-row',active);button.textContent=active?'Terpilih':'Buka';button.setAttribute('aria-pressed',String(active));});
}

function moduleIcon(index,color){
  const root=svg('svg',{viewBox:'0 0 40 40','aria-hidden':'true'});
  for(let j=0;j<3;j++)root.append(svg('ellipse',{cx:20,cy:20,rx:12,ry:4+j*.8,fill:'none',stroke:color,'stroke-width':.85,transform:`rotate(${index*13+j*60} 20 20)`}));
  root.append(svg('circle',{cx:20,cy:20,r:2.2,fill:color}));return root;
}

function renderModules(){
  const root=$('module-grid');root.replaceChildren();
  MODULES.forEach((module,index)=>{
    const card=document.createElement('button');card.className='module-card';card.style.setProperty('--module-color',module.color);card.setAttribute('aria-label',`${module.name}, skor ${signed(data.signal.scores[module.id])}. Lihat aturan modul.`);
    const meta=document.createElement('div');meta.className='module-meta';meta.innerHTML=`<span>M0${index+1}</span><span>${module.weight}%</span>`;
    const icon=document.createElement('div');icon.className='module-icon';icon.append(moduleIcon(index,module.color));
    const name=document.createElement('h3');name.textContent=module.name;
    const role=document.createElement('p');role.className='module-role';role.textContent=module.role;
    const score=document.createElement('strong');score.className='module-score';score.textContent=signed(data.signal.scores[module.id]);
    const label=document.createElement('span');label.className='score-caption';label.textContent='SKOR / 100';
    const spark=svg('svg',{viewBox:'0 0 180 42',class:'sparkline','aria-hidden':'true'});spark.append(svg('line',{x1:0,y1:21,x2:180,y2:21,stroke:'#d6dfd0','stroke-width':.6,'stroke-dasharray':'2 3'}));
    const history=data.signal.history[module.id];const line=history.map((n,i)=>`${i?'L':'M'}${i/(history.length-1)*180} ${21-n/100*16}`).join(' ');
    spark.append(svg('path',{d:`${line} L180 42 L0 42 Z`,fill:module.color,opacity:.06}));spark.append(svg('path',{d:line,fill:'none',stroke:module.color,'stroke-width':1.25}));
    card.append(meta,icon,name,role,score,label,spark);card.addEventListener('click',()=>showModule(module));root.append(card);
  });
  $('module-time').textContent=`Snapshot ${when(data.signal.time)} 2026 · 48 bar terakhir pada jejak skor`;
}

function renderTable(){
  const root=$('scenario-rows');root.replaceChildren();
  data.scenarios.forEach(s=>{
    const tr=document.createElement('tr');
    [PERIOD_LABELS[s.period],`${s.risk*100}%`,s.cost,money(s.finalEquity),money(s.netPnl),String(s.trades),count(s.rejected)].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});
    const td=document.createElement('td'),button=document.createElement('button');button.dataset.scenario=s.id;button.textContent='Buka';button.setAttribute('aria-label',`Buka ${PERIOD_LABELS[s.period]}, risiko ${s.risk*100} persen, ${s.cost}`);button.addEventListener('click',()=>{
      state.period=s.period;state.risk=s.risk;state.cost=s.cost;$('period-select').value=s.period;$('risk-select').value=String(s.risk);$('cost-select').value=s.cost;renderScenario();$('console').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    });td.append(button);tr.append(td);root.append(tr);
  });
}

function openDialog(title,eyebrow,html){
  $('dialog-title').textContent=title;$('dialog-eyebrow').textContent=eyebrow;$('dialog-content').innerHTML=html;$('detail-dialog').showModal();
}
function showModule(module){
  openDialog(module.title,`MODUL ${module.name} / ATURAN V0.1`,
    `<div class="dialog-stats"><div><small>SKOR SNAPSHOT</small><strong>${signed(data.signal.scores[module.id])}</strong></div><div><small>BOBOT CONSENSUS</small><strong>${module.weight}%</strong></div></div><p>${module.body}</p><code>${module.formula}</code><p>clip membatasi nilai ke −100/+100. Skor bukan peluang menang; modul memakai data yang tumpang tindih.</p><a class="dialog-link" href="https://github.com/achaer31/VORTEX/blob/main/research/SIGNALS.md" target="_blank" rel="noopener noreferrer">Baca spesifikasi sinyal ↗</a>`);
}
function showDiagnosis(){
  const s=selectedScenario(),d=data.diagnosis[state.cost];
  openDialog('Budget belum muat 0,01 lot.','DIAGNOSIS / SKENARIO TERPILIH',
    `<p>Pada ${PERIOD_LABELS[state.period].toLowerCase()} dengan risiko ${s.risk*100}% dan biaya ${state.cost}, ${count(s.rejected)} kandidat ditolak karena lot hasil perhitungan berada di bawah minimum.</p><div class="dialog-stats"><div><small>BUDGET ENTRY</small><strong>${money(s.budget)}</strong></div><div><small>RISIKO 0,01 LOT TERENDAH*</small><strong>${money(d.minimumRisk)}</strong></div></div><p>*Di ${count(d.candidates)} kandidat seluruh periode. Median kebutuhannya ${money(d.medianRisk)} dan maksimum ${money(d.maximumRisk)}. Sizing memakai stop 2,2 × ATR, pembulatan tick, dan asumsi slippage.</p><code>0,01 lot × [100 × (jarak SL + 2 × slippage) + 2 × komisi]</code><p>Lot dibulatkan turun. Tidak ada transaksi berarti belum ada bukti profit/loss strategi. Hasil v0.1 dipertahankan tanpa memilih ulang parameter setelah melihat holdout.</p><a class="dialog-link" href="https://github.com/achaer31/VORTEX/blob/main/reports/v0.1/SIZING-DIAGNOSIS.md" target="_blank" rel="noopener noreferrer">Lihat diagnosis yang dapat diaudit ↗</a>`);
}
function showInfo(){
  const s=selectedScenario();
  openDialog('Sebuah snapshot penelitian.','TENTANG DATA / VORTEX-XAU-V0.1',
    `<p>Dashboard ini membaca hasil historis yang tersimpan. Equity, P/L, dan event berasal dari simulator offline; halaman ini tidak terhubung ke broker, tidak menerima harga live, dan tidak mengirim order.</p><div class="dialog-keys"><span>Data terakhir</span><strong>${when(data.meta.asOf)} 2026</strong></div><div class="dialog-keys"><span>Candle ditampilkan</span><strong>Maks. 200 / timeframe</strong></div><div class="dialog-keys"><span>Spread skenario</span><strong>Bar sebelumnya ×${s.costAssumptions.spreadMultiplier}</strong></div><div class="dialog-keys"><span>Slippage skenario</span><strong>${money(s.costAssumptions.slippage)} / ounce / sisi</strong></div><p>Clock server memiliki offset UTC/DST yang belum diverifikasi. Grafik candle dan keenam modul selalu memakai snapshot pasar terakhir; pilihan skenario mengubah hasil simulasi, budget risiko, equity, dan jurnal.</p><p>Komisi nol adalah asumsi, swap belum dimodelkan, dan Bid/Ask intrabar belum direkonstruksi. History belum tersertifikasi lengkap. Gambar pusaran adalah ilustrasi geometris; jejak skor modul memakai hasil perhitungan nyata.</p><p>Seluruh periode bertumpang tindih dengan development, validation, dan holdout. Equity tiap skenario dimulai dari US$50.</p><a class="dialog-link" href="https://github.com/achaer31/VORTEX/blob/main/reports/v0.1/REPORT.md" target="_blank" rel="noopener noreferrer">Baca metodologi & hasil lengkap ↗</a>`);
}

function bindControls(){
  $('period-select').addEventListener('change',e=>{state.period=e.target.value;renderScenario();});
  $('risk-select').addEventListener('change',e=>{state.risk=Number(e.target.value);renderScenario();});
  $('cost-select').addEventListener('change',e=>{state.cost=e.target.value;renderScenario();});
  document.querySelectorAll('[data-timeframe]').forEach(b=>b.addEventListener('click',()=>{state.timeframe=b.dataset.timeframe;drawCandles();}));
  $('range-button').addEventListener('click',()=>{state.chartCount=state.chartCount===100?200:100;drawCandles();});
  $('chart-wrap').addEventListener('pointermove',e=>{
    const bounds=$('candle-svg').getBoundingClientRect();
    /* SVG uses meet-preserving scale: subtract horizontal letterbox if needed. */
    const scale=Math.min(bounds.width/760,bounds.height/320),offset=(bounds.width-760*scale)/2;
    const x=(e.clientX-bounds.left-offset)/scale,index=Math.floor((x-17)/Number($('candle-svg').dataset.step));
    if(index>=0&&index<visibleBars.length)showBar(index,true);
  });
  $('chart-wrap').addEventListener('pointerleave',()=>{hoverIndex=null;showBar(visibleBars.length-1,false);});
  $('chart-wrap').addEventListener('keydown',e=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
    let index=hoverIndex??visibleBars.length-1;
    index=e.key==='Home'?0:e.key==='End'?visibleBars.length-1:index+(e.key==='ArrowRight'?1:-1);
    showBar(Math.max(0,Math.min(visibleBars.length-1,index)),true);
  });
  $('table-toggle').addEventListener('click',()=>{const expanded=$('table-toggle').getAttribute('aria-expanded')==='true';$('scenario-table-wrap').hidden=expanded;$('table-toggle').setAttribute('aria-expanded',String(!expanded));$('table-toggle').innerHTML=expanded?'LIHAT 32 SKENARIO ↓':'TUTUP REGISTER ↑';});
  $('diagnosis-button').addEventListener('click',showDiagnosis);$('info-button').addEventListener('click',showInfo);$('footer-info').addEventListener('click',showInfo);
  $('dialog-close').addEventListener('click',()=>$('detail-dialog').close());
  $('detail-dialog').addEventListener('click',e=>{if(e.target===$('detail-dialog')){const r=$('detail-dialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('detail-dialog').close();}});
}

async function init(){
  try{
    const response=await fetch('assets/snapshot.json',{cache:'no-cache'});if(!response.ok)throw new Error('snapshot missing');
    data=await response.json();
    if(data.schemaVersion!==1||data.scenarios.length!==32||data.meta.liveFeed!==false)throw new Error('unsupported snapshot');
    $('snapshot-time').textContent=`${when(data.meta.asOf)} 2026`;$('snapshot-time').dateTime=data.meta.asOf;
    $('consensus-value').textContent=signed(data.signal.consensus);$('atr-value').textContent=data.signal.atr.toFixed(2);
    $('signal-direction').textContent=data.signal.direction===1?'LONG CANDIDATE':data.signal.direction===-1?'SHORT CANDIDATE':'WAIT / NO SIGNAL';
    $('consensus-marker').style.left=`${(data.signal.consensus+100)/2}%`;
    $('consensus-caption').textContent=`Skor historis ${signed(data.signal.consensus)} · ${when(data.signal.time)} · threshold entry ±75`;
    drawVortex();drawCandles();renderModules();renderTable();renderScenario();bindControls();
    $('load-state').hidden=true;$('app').hidden=false;
  }catch(error){
    $('load-state').textContent='Snapshot belum dapat dibuka. Muat ulang halaman atau periksa sumber penelitian.';
    const retry=document.createElement('button');retry.textContent='Coba lagi';retry.addEventListener('click',()=>location.reload());$('load-state').append(retry);
    console.error('VORTEX: historical snapshot unavailable.');
  }
}
init();
