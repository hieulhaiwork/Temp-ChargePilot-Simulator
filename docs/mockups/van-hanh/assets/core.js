'use strict';
/* Bộ mockup vận hành — khung chung (header-tab theo RoleShell vận hành của nhánh buivanlam), điều hướng, kịch bản mẫu.
   Helper icon/esc/panel/tag/note… lấy từ ../cu-dan/assets/kit.js. Mọi số liệu là MINH HOẠ, giờ trạm GMT+7.
   Trạm theo PRD v0.2: 8 đầu nối A01–A08 × 7 kW, giới hạn 35 kW. Riêng S9 Sơ đồ bãi dùng topology hybrid của ADR-010. */
const OP_FILES={dashboard:'operator.html',map:'operator-map.html',schedule:'operator-schedule.html',approvals:'operator-approvals.html',simulation:'operator-simulation.html'};
const OP_PAGES={dashboard:['Dashboard','gauge'],map:['Sơ đồ bãi','map'],schedule:['Hàng đợi & lịch','queue'],approvals:['Duyệt lệnh','shield'],simulation:['Mô phỏng','flask']};
const OP_TITLES={dashboard:'Dashboard trạm',map:'Sơ đồ bãi',schedule:'Hàng đợi & lịch',approvals:'Duyệt lệnh',simulation:'Mô phỏng kịch bản'};
let page='dashboard',variant='',paused=false,toastTimer=null,modalReturn=null,ui={};

/* Trạng thái mỗi màn: id → nhãn. id giữ nguyên theo bảng "Trạng thái" của spec 21 §3. */
const OP_STATES={
 dashboard:{live:'Trực tiếp · bình thường',powerdrop:'Nguồn giảm còn 20 kW (AC5)',blocked:'Guard vừa chặn một lệnh (AC6)',connector:'Chi tiết đầu nối A07',chartfocus:'Biểu đồ · đang xem một mốc giờ',events:'Xem tất cả sự kiện',paused:'Tạm dừng cập nhật',stale:'Dữ liệu cũ hơn 60 giây',offline:'Mất kết nối trực tiếp',loading:'Đang tải',empty:'Trạm vừa khởi động · chưa có dữ liệu',error:'Một khối lỗi · có thể thử lại',notimpl:'Dịch vụ chưa sẵn sàng (501)'},
 map:{peak:'18:30 · Cao điểm tối, mọi ngân sách chạy đầy',turnover:'20:10 · Luân chuyển cổng, xe đầy chưa rút',fault:'19:05 · Cổng DC-01-2 báo lỗi',offline:'Mất kết nối trực tiếp',loading:'Đang tải',error:'Lỗi tải sơ đồ',notimpl:'Dịch vụ chưa sẵn sàng (501)'},
 schedule:{today:'Lịch hôm nay',replanning:'Đang lập lịch lại',replanned:'Đã lập lịch lại',assigning:'Xếp thủ công · đang gửi',assignok:'Xếp thủ công · đã xếp',assignpending:'Xếp thủ công · chờ duyệt',assignblocked:'Xếp thủ công · Guard chặn (AC6)',missing:'Hàng chờ thiếu chi tiết',otherday:'Ngày khác · chỉ xem',nodate:'Không có lịch cho ngày đã chọn',emptyplan:'Lịch chưa có phiên',emptyqueue:'Không có xe chờ',offline:'Mất kết nối trực tiếp',loading:'Đang tải',error:'Lỗi tải · có thể thử lại',notimpl:'Dịch vụ chưa sẵn sàng (501)'},
 approvals:{pending:'Chờ duyệt · đang chọn một đề nghị',submitting:'Đang gửi quyết định',decided:'Đã duyệt',execblocked:'Đã duyệt nhưng Guard chặn khi thực thi',conflict409:'Đề nghị đã được xử lý trước đó',expiredrow:'Một đề nghị hết hạn',blocked:'Tab Bị Guard chặn',log:'Tab Nhật ký quyết định',offline:'Mất kết nối trực tiếp',empty:'Không có đề nghị',loading:'Đang tải',error:'Lỗi tải · có thể thử lại',notimpl:'Dịch vụ chưa sẵn sàng (501)',postnotimpl:'Chưa gửi được quyết định (501)'},
 simulation:{default:'Có bảng đối chứng',running:'Đang chạy',ran:'Chạy xong · thêm cột kết quả',invalid:'Dữ liệu cần sửa',nobench:'Kịch bản chưa có đối chứng',powerlimit:'Sự cố · đổi giới hạn nguồn',confirm:'Xác nhận bơm sự cố',injected:'Đã bơm sự cố',loading:'Đang tải',noscenario:'Chưa có kịch bản',error:'Lỗi tải · có thể thử lại',notimpl:'Dịch vụ chưa sẵn sàng (501)'}
};
const opDefault=p=>Object.keys(OP_STATES[p])[0];
const is=(...ids)=>ids.includes(variant);

