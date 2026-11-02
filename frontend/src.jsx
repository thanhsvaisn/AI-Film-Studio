import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Clapperboard,LayoutDashboard,Captions,AudioLines,Settings2,Plus,ArrowUpRight,Film,Check,Play,Pause,Download,X,FolderOpen,ShieldCheck,Globe2,Layers3,HardDrive,ChevronRight,Video,Activity,CloudUpload,Sparkles,Search,PanelLeft} from 'lucide-react';
import BatchImport from './BatchImport.jsx';
import SingleImport from './SingleImport.jsx';
import ChannelWorkspace from './ChannelWorkspace.jsx';
import ChannelSettings from './ChannelSettings.jsx';
import OverviewWorkspace from './OverviewWorkspace.jsx';
import ProjectWorkspace from './ProjectWorkspace.jsx';
import ProjectStudio from './ProjectStudio.jsx';
import QueuePage from './QueuePage.jsx';
import YouTubePublisher from './YouTubePublisher.jsx';
import VoiceWorkspace from './VoiceWorkspace.jsx';
import './style.css';
import './reference-ui.css';
import './channel-ui.css';
import './redesign-pages.css';
import './studio-ui.css';

const labels={draft:'Bản nháp',queued:'Đang chờ',translation:'Đang dịch',tts:'Tạo giọng đọc',audio_mixing:'Ghép âm thanh',qa:'Kiểm tra',mux:'Xuất video',completed:'Hoàn tất',needs_attention:'Cần kiểm tra',failed:'Có lỗi',paused:'Tạm dừng',canceled:'Đã hủy'};
const navItems=[['projects',LayoutDashboard,'Tổng quan'],['subtitles',Film,'Dự án'],['queue',Layers3,'Hàng đợi'],['voice',AudioLines,'Thư viện giọng'],['voice-preview',AudioLines,'Đọc thử văn bản'],['voice-clone',AudioLines,'Clone giọng mới'],['channels',Globe2,'Kênh YouTube'],['channel-settings',Settings2,'Cấu hình kênh'],['members',Film,'Thành viên và gói'],['settings',Settings2,'Cài đặt']];
const navGroups=[['Sản xuất',['projects','subtitles','queue']],['Giọng đọc',['voice','voice-preview']],['Phân phối',['channels','channel-settings']],['Không gian làm việc',['members']],['Thiết lập',['settings']]];
const activeStatuses=new Set(['queued','translation','tts','audio_mixing','qa','mux']);
async function api(path,options={}){const response=await fetch('/api'+path,options);const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Dữ liệu chưa hợp lệ. Kiểm tra các trường bắt buộc.');return data;}

function Sidebar({tab,setTab,activeCount,connectedCount,health,mobileOpen,onClose}){
 return <><aside className={'sidebar '+(mobileOpen?'sidebar-open':'')}><div className="brand"><span className="brand-mark"><AudioLines size={22}/></span><div><strong>AI Film Studio</strong><small>PRODUCTION WORKSPACE</small></div><button className="sidebar-close" aria-label="Đóng menu" onClick={onClose}><X size={18}/></button></div>
  <div className="workspace-switch"><span className="workspace-avatar">FS</span><div><strong>Studio cá nhân</strong><small>Không gian làm việc trên máy</small></div><span className="workspace-dot"/></div>
  <div className="nav-group">{navGroups.map(([group,ids])=><div className="nav-section" key={group}><p className="nav-caption">{group}</p><nav aria-label={group}>{ids.map(id=>{const [,Icon,title]=navItems.find(([key])=>key===id);return <button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)} aria-current={tab===id?'page':undefined}><Icon size={18}/><span>{title}</span>{id==='queue'&&activeCount>0&&<b>{activeCount}</b>}</button>})}</nav></div>)}</div>
  <div className="sidebar-bottom"><div className="sidebar-status"><span className="status-light"/><div><strong>{health?.tts?.model_ready?'Giọng đọc sẵn sàng':'Giọng đọc cần kiểm tra'}</strong><small>{connectedCount} kênh YouTube đã kết nối</small></div></div><div className="sidebar-account"><span className="account-avatar">FS</span><div><strong>Studio cá nhân</strong><small>Không gian làm việc</small></div></div></div>
 </aside>{mobileOpen&&<button className="mobile-scrim" aria-label="Đóng menu" onClick={onClose}/> }</>;
}

