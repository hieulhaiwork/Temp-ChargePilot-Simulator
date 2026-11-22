'use strict';
const FILES={home:'resident.html',book:'resident-book.html',plan:'resident-plan.html',notifications:'resident-notifications.html',approval:'resident-approval.html',profile:'resident-profile.html',map:'resident-map.html'};
const PAGES={home:['Trang chủ','home'],book:['Đặt lịch','calendar'],plan:['Lịch sạc','activity'],notifications:['Thông báo','bell'],approval:['Đề nghị điều chỉnh','adjust'],profile:['Hồ sơ','user'],map:['Sơ đồ bãi','map']};
const MIN=60000, BASE=Date.UTC(2026,10,17,22,36,32), STDSTART='2026-11-17T23:00', STDEND='2026-11-18T07:00';
const stamp=s=>typeof s==='string'&&s?Date.parse(s+'Z'):NaN;
const iso=n=>Number.isFinite(n)?new Date(n).toISOString().slice(0,16):'';
const hm=n=>Number.isFinite(n)?new Date(n).toISOString().slice(11,16):'—';
const day=n=>Number.isFinite(n)?new Date(n).toISOString().slice(5,10).split('-').reverse().join('/'):'—';
const fmtDay=n=>new Intl.DateTimeFormat('vi-VN',{weekday:'long',day:'2-digit',month:'2-digit',year:'numeric',timeZone:'UTC'}).format(n).replace(/^./u,s=>s.toLocaleUpperCase('vi'));
const caps={'DEMO-60':60,'DEMO-45':45};
const carLabel=v=>`Xe mẫu ${caps[v]||60} kWh`;
const cars=Object.keys(caps).map(v=>[v,carLabel(v)]);
const defaultProfile={name:'Minh Anh',vehicle:'DEMO-60',target:80,delay:30,reduce:true,emergency:true};
const demoNow=()=>S.time+Math.max(0,Date.now()-S.anchor);
const consentOf=p=>({delay:p.delay,reduce:p.reduce,emergency:p.emergency});
const baseRequest=(p=defaultProfile)=>({vehicle:p.vehicle,now:32,target:p.target,arrival:STDSTART,deadline:STDEND,mode:'reserve'});
function quote(req,queued=false){const capacity=caps[req.vehicle]||60;const into=capacity*(req.target-req.now)/100;const energy=into/.9;const start=stamp(req.arrival)+(queued?75*MIN:0);const avg=queued?40/(445/60):32/6.5;const rate=queued?1355:1200;const duration=Math.ceil(Math.round(energy/avg*60*1000)/1000/5)*5;return {req:clone(req),start,end:start+duration*MIN,limit:stamp(req.deadline),into,energy,cost:Math.round(energy*rate),rate,avg,power:7,connector:queued?'':'A07',queued,position:queued?3:null};}
function basicBooking(){return {...quote(baseRequest()),id:'CP-A07-1711',phase:'booked',consent:consentOf(defaultProfile),position:2};}
function baseNotes(){return [{id:'a0',type:'approval',title:'Trạm đề nghị điều chỉnh lịch sạc A07',short:'Đổi công suất trong giờ đầu. Xem giờ sạc xong trước khi trả lời.',body:'Trạm đề nghị giảm A07 từ 7 kW xuống 3,5 kW trong khung 23:00–00:00 để cân bằng tải.',time:'22:34',read:false},{id:'e0',type:'emergency',title:'Trạm đã giảm công suất khẩn cấp',short:'Nguồn cấp giảm còn 20 kW. Lịch của bạn vẫn kịp hạn 07:00.',body:'Lúc 18:02, nguồn cấp giảm từ 35 xuống 20 kW. Trạm đã giảm công suất theo phạm vi bảo vệ khẩn cấp đã đồng ý và gửi thông báo sau khi thực hiện.',time:'18:02',read:false},{id:'c0',type:'schedule',title:'Lịch A07 đã được cập nhật',short:'Khung sạc đêm nay là 23:00–05:30.',body:'Trạm đã tính lại lịch. Xe dự kiến đạt 80% lúc 05:30 và bạn có thể lấy xe lúc 07:00.',time:'17:40',read:true},{id:'i0',type:'info',title:'Đã xác nhận lịch sạc',short:'Lịch sạc đêm 17/11 trên đầu nối A07 đã được giữ chỗ.',body:'Yêu cầu đặt lịch đã được xác nhận. Bạn có thể xem phương án và phạm vi đã đồng ý trong Lịch sạc.',time:'16/11',read:true}];}
const emptyApproval=()=>({status:'none',expires:null,decided:null,note:'',bookingId:null});
function seed(active=true){return {schema:1,profile:clone(defaultProfile),booking:active?basicBooking():null,draft:null,form:null,chat:[],time:BASE,anchor:Date.now(),approval:active?{status:'pending',expires:BASE+748000,decided:null,note:'',bookingId:'CP-A07-1711'}:emptyApproval(),notes:active?baseNotes():[],signedOut:false,deleted:false};}
const STORE='chargepilot.resident.v3';let storage=true;
function readStore(){try{const data=JSON.parse(localStorage.getItem(STORE)||'null');return data&&data.schema===1&&data.profile&&Array.isArray(data.notes)?data:null}catch{return null}}
let S=readStore()||seed(document.body.dataset.entry!=='book');
function save(){try{localStorage.setItem(STORE,JSON.stringify(S))}catch{storage=false}}
let page='home', variant='', view='', filter='all', expanded=new Set(), toastTimer, modalReturn=null, touchedRoute=false;let chatText='',chatWaiting=false,chatToken=0;let openNote=false,modeSource='';
const unread=()=>S.notes.filter(n=>!n.read).length;
function toast(text){$('toast').textContent=text;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('toast').textContent=''},4400)}
function addNotice(type,title,short,body){const id='n'+Date.now()+Math.random().toString(36).slice(2,5);S.notes.unshift({id,type,title,short,body,time:hm(demoNow()),read:false});return id;}
function expire(){const a=S.approval;if(a.status==='pending'&&a.expires!==null&&demoNow()>=a.expires){a.status='expired';a.decided=a.expires;save();return true}return false;}
function consentList(c){return `<ul class="checks">${[[c.delay?'Lùi giờ bắt đầu tối đa '+c.delay+' phút':'Giữ nguyên giờ bắt đầu','clock'],[c.reduce?'Được giảm công suất nếu vẫn kịp hạn':'Hỏi lại trước khi giảm công suất','adjust'],[c.emergency?'Bảo vệ khẩn cấp được thực hiện và thông báo sau':'Chưa đồng ý trước với bảo vệ khẩn cấp','shield']].map(([s,i])=>`<li>${icon(i)}<span>${s}</span></li>`).join('')}</ul>`;}
function initials(n){return n.trim().split(/\s+/).filter(Boolean).slice(-2).map(w=>w[0]).join('').toLocaleUpperCase('vi')||'CD';}
const badgeStatus=(b)=>b.phase==='charging'?'Đang sạc':b.queued?'Trong hàng chờ':'Đã xác nhận';
const gapTime=q=>Math.round((q.limit-q.end)/MIN);
const buffer=q=>gapTime(q)>0?'Sớm '+minutes(gapTime(q)):gapTime(q)===0?'Vừa kịp giờ lấy xe':'Trễ '+minutes(-gapTime(q));
function defaultForm(){return baseRequest(S.profile)}
function stopPreview(){variant='';}
function statusCard(titleTxt,desc,actionHtml='',type='info'){return panel(`<div class="stateview"><span class="slab-icon">${icon(type)}</span><h2>${titleTxt}</h2><p>${desc}</p>${actionHtml}</div>`,'status-page');}
const loadNames={home:'thông tin xe',book:'danh mục xe',plan:'lịch sạc',notifications:'thông báo',approval:'đề nghị điều chỉnh',profile:'hồ sơ cư dân',map:'sơ đồ bãi'};
function genericState(){if(!['loading','error','notimpl'].includes(variant))return '';const name=loadNames[page];if(variant==='loading')return panel(`<div class="stateview" role="status"><span class="slab-icon">${icon('clock')}</span><h2>Đang tải ${name}…</h2><div class="skeleton"></div><div class="skeleton short"></div>${textAction('recover','Hoàn tất tải mô phỏng')}</div>`,'status-page');if(variant==='error')return statusCard('Chưa tải được '+name,'Kết nối bị gián đoạn. Dữ liệu đã lưu vẫn có trên thiết bị.',action('recover','Thử lại','primary','refresh'),'wifi');return statusCard('Tính năng đang chờ kết nối',`Dịch vụ ${name} chưa sẵn sàng trong tình huống này.`,action('recover','Trở về bản mô phỏng','primary','back'),'plug');}
const navHome=()=>route('home');
