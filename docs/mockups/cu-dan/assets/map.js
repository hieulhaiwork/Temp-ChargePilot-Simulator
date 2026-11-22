/* Màn 7 · Sơ đồ bãi (cư dân) — spec 21 §2.8, ADR-010.
   Cư dân chỉ thấy ô của mình đầy đủ; ô của người khác chỉ có 3 mức "Đang dùng / Trống / Tạm ngưng" (NFR riêng tư).
   Topology bãi hybrid AC/DC theo ADR-010 (Proposed) — khác số đầu nối A01–A08 ở các màn còn lại. */
const MAP_STATES={
 queued:{clock:'18:30',ports:{'AC-01-1':{status:'charging'},'AC-02-1':{status:'charging'},'DC-01-1':{status:'throttled'},'DC-01-2':{status:'throttled'}},queues:{AC:[{},{}],DC:[{},{},{}]},mine:null,mineQueue:{zone:'AC',pos:1},
  card:{eyebrow:'Xe của bạn · vùng AC',big:'Chờ vị trí 1',rows:[['Dự kiến vào cổng','~20:00'],['Đạt 65%','~22:16'],['Lấy xe','23:15']],chip:'Dự phòng 59 phút'},
  steps:['Vào bằng Lối vào phía đường nội khu.','Đi thẳng tới <b>Làn chờ AC</b>, đỗ ở vạch số 1.','Ứng dụng báo khi một cổng AC trống. Bạn có 10 phút để chuyển xe vào ô.']},
 charging:{clock:'20:10',ports:{'AC-01-1':{status:'charging',veh:'Xe của bạn',kw:11,soc:.33,target:.65},'AC-02-1':{status:'finished'},'DC-01-1':{status:'charging'},'DC-01-2':{status:'finished'}},queues:{AC:[{}],DC:[]},mine:'AC-01-1',mineQueue:null,
  card:{eyebrow:'Xe của bạn · ô B-A1 · cổng AC-01-1',big:'Đang sạc 11 kW',rows:[['Pin','33% → 65%'],['Đạt mục tiêu','~22:16'],['Lấy xe','23:15']],chip:'Dự phòng 59 phút'},
  steps:['Xe đang ở ô <b>B-A1</b>, vùng AC, ngay trước tủ AC-01.','Không cần làm gì. Trạm tự điều chỉnh công suất trong giới hạn của khu.']},
 done:{clock:'22:20',ports:{'AC-01-1':{status:'finished',veh:'Xe của bạn',kw:0,soc:.65,target:.65},'AC-02-1':{status:'charging'},'DC-01-1':{status:'idle'},'DC-01-2':{status:'idle'}},queues:{AC:[],DC:[]},mine:'AC-01-1',mineQueue:null,
  card:{eyebrow:'Xe của bạn · ô B-A1 · cổng AC-01-1',big:'Đã đạt 65%',rows:[['Xong lúc','22:16'],['Cần rời ô trước','23:15']],chip:'Cổng vẫn giữ cho bạn tới 23:15'},
  steps:['Xe ở ô <b>B-A1</b>, vùng AC.','Rút sạc và rời ô trước 23:15 để xe sau vào cổng.','Ra bằng Lối ra phía đường nội khu.']}
};
const mapKey=()=>MAP_STATES[variant]?variant:(variant==='offline'?'charging':'queued');
const mapNarrow=()=>window.matchMedia('(max-width:720px)').matches;
function mapScreen(){const D=MAP_STATES[mapKey()],M=window.SiteMap,c=D.card;const free={AC:0,DC:0};M.SITE.ports.forEach(p=>{if(D.ports[p.id].status==='idle')free[p.zone]++;});
 return `<div class="columns map-cols"><div class="stack">${panel(title('Khu sạc lúc '+D.clock,'map',tag('Bãi hybrid AC/DC','neutral'))+`<svg class="map-svg" id="site-map" role="img"></svg><ul class="map-legend" id="map-legend" aria-label="Chú giải"></ul><p class="hint mt">Bạn chỉ thấy ô nào đang dùng hay còn trống, không thấy xe của cư dân khác.</p>`)}${note('Bố cục theo phương án bãi hybrid (ADR-010, chờ duyệt)','Tên cổng ở đây (AC-01-1, DC-01-2…) theo tủ AC/DC mới. Các màn khác vẫn dùng đầu nối A01–A08 của PRD v0.2.','gold','info')}</div>
 <aside class="stack side-stack"><section class="panel map-mine" aria-labelledby="mine-h"><p class="eyeline" id="mine-h">${c.eyebrow}</p><p class="map-big">${c.big}</p><div class="map-row">${c.rows.map(([k,v])=>`<span>${k} <b class="num">${v}</b></span>`).join('')}</div><span class="map-chip">${icon('clock')}${c.chip}</span></section>
 ${panel(title('Cổng còn trống','plug')+`<div class="map-free">${['AC','DC'].map(z=>`<div><b class="num">${free[z]}/2</b><span>cổng ${z} · ${z==='AC'?'11 kW':'tới 60 kW'} · chờ ${D.queues[z].length} xe</span></div>`).join('')}</div>`)}
 ${panel(title('Đường tới chỗ của bạn','pin')+`<ol class="map-steps">${D.steps.map(s=>`<li><span>${s}</span></li>`).join('')}</ol>`)}</aside></div>`;}
function drawMap(){const el=$('site-map');if(!el)return;const D=MAP_STATES[mapKey()],M=window.SiteMap;M.renderMap(el,{layout:mapNarrow()?'portrait':'landscape',ports:D.ports,queues:D.queues,privacy:true,mine:D.mine,mineQueue:D.mineQueue,interactive:false,title:'Sơ đồ khu sạc'});const free={AC:0,DC:0};M.SITE.ports.forEach(p=>{if(D.ports[p.id].status==='idle')free[p.zone]++;});const where=D.mine?`Xe của bạn ở ô ${M.SITE.ports.find(p=>p.id===D.mine).bay}`:`Xe của bạn ở làn chờ ${D.mineQueue.zone}, vị trí ${D.mineQueue.pos}`;el.setAttribute('aria-label',`Sơ đồ khu sạc. ${where}. Cổng AC trống ${free.AC} trên 2, cổng DC trống ${free.DC} trên 2. Chờ AC ${D.queues.AC.length} xe, chờ DC ${D.queues.DC.length} xe.`);M.legend($('map-legend'),'public');}
window.matchMedia('(max-width:720px)').addEventListener('change',()=>{if(page==='map')drawMap();});