function Topbar({tab,health,projects,onOpen,onMenu}){
 const [query,setQuery]=useState(''),[searchOpen,setSearchOpen]=useState(false);
 const searchRef=useRef(null);
 useEffect(()=>{const key=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setSearchOpen(true);searchRef.current?.focus()}if(e.key==='Escape')setSearchOpen(false)};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[]);
 const results=query.trim()?projects.filter(p=>`${p.name} ${p.locale}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi'))).slice(0,6):[];
 const title=tab==='batch'?'Nhập hàng loạt':navItems.find(([id])=>id===tab)?.[2]||'Tổng quan';
 return <header className="topbar"><div className="topbar-left"><button className="mobile-menu" aria-label="Mở menu" onClick={onMenu}><PanelLeft size={19}/></button><div className="breadcrumb">Không gian làm việc <ChevronRight size={14}/><strong>{title}</strong></div></div><div className="topbar-actions"><div className="topbar-search"><Search size={16}/><input ref={searchRef} aria-label="Tìm dự án" placeholder="Tìm dự án..." value={query} onFocus={()=>setSearchOpen(true)} onBlur={()=>setTimeout(()=>setSearchOpen(false),150)} onChange={e=>setQuery(e.target.value)}/><kbd>Ctrl K</kbd>{searchOpen&&query.trim()&&<div className="topbar-search-results">{results.length?results.map(p=><button key={p.id} onMouseDown={e=>e.preventDefault()} onClick={()=>{onOpen(p);setQuery('');setSearchOpen(false)}}><Film size={16}/><span><strong>{p.name}</strong><small>{p.locale} · {labels[p.status]||p.status}</small></span><ArrowUpRight size={14}/></button>):<p>Không tìm thấy dự án phù hợp.</p>}</div>}</div><span className={'health-chip '+(health?.tts?.model_ready?'ok':'warn')}><span/>{health?.tts?.model_ready?'Giọng sẵn sàng':'Cần kiểm tra giọng'}</span><span className="topbar-divider"/><span className="topbar-live"><Activity size={16}/></span></div></header>;
}

function ProjectList({projects,open,onNew,emptyTitle='Chưa có dự án'}){
 if(!projects.length)return <div className="empty"><span className="empty-icon"><FolderOpen size={29}/></span><h3>{emptyTitle}</h3><p>Thêm video và phụ đề để bắt đầu sản xuất bản lồng tiếng.</p><button className="button-primary" onClick={onNew}><Plus size={16}/> Tạo dự án</button></div>;
 return <div className="project-list">{projects.map(p=><button className="project-row" key={p.id} onClick={()=>open(p)}><span className="project-icon"><Video size={20}/></span><span className="project-info"><strong>{p.name}</strong><small>{p.locale} <i/> {Number(p.duration/60).toFixed(1)} phút <i/> {p.audio_mode==='approved'?'Âm thanh WAV':'Giọng AI'}</small></span><span className={'status '+p.status}>{labels[p.status]||p.status}</span><span className="project-progress">{p.progress||0}%</span><ArrowUpRight size={17} className="project-arrow"/></button>)}</div>;
}

function ProjectDetail({selected,active,dirty,busy,error,change,save,action,onNew,onBack,player}){
 if(!selected)return <><div className="page-heading"><div><p className="eyebrow">DỰ ÁN & PHỤ ĐỀ</p><h1>Không gian biên tập</h1><p>Chọn một dự án để xem video, chỉnh phụ đề và đăng YouTube.</p></div><button className="button-primary" onClick={onNew}><Plus size={16}/> Dự án mới</button></div><div className="empty"><span className="empty-icon"><Captions size={28}/></span><h3>Chưa chọn dự án</h3><p>Mở dự án từ trang Tổng quan hoặc tạo một dự án mới.</p><button className="button-primary" onClick={onNew}>Tạo dự án</button></div></>;
 return <><div className="page-heading project-heading"><div><button className="library-back" onClick={onBack}>← Danh sách dự án</button><p className="eyebrow">DỰ ÁN / {selected.locale}</p><h1>{selected.name}</h1><p>{selected.segments.length} dòng phụ đề · {Number(selected.duration/60).toFixed(1)} phút · {selected.channel_ids?.length||0} kênh đích</p></div><span className={'status '+selected.status}>{labels[selected.status]||selected.status}</span></div>
  <div className="editor-grid"><div className="card player-card"><div className="section-title"><div><h2>Xem trước nguồn phim</h2><p>Kiểm tra hình và thời gian lời thoại.</p></div></div><video ref={player} controls src={`/api/projects/${selected.id}/files/source`}/></div>
  <div className="card production-card"><div className="section-title"><div><h2>Tiến độ sản xuất</h2><p>Bản xuất {selected.locale} · một giọng đọc xuyên suốt</p></div></div><div className="production-status"><span className={'big-status '+selected.status}>{labels[selected.status]||selected.status}</span><strong>{selected.progress||0}%</strong></div><progress max="100" value={selected.progress||0}/><p>Phụ đề tiếng Trung được dịch sang tiếng Việt khi cần. Phụ đề đã dịch được dùng trực tiếp.</p>{selected.error&&<p className="error">{selected.error}</p>}<div className="actions"><button className="button-primary" disabled={busy||dirty||active.some(p=>p.id===selected.id)} onClick={()=>action('start')}><Play size={15}/> Xuất / tiếp tục</button><button disabled={busy} onClick={()=>action('pause')}><Pause size={15}/> Tạm dừng</button><button disabled={busy} onClick={()=>action('cancel')}>Hủy</button></div>{selected.status==='completed'&&<div className="downloads">{[['video','Video MP4'],['srt','Phụ đề SRT'],['report','Báo cáo QA']].map(([kind,title])=><a key={kind} href={`/api/projects/${selected.id}/files/${kind}`}><Download size={15}/>{title}</a>)}</div>}</div></div>
  <YouTubePublisher project={selected}/>
  {selected.warnings.length>0&&<details className="warning" open><summary>{selected.warnings.length} điểm cần kiểm tra</summary>{selected.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>}
  <section className="card subtitles-card"><div className="section-title"><div><h2>Phụ đề & bản dịch</h2><p>Điều chỉnh nội dung và thời gian từng câu trước khi xuất.</p></div><button className="button-primary" disabled={busy||!dirty} onClick={save}>Lưu thay đổi{dirty?' *':''}</button></div>{error&&<p role="alert" className="error">{error}</p>}<div className="table-wrap"><table><thead><tr><th>#</th><th>Bắt đầu (giây)</th><th>Kết thúc (giây)</th><th>Nội dung đã dịch</th><th>Nghe</th></tr></thead><tbody>{selected.segments.map((s,i)=><tr key={s.id}><td>{s.id}</td><td><input aria-label={`Bắt đầu ${s.id}`} type="number" step="0.001" value={s.start} onChange={e=>change(i,'start',Number(e.target.value))}/></td><td><input aria-label={`Kết thúc ${s.id}`} type="number" step="0.001" value={s.end} onChange={e=>change(i,'end',Number(e.target.value))}/></td><td><textarea aria-label={`Nội dung ${s.id}`} value={s.text} onChange={e=>change(i,'text',e.target.value)}/></td><td><button aria-label={`Phát dòng ${s.id}`} onClick={()=>{player.current.currentTime=s.start;player.current.play()}}><Play size={14}/></button></td></tr>)}</tbody></table></div></section></>;
}

function VoiceSettings({tab,health,onNew}){
 const voice=tab==='voice';
 return <><div className="page-heading"><div><p className="eyebrow">{voice?'VOICE WORKSPACE':'CẤU HÌNH'}</p><h1>{voice?'Giọng đọc & âm thanh':'Mô hình & cài đặt'}</h1><p>{voice?'Thiết lập nguồn giọng cho bản lồng tiếng.':'Kiểm tra các thành phần đang chạy trên máy này.'}</p></div></div><div className="settings-grid"><div className="card feature-card"><span className="feature-icon violet"><AudioLines size={23}/></span><h2>VoxCPM2 · Giọng mặc định</h2><p>Một giọng đọc nhất quán cho từng ngôn ngữ. Mẫu giọng được tạo và tái sử dụng cho các video tiếp theo.</p><div className="system-line"><span>Thư viện</span><b className={health?.tts?.installed?'ready':'missing'}>{health?.tts?.installed?'Đã cài':'Chưa cài'}</b></div><div className="system-line"><span>Mô hình</span><b className={health?.tts?.model_ready?'ready':'missing'}>{health?.tts?.model_ready?'Sẵn sàng':'Chưa sẵn sàng'}</b></div></div>
  <div className="card feature-card"><span className="feature-icon blue"><ShieldCheck size={23}/></span><h2>Âm thanh WAV đã duyệt</h2><p>Dùng bản lồng tiếng đã đồng bộ với video khi bạn muốn bỏ qua bước tạo giọng AI.</p><button className="button-secondary" onClick={onNew}>Tạo dự án với WAV <ArrowUpRight size={15}/></button></div>
  <div className="card feature-card"><span className="feature-icon green"><Film size={23}/></span><h2>Bộ xuất video</h2><p>Hình ảnh giữ nguyên, âm thanh được thay bằng lời thoại mới. Bản xuất kèm MP4, SRT và báo cáo QA.</p><div className="system-line"><span>FFmpeg</span><b className={health?.ffmpeg?'ready':'missing'}>{health?.ffmpeg?'Sẵn sàng':'Chưa tìm thấy'}</b></div><div className="system-line"><span>ffprobe</span><b className={health?.ffprobe?'ready':'missing'}>{health?.ffprobe?'Sẵn sàng':'Chưa tìm thấy'}</b></div></div>
  <div className="card feature-card"><span className="feature-icon amber"><CloudUpload size={23}/></span><h2>YouTube & dữ liệu</h2><p>Kênh kết nối qua Google. SEO, ảnh bìa và proxy được đặt riêng trước khi đăng video.</p><p className="note">Đăng video chỉ bắt đầu khi bạn bấm đăng trên dự án đã hoàn tất.</p></div></div></>;
}

function App(){
 const [tab,setTab]=useState(navItems.some(([id])=>id===new URLSearchParams(location.search).get('tab'))?new URLSearchParams(location.search).get('tab'):'projects');
 const [projects,setProjects]=useState([]),[channels,setChannels]=useState([]),[health,setHealth]=useState(null),[selected,setSelected]=useState(null);
 const [showImport,setShowImport]=useState(false),[showBatch,setShowBatch]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
 const [configuredChannelId,setConfiguredChannelId]=useState('');
 const [mobileOpen,setMobileOpen]=useState(false);
 const player=useRef(null);
 useEffect(()=>{const url=new URL(location.href);url.searchParams.set('tab',tab);history.replaceState(null,'',url)},[tab]);
 const refresh=async()=>{const [p,h,c]=await Promise.all([api('/projects'),api('/health'),api('/channels')]);setProjects(p);setHealth(h);setChannels(c)};
 useEffect(()=>{refresh().catch(e=>setError(e.message));const timer=setInterval(()=>refresh().catch(()=>{}),5000);return()=>clearInterval(timer)},[]);
 useEffect(()=>{if(!selected||dirty)return;const timer=setInterval(()=>api('/projects/'+selected.id).then(setSelected).catch(e=>setError(e.message)),2500);return()=>clearInterval(timer)},[selected?.id,dirty]);
 async function perform(fn){setError('');setBusy(true);try{await fn();await refresh()}catch(e){setError(e.message)}finally{setBusy(false)}}
 function open(p){if(dirty&&!window.confirm('Bỏ thay đổi chưa lưu?'))return;perform(async()=>{setSelected(await api('/projects/'+p.id));setDirty(false);setTab('subtitles')})}
 async function create(form){setError('');setBusy(true);try{const p=await api('/projects',{method:'POST',body:form});await refresh();setShowImport(false);setSelected(p);setDirty(false);setTab('subtitles');return true}catch(e){setError(e.message);return false}finally{setBusy(false)}}
 const active=projects.filter(p=>activeStatuses.has(p.status));
 const change=(index,key,value)=>{setSelected(p=>({...p,segments:p.segments.map((s,i)=>i===index?{...s,[key]:value}:s)}));setDirty(true)};
 const action=(name)=>perform(async()=>{setSelected(await api(`/projects/${selected.id}/${name}`,{method:'POST'}))});
 const save=()=>perform(async()=>{setSelected(await api(`/projects/${selected.id}/subtitles`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:selected.revision,segments:selected.segments})}));setDirty(false)});
 return <div className="app-shell"><Sidebar tab={tab} setTab={id=>{setShowBatch(false);setShowImport(false);setTab(id);setMobileOpen(false)}} activeCount={active.length} connectedCount={channels.filter(c=>c.youtube_channel_id).length} health={health} mobileOpen={mobileOpen} onClose={()=>setMobileOpen(false)}/><div className="main-column"><Topbar tab={showBatch?'batch':tab} health={health} projects={projects} onOpen={open} onMenu={()=>setMobileOpen(true)}/><main className="content">{error&&<div role="alert" className="error app-error">{error}<button aria-label="Đóng lỗi" onClick={()=>setError('')}><X size={16}/></button></div>}
  {showImport&&<SingleImport health={health} busy={busy} error={error} onClose={()=>setShowImport(false)} onSetupChannels={()=>{setShowImport(false);setTab('channel-settings')}} onSubmit={create}/>}
  {!showImport&&showBatch&&<BatchImport embedded health={health} onClose={()=>setShowBatch(false)} onSetupChannels={()=>{setShowBatch(false);setTab('channel-settings')}} onQueued={refresh} onOpenQueue={()=>{setShowBatch(false);setTab('queue')}}/>}
  {!showBatch&&!showImport&&tab==='projects'&&<OverviewWorkspace projects={projects} channels={channels} health={health} onNew={()=>setShowImport(true)} onBatch={()=>setShowBatch(true)} onChannels={()=>setTab('channels')} onQueue={()=>setTab('queue')} open={open}/>}
  {!showBatch&&!showImport&&tab==='subtitles'&&(selected?<ProjectStudio selected={selected} active={active} dirty={dirty} busy={busy} error={error} change={change} save={save} action={action} onBack={()=>{if(dirty&&!window.confirm('Bỏ thay đổi chưa lưu?'))return;setSelected(null);setDirty(false)}} player={player}/>:<ProjectWorkspace projects={projects} open={open} onNew={()=>setShowImport(true)} onBatch={()=>setShowBatch(true)}/>) }
  {!showBatch&&!showImport&&tab==='channels'&&<ChannelWorkspace onConfigure={id=>{setConfiguredChannelId(id||'');setTab('channel-settings')}}/>}
  {!showBatch&&!showImport&&tab==='channel-settings'&&<ChannelSettings selectedId={configuredChannelId} onBack={()=>setTab('channels')}/>}
  {!showBatch&&!showImport&&tab==='queue'&&<QueuePage projects={projects} health={health} open={open} onNew={()=>setShowImport(true)}/>}
  {!showBatch&&!showImport&&(['voice','voice-preview','voice-clone','members','settings'].includes(tab))&&<VoiceWorkspace tab={tab} health={health} channels={channels} onNavigate={setTab} onNew={()=>setShowImport(true)}/>}</main></div></div>;
}

createRoot(document.getElementById('root')).render(<App/>);