/* ---- Trạm + trạng thái đầu nối ---- */
const STATION={name:'Trạm sạc cư dân CP-01',perKw:7,limitKw:35};
const CST={charging:{label:'Đang sạc',mark:'#24654e',ico:'dot'},throttled:{label:'Giảm công suất',mark:'#a86f12',ico:'down'},idle:{label:'Trống',mark:'#6f8279',ico:'ring'},finished:{label:'Đã đầy',mark:'#326467',ico:'check'},fault:{label:'Lỗi',mark:'#963d32',ico:'cross'}};
const STICON={dot:'<circle cx="8" cy="8" r="5" fill="currentColor"/>',ring:'<circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2"/>',down:'<path d="M2.5 4h11L8 13z" fill="currentColor"/>',check:'<path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',cross:'<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'};
const stIcon=st=>`<svg viewBox="0 0 16 16" aria-hidden="true" style="color:${CST[st].mark}">${STICON[CST[st].ico]}</svg>`;
const stTag=st=>`<span class="tag ${{charging:'good',throttled:'gold',idle:'neutral',finished:'blue',fault:'bad'}[st]}">${stIcon(st)}${CST[st].label}</span>`;
function connectors(){
 if(is('empty'))return ['A01','A02','A03','A04','A05','A06','A07','A08'].map(id=>({id,st:'idle',kw:0}));
 if(is('powerdrop'))return [
  {id:'A01',st:'throttled',kw:3.5,car:'#a1c4',soc:[44,80],due:'21:30'},{id:'A02',st:'throttled',kw:3.5,car:'#b82e',soc:[57,90],due:'22:00'},{id:'A03',st:'idle',kw:0},
  {id:'A04',st:'throttled',kw:3.5,car:'#c09f',soc:[63,90],due:'22:00'},{id:'A05',st:'fault',kw:0,why:'Mất liên lạc với đầu nối lúc 18:47'},{id:'A06',st:'finished',kw:0,car:'#d7a0',soc:[100,100],due:'19:30'},
  {id:'A07',st:'throttled',kw:5.8,car:'#b7e2',soc:[46,90],due:'21:00',risk:'Trễ ~25 phút',why:'Ưu tiên xe gần hạn nhất khi nguồn giảm'},{id:'A08',st:'throttled',kw:3.5,car:'#e3f1',soc:[50,80],due:'23:00'}];
 return [
  {id:'A01',st:'charging',kw:7,car:'#a1c4',soc:[38,80],due:'21:30'},{id:'A02',st:'charging',kw:7,car:'#b82e',soc:[52,90],due:'22:00'},{id:'A03',st:'idle',kw:0},
  {id:'A04',st:'throttled',kw:4.2,car:'#c09f',soc:[61,90],due:'22:00',why:'Giữ tổng tải dưới 35 kW'},{id:'A05',st:'fault',kw:0,why:'Mất liên lạc với đầu nối lúc 18:47'},{id:'A06',st:'finished',kw:0,car:'#d7a0',soc:[100,100],due:'19:30'},
  {id:'A07',st:'throttled',kw:5.6,car:'#b7e2',soc:[41,90],due:'21:00',risk:'Trễ ~15 phút',why:'Giữ tổng tải dưới 35 kW'},{id:'A08',st:'charging',kw:5.6,car:'#e3f1',soc:[47,80],due:'23:00'}];}
