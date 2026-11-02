import React,{useEffect,useMemo,useRef,useState} from 'react';
import {FolderOpen,X,ChevronDown,Check,Search,Activity,AlertTriangle,ArrowRight} from 'lucide-react';
import {planBatch} from './batchPlan.js';
import ProductionSteps,{activeStatuses,statusLabel} from './ProductionSteps.jsx';

function uploadProject(form,signal,onProgress){
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();
  xhr.open('POST','/api/projects');
  xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(e.loaded,e.total)};
  xhr.onload=()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch{};if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(new Error(data.detail||`HTTP ${xhr.status}`))};
  xhr.onerror=()=>reject(new Error('Mất kết nối trong khi tải tệp.'));
  xhr.onabort=()=>reject(new DOMException('Đã dừng tải.','AbortError'));
  const abort=()=>xhr.abort();
  if(signal.aborted){abort();return}
  signal.addEventListener('abort',abort,{once:true});
  xhr.onloadend=()=>signal.removeEventListener('abort',abort);
  xhr.send(form);
 });
}

export default function BatchImport({health,onClose,onSetupChannels,onQueued,onOpenQueue,embedded=false}){
 const [files,setFiles]=useState([]),[channels,setChannels]=useState([]),[selected,setSelected]=useState([]),[assignment,setAssignment]=useState({}),[mappingMode,setMappingMode]=useState('all-markets');
 const [running,setRunning]=useState(false),[done,setDone]=useState(0),[uploading,setUploading]=useState(null),[transfer,setTransfer]=useState(0),[failures,setFailures]=useState([]),[message,setMessage]=useState(''),[batchProjects,setBatchProjects]=useState([]),[channelMenuOpen,setChannelMenuOpen]=useState(false),[channelQuery,setChannelQuery]=useState('');
 const batchId=useRef(crypto.randomUUID()),abort=useRef(null);
 useEffect(()=>{fetch('/api/channels').then(r=>r.json()).then(setChannels).catch(()=>{});},[]);
 useEffect(()=>{let alive=true;const refresh=()=>fetch('/api/projects').then(r=>r.json()).then(rows=>{if(alive)setBatchProjects(rows.filter(p=>p.batch_id===batchId.current))}).catch(()=>{});refresh();const timer=setInterval(refresh,1800);return()=>{alive=false;clearInterval(timer)}},[]);
 const connected=useMemo(()=>channels.filter(c=>c.youtube_channel_id&&c.configured),[channels]);
 const videos=useMemo(()=>files.filter(f=>f.name.toLowerCase().endsWith('.mp4')).map(f=>({path:(f.webkitRelativePath||f.name).replaceAll('\\','/')})),[files]);
 const plan=useMemo(()=>planBatch(files,channels,selected,assignment,mappingMode),[files,channels,selected,assignment,mappingMode]);
 const bytes=n=>`${(n/1024**3).toFixed(1)} GB`;
 async function upload(){setRunning(true);setDone(0);setFailures([]);setMessage('');setBatchProjects([]);abort.current=new AbortController();const errors=[];
  for(let i=0;i<plan.jobs.length;i++){if(abort.current.signal.aborted)break;const item=plan.jobs[i],form=new FormData();
   for(const [key,value] of Object.entries({name:item.name.slice(0,150),locale:item.locale,audio_mode:'voxcpm',batch_id:batchId.current,source_filename:item.path,channel_ids:JSON.stringify(item.channelIds)}))form.append(key,value);
   form.append('video',item.video);form.append('subtitles',item.subtitles);
   form.append('srt_kind',item.subtitles.name.toLowerCase().endsWith(`.${item.locale.toLowerCase()}.srt`)?'translated':'auto');
   setUploading(item);setTransfer(0);
   try{await uploadProject(form,abort.current.signal,(loaded,total)=>setTransfer(Math.round(loaded/total*100)));onQueued();}
   catch(e){if(e.name==='AbortError')break;errors.push(`${item.path} → ${item.locale}: ${e.message}`);setFailures([...errors]);}
   setDone(i+1);setUploading(null);setTransfer(0);
  }
  setRunning(false);setUploading(null);setMessage(abort.current.signal.aborted?'Đã dừng tải thêm. Những video đã nhận vẫn tiếp tục xử lý.':'Đã tải xong danh sách. Các bản xuất đang tự chạy và vẫn tiếp tục nếu bạn đóng cửa sổ này.');
 }
 const jobCounts=useMemo(()=>({active:batchProjects.filter(p=>activeStatuses.has(p.status)).length,queued:batchProjects.filter(p=>p.status==='queued').length,completed:batchProjects.filter(p=>p.status==='completed').length,attention:batchProjects.filter(p=>['failed','needs_attention','paused','canceled'].includes(p.status)).length}),[batchProjects]);
 const meanProgress=batchProjects.length?Math.round(batchProjects.reduce((sum,p)=>sum+(p.progress||0),0)/batchProjects.length):0;
 return <div className={embedded?'ref-batch-page':'overlay'}><div className={embedded?'ref-batch-content':'modal batch-modal'} role={embedded?undefined:'dialog'} aria-label="Nhập hàng loạt">
  <div className="section-title"><h2>Nhập hàng loạt</h2><button aria-label="Đóng" disabled={running} onClick={onClose}><X/></button></div>
  <p>Chọn tối đa 100 MP4 cùng SRT theo tên. Mỗi video nguồn chỉ dựng một lần cho mỗi ngôn ngữ và giọng; các kênh cùng nhóm dùng chung MP4 đó.</p>
  <button onClick={onSetupChannels}>Thiết lập kênh →</button>
  {connected.length?<div className="channel-picker channel-picker-dropdown"><div className="channel-picker-title"><span className="channel-picker-icon"><FolderOpen size={16}/></span><span><strong>Kênh nhận video</strong><small>Chọn các kênh muốn tạo bản xuất</small></span><span className="channel-picker-count">{selected.length}/{connected.length}</span></div><button type="button" className="channel-picker-trigger" disabled={running} aria-expanded={channelMenuOpen} onClick={()=>setChannelMenuOpen(open=>!open)}><span>{selected.length?`${selected.length} kênh đang được chọn`:'Chọn kênh nhận video'}</span><ChevronDown className={channelMenuOpen?'is-open':''} size={16}/></button>{selected.length>0&&<div className="channel-selected-summary">{connected.filter(c=>selected.includes(c.id)).map(c=><span key={c.id}><span>{c.name} · {c.locale}</span><button type="button" aria-label={`Bỏ chọn ${c.name}`} disabled={running} onClick={()=>setSelected(old=>old.filter(id=>id!==c.id))}><X size={12}/></button></span>)}</div>}{channelMenuOpen&&<div className="channel-picker-menu"><label className="channel-search"><Search size={14}/><input autoFocus placeholder="Tìm theo tên, quốc gia hoặc ngôn ngữ" value={channelQuery} onChange={e=>setChannelQuery(e.target.value)}/></label><div className="channel-picker-menu-actions"><span>{connected.filter(c=>`${c.name} ${c.country} ${c.locale}`.toLocaleLowerCase('vi').includes(channelQuery.toLocaleLowerCase('vi'))).length} kênh khả dụng</span><div><button type="button" disabled={running} onClick={()=>setSelected(connected.map(c=>c.id))}>Chọn tất cả</button><button type="button" disabled={running} onClick={()=>setSelected([])}>Bỏ chọn</button></div></div><div className="channel-picker-options">{connected.filter(c=>`${c.name} ${c.country} ${c.locale}`.toLocaleLowerCase('vi').includes(channelQuery.toLocaleLowerCase('vi'))).map(c=><label className={selected.includes(c.id)?'selected':''} key={c.id}><input type="checkbox" disabled={running} checked={selected.includes(c.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,c.id]:old.filter(id=>id!==c.id))}/><span className="channel-option-avatar">{c.youtube_thumbnail?<img src={c.youtube_thumbnail} alt=""/>:c.name?.slice(0,1)||'Y'}</span><span><strong>{c.name}</strong><small>{c.country} · {c.locale}</small></span>{selected.includes(c.id)&&<Check size={15}/>}</label>)}</div><button type="button" className="channel-picker-done" onClick={()=>setChannelMenuOpen(false)}>Xong</button></div>}</div>:<p className="warning">Cần kết nối kênh YouTube trước khi tạo dự án.</p>}
  <label>Cách phân phối<select disabled={running} value={mappingMode} onChange={e=>setMappingMode(e.target.value)}><option value="all-markets">Một bản cho mỗi ngôn ngữ + giọng, dùng chung cho các kênh</option><option value="per-channel">Gán riêng mỗi video nguồn cho một kênh</option></select></label>
  <label className="batch-picker"><FolderOpen size={25}/>Chọn thư mục MP4/SRT<input type="file" webkitdirectory="" multiple disabled={running} onChange={e=>setFiles([...e.target.files])}/></label>
  <label className="batch-picker secondary">Hoặc chọn nhiều tệp MP4/SRT<input type="file" accept=".mp4,.srt" multiple disabled={running} onChange={e=>setFiles([...e.target.files])}/></label>
  {mappingMode==='per-channel'&&!!videos.length&&<div className="assignment-list"><strong>Gán video cho kênh</strong>{videos.map(v=><label key={v.path}>{v.path}<select disabled={running} value={assignment[v.path]||''} onChange={e=>setAssignment(old=>({...old,[v.path]:e.target.value}))}><option value="">Chọn kênh…</option>{connected.filter(c=>selected.includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name} · {c.locale}</option>)}</select></label>)}</div>}
  {!!files.length&&<><div className="batch-summary"><strong>{plan.videoCount} video nguồn · {plan.jobs.length} bản xuất</strong><span>{bytes(plan.totalBytes)} cần tải lên</span><span>{plan.issues.length} tệp cần xử lý</span></div>
   {!!plan.issues.length&&<details className="warning" open><summary>Tệp chưa ghép được</summary>{plan.issues.slice(0,30).map((x,i)=><p key={i}>{x}</p>)}</details>}
   {!!plan.jobs.length&&<div className="batch-preview">{plan.jobs.slice(0,12).map(j=><div key={j.path+j.locale}>{j.path} → {j.locale} · {j.channelIds.length} kênh</div>)}{plan.jobs.length>12&&<p>… và {plan.jobs.length-12} bản khác</p>}</div>}
   {health?.disk_free_bytes<plan.totalBytes*2&&<p className="error">Ổ lưu trữ chỉ còn {bytes(health.disk_free_bytes)}. Hãy chia lô hoặc thêm dung lượng.</p>}
  </>}
  {running&&<section className="batch-live-upload" role="status"><div className="batch-live-heading"><span><strong>Đang tải tệp lên</strong><small>{uploading?.path} → {uploading?.locale}</small></span><b>{done}/{plan.jobs.length}</b></div><div className="batch-progress-track"><i style={{width:`${transfer}%`}}/></div><small>Đang gửi bản {Math.min(done+1,plan.jobs.length)} trên {plan.jobs.length} · {transfer}%</small></section>}
  {batchProjects.length>0&&<section className="batch-live-work"><div className="batch-live-heading"><span><strong><Activity size={16}/> Tiến độ xử lý lô</strong><small>Tự chạy tuần tự trên máy này · vẫn tiếp tục khi đóng cửa sổ</small></span><b>{jobCounts.completed}/{batchProjects.length} hoàn tất</b></div><div className="batch-progress-track overall"><i style={{width:`${meanProgress}%`}}/></div><div className="batch-live-counts"><span>{jobCounts.active} đang chạy</span><span>{jobCounts.queued} đang chờ</span><span>{jobCounts.completed} hoàn tất</span>{jobCounts.attention>0&&<span className="attention"><AlertTriangle size={13}/>{jobCounts.attention} cần xử lý</span>}</div><div className="batch-live-list">{batchProjects.map(p=><div className="batch-live-row" key={p.id}><span className="batch-live-title"><strong>{p.name}</strong><small>{p.locale} · {statusLabel[p.status]||p.status}</small>{p.progress_detail?.message&&<small className="batch-live-detail">{p.progress_detail.message}</small>}</span>{activeStatuses.has(p.status)?<ProductionSteps status={p.status} progress={p.progress||0}/>:p.error?<span className="batch-live-error" title={p.error}>{p.error}</span>:<span className={'status '+p.status}>{p.status==='completed'?'Hoàn tất':statusLabel[p.status]||p.status}</span>}<b>{p.progress||0}%</b></div>)}</div><button type="button" className="batch-queue-link" onClick={onOpenQueue}>Mở hàng đợi <ArrowRight size={14}/></button></section>}
  {message&&<p role="status">{message}</p>}
  {message&&!abort.current?.signal.aborted&&<p className="delivery-path">Thư mục bàn giao: <code>{health?.delivery_root}\{batchId.current}</code></p>}
  {message&&done>0&&<p><a href={`/api/batches/${batchId.current}/report.csv`} download>Tải báo cáo lô CSV</a> · Báo cáo cập nhật khi các video hoàn tất.</p>}
  {!!failures.length&&<details className="error" open><summary>{failures.length} bản lỗi</summary>{failures.map((e,i)=><p key={i}>{e}</p>)}</details>}
  <div className="batch-actions">{running?<button onClick={()=>abort.current.abort()}>Dừng tải thêm</button>:<button className="primary" disabled={!plan.jobs.length||plan.issues.length>0||plan.videoCount>100||!selected.length||!health?.tts.model_ready||health?.disk_free_bytes<plan.totalBytes*2} onClick={upload}>Đưa {plan.jobs.length} bản vào hàng đợi</button>}</div>
  <p className="note">Mỗi ngôn ngữ cần SRT đúng mã, ví dụ <code>film.ja-JP.srt</code>. Khi chọn nhiều ngôn ngữ, <code>film.srt</code> không được dùng chung cho tất cả. Hiện chỉ có dịch cục bộ Trung → Việt; các ngôn ngữ khác cần SRT đã dịch sẵn.</p>
 </div></div>;
}
