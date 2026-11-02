import React,{useState} from 'react';
import {Film,FolderOpen,Layers3,Plus,Search,Video} from 'lucide-react';
import {activeStatuses,statusLabel} from './ProductionSteps.jsx';

const filters=[['all','Tất cả'],['active','Đang xử lý'],['completed','Hoàn tất'],['attention','Cần kiểm tra'],['draft','Bản nháp']];
const matches=(p,filter)=>filter==='all'||(filter==='active'&&activeStatuses.has(p.status))||(filter==='completed'&&p.status==='completed')||(filter==='attention'&&['failed','needs_attention'].includes(p.status))||(filter==='draft'&&p.status==='draft');

export default function ProjectLibrary({projects,open,onNew,onBatch}){
 const [search,setSearch]=useState(''),[filter,setFilter]=useState('all'),[layout,setLayout]=useState('grid');
 const visible=projects.filter(p=>matches(p,filter)&&`${p.name} ${p.locale}`.toLocaleLowerCase('vi').includes(search.trim().toLocaleLowerCase('vi')));
 const counts=Object.fromEntries(filters.map(([id])=>[id,projects.filter(p=>matches(p,id)).length]));
 return <div className="ref-library"><div className="page-heading ref-heading"><div><h1>Dự án</h1><p>{projects.length} bản xuất. Chọn một dự án để mở Studio chỉnh phụ đề và giọng.</p></div><div className="ref-heading-actions">{onBatch&&<button onClick={onBatch}><FolderOpen size={17}/> Nhập hàng loạt</button>}<button className="button-primary" onClick={onNew}><Plus size={17}/> Dự án mới</button></div></div>
  <div className="ref-library-tools"><div className="ref-filter-tabs">{filters.map(([id,title])=><button key={id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{title} <span>{counts[id]}</span></button>)}</div><div className="ref-library-controls"><label><Search size={17}/><input aria-label="Tìm dự án" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Tìm theo tên video"/></label><button className={layout==='grid'?'active':''} aria-label="Xem dạng lưới" onClick={()=>setLayout('grid')}><Film size={16}/></button><button className={layout==='list'?'active':''} aria-label="Xem dạng danh sách" onClick={()=>setLayout('list')}><Layers3 size={16}/></button></div></div>
  {visible.length?<div className={`ref-project-grid ${layout==='list'?'as-list':''}`}>{visible.map((p,index)=><button className="ref-project-card" key={p.id} onClick={()=>open(p)}><span className={`ref-project-cover art-${index%5}`}><Video size={29}/><span className={'status '+p.status}>{statusLabel[p.status]||p.status}</span><small>{(Number(p.duration)/60).toFixed(1)} phút</small></span><span className="ref-project-title">{p.name}</span><span className="ref-project-meta"><span className="ref-language">{p.locale}</span><span>{p.audio_mode==='approved'?'WAV đã duyệt':'Giọng AI'}</span><span>{p.progress||0}%</span></span></button>)}</div>:<div className="ref-empty-state"><FolderOpen size={31}/><h2>{projects.length?'Không tìm thấy dự án':'Chưa có dự án'}</h2><p>{projects.length?'Đổi bộ lọc hoặc từ khóa tìm kiếm.':'Nhập video và SRT để bắt đầu.'}</p>{!projects.length&&<button className="button-primary" onClick={onNew}>Tạo dự án đầu tiên</button>}</div>}
 </div>;
}