const limitNow=()=>is('powerdrop')?20:STATION.limitKw;
const loadNow=()=>connectors().reduce((s,c)=>s+c.kw,0);
function pendingCount(){if(page==='approvals'){if(is('empty'))return 0;if(is('decided','execblocked','conflict409'))return 2;}return 3;}

/* ---- Khối trạng thái dùng lại ---- */
const skel=(n=3)=>`<div role="status" aria-label="Đang tải">${'<span class="sk"></span>'.repeat(n)}<span class="sk w40"></span></div>`;
const errBlock=(what)=>note('Chưa tải được '+what,'Kết nối tới máy chủ bị gián đoạn. Các khối khác vẫn hoạt động. '+textAction('recover','Thử lại'),'bad','wifi');
const implBlock=(what,task)=>note('Dịch vụ '+what+' chưa sẵn sàng','Máy chủ trả 501 · việc '+task+' chưa làm. Giao diện giữ chỗ để nối API sau.','gold','plug');
const disabledReason=(id,txt)=>`<span class="reason" id="${id}">${txt}</span>`;

/* ---- Khung ---- */
function liveState(){if(is('notimpl'))return ['off','Realtime chưa được cài đặt'];if(is('offline'))return ['off','Mất kết nối · hỏi lại mỗi 15 giây'];if(paused||is('paused'))return ['gold','Đã tạm dừng cập nhật'];if(is('stale'))return ['gold','Dữ liệu cũ'];if(is('loading'))return ['gold','Đang kết nối'];return ['on','Trực tiếp'];}
const brand=`<span class="brand-glyph"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/></svg></span>`;
function tabItem(p){const [l,g]=OP_PAGES[p],cur=p===page,n=p==='approvals'?pendingCount():0;return `<a href="${route(p)}" ${cur?'aria-current="page"':''} ${n?`aria-label="${l}, ${n} đề nghị chờ duyệt"`:''}>${icon(g)}${l}${n?`<span class="pill">${n}</span>`:''}${p==='map'?'<span class="new">Mới</span>':''}</a>`;}
function render(){document.title=OP_TITLES[page]+' · ChargePilot Vận hành';const [lc,lt]=liveState();const app=$('app');
 if(ui.signedOut){app.innerHTML=`<main class="op"><section class="panel status-page" style="max-width:560px;margin:60px auto"><span class="slab-icon">${icon('exit')}</span><h1 style="font-size:26px">Đã đăng xuất</h1><p>Ca vận hành đã kết thúc trên trình duyệt này.</p><div class="actions" style="justify-content:center">${action('restart','Mở lại bản mẫu','primary','refresh')}<a class="btn secondary" href="../login.html">Tới màn đăng nhập</a></div></section></main>`;return}
 app.innerHTML=`<a href="#main" class="skip" data-act="skip">Bỏ qua tới nội dung chính</a><div class="op"><header class="op-head"><div class="op-left"><a class="op-brand" href="${route('dashboard')}" aria-label="ChargePilot Vận hành, Dashboard">${brand}<span><b>ChargePilot</b><small>Control Center · Vận hành</small></span></a><nav class="op-tabs" aria-label="Điều hướng chính">${Object.keys(OP_PAGES).map(tabItem).join('')}</nav></div><div class="op-who"><span class="live ${lc}" role="status"><i aria-hidden="true"></i>${lt}</span><span class="sep" aria-hidden="true"></span><button type="button" class="btn secondary small" data-act="scenarios">${icon('layers')}Kịch bản mẫu</button><span class="who-text"><b>Vận hành A</b><span class="hint">Ca tối · ${STATION.name}</span></span><button type="button" class="btn secondary small" data-act="logout">Đăng xuất</button></div></header><main id="main" tabindex="-1" class="op-main">${OP_SCREENS[page]()}<p class="footnote">${icon('info')}Dữ liệu mô phỏng · Giờ trạm GMT+7 · Mọi lệnh tới trạm đi qua Guard</p></main></div>`;
 (OP_AFTER[page]||(()=>{}))();}
const OP_SCREENS={},OP_AFTER={};

/* ---- Toast, dialog ---- */
function toast(text){$('toast').innerHTML=text;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('toast').textContent=''},5200)}
function openDialog(t,body,wide=false){const dlg=$('modal');if(!dlg.open)modalReturn=document.activeElement;dlg.style.maxWidth=wide?'min(760px,calc(100vw - 28px))':'';dlg.innerHTML=`<div class="dialog-inner"><div class="section-head"><h2 id="dlg-title">${t}</h2><button type="button" class="iconbtn" data-act="close" aria-label="Đóng">${icon('close')}</button></div>${body}</div>`;dlg.setAttribute('aria-labelledby','dlg-title');if(!dlg.open)dlg.showModal();(dlg.querySelector('[data-safe]')||dlg.querySelector('button'))?.focus();}
function closeDialog(){if($('modal').open)$('modal').close();if(modalReturn?.isConnected)modalReturn.focus({preventScroll:true});modalReturn=null;}
function openScenarios(p=page,selected=variant){const ids=Object.keys(OP_STATES[p]);openDialog('Kịch bản mẫu',`<p class="subcopy">Chọn màn và tình huống để xem thử. Mỗi lần áp dụng sẽ nạp lại dữ liệu minh hoạ.</p><div class="screen-pick">${Object.entries(OP_PAGES).map(([k,[l,g]])=>`<button type="button" class="${k===p?'on':''}" data-act="pick-screen" data-page="${k}" aria-pressed="${k===p}">${icon(g)}${l}</button>`).join('')}</div>${selectField('scenario','Tình huống',ids.map(id=>[id,OP_STATES[p][id]]),ids.includes(selected)?selected:ids[0])}<div class="actions">${action('apply-scenario','Xem tình huống','primary','layers',`data-page="${p}"`)}</div><hr class="divider"><p class="hint">Bộ khác: <a class="textbtn" href="../cu-dan/resident.html">Cổng cư dân</a> · <a class="textbtn" href="../login.html">Đăng nhập</a> · <a class="textbtn" href="../index.html">Toàn cảnh</a></p>`);}

/* ---- Điều hướng: #/trang?state=… (giống bộ cu-dan) ---- */
function loadRoute(){const h=location.hash.replace(/^#/,'');let p=document.body.dataset.entry||'dashboard',params=new URLSearchParams();if(h.startsWith('/')){const [k,raw='']=h.slice(1).split('?');if(k in OP_PAGES)p=k;params=new URLSearchParams(raw);}else if(h&&OP_STATES[p]?.[h])params.set('state',h);
 const s=params.get('state');const changed=p!==page;page=p;variant=s&&OP_STATES[p][s]?s:opDefault(p);if(changed||s)ui={};paused=variant==='paused';if($('modal').open)closeDialog();render();window.scrollTo({top:0,behavior:'instant'});document.querySelector('.op-main h1')?.focus?.({preventScroll:true});(OP_OPEN[page]||(()=>{}))();}
const OP_OPEN={};
function setVariant(s,msg){variant=s;render();if(msg)toast(msg);}
document.addEventListener('click',e=>{const el=e.target.closest('[data-act]');if(!el)return;const a=el.dataset.act;
 if(a==='skip'){e.preventDefault();$('main')?.focus();return}
 if(a==='close'){closeDialog();return}
 if(a==='scenarios'){openScenarios();return}
 if(a==='pick-screen'){openScenarios(el.dataset.page,'');return}
 if(a==='apply-scenario'){const p=el.dataset.page,s=$('scenario').value;closeDialog();const h=route(p,'state='+s);if(location.hash===h)loadRoute();else location.hash=h;return}
 if(a==='recover'){variant=opDefault(page);ui={};render();toast('Đã tải lại dữ liệu mô phỏng.');return}
 if(a==='logout'){openDialog('Đăng xuất?',`<p class="subcopy">Kết thúc ca vận hành trên trình duyệt này. Lệnh đang chờ duyệt vẫn được giữ.</p><div class="actions">${action('close','Ở lại','secondary','','data-safe')}${action('do-logout','Đăng xuất','primary')}</div>`);return}
 if(a==='do-logout'){closeDialog();ui.signedOut=true;render();return}
 if(a==='restart'){ui={};render();return}
 (OP_ACTS[a]||(()=>{}))(el,e);});
const OP_ACTS={};
$('modal').addEventListener('click',e=>{if(e.target===$('modal')){const b=$('modal').getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)closeDialog();}});
window.addEventListener('hashchange',loadRoute);
