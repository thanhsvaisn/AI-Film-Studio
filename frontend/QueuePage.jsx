import React,{useState} from 'react';
import {ChevronRight,Film,HardDrive,Plus} from 'lucide-react';
import ProductionSteps,{activeStatuses,statusLabel} from './ProductionSteps.jsx';

const filters=[['all','Tất cả'],['active','Đang chạy'],['queued','Đang chờ'],['attention','Cần kiểm tra'],['completed','Hoàn tất']];
const match=(p,id)=>id==='all'||(id==='active'&&activeStatuses.has(p.status)&&p.status!=='queued')||(id==='queued'&&p.status==='queued')||(id==='attention'&&['failed','needs_attention'].includes(p.status))||(id==='completed'&&p.status==='completed');

export default function QueuePage({projects,health,open,onNew}){
 const [filter,setFilter]=useState('all');
 const queued=projects.filter(p=>p.status!=='draft');
 const visible=queued.filter(p=>match(p,filter));
 const free=Number(health?.disk_free_bytes);
 return <div className="ref-queue"><div className="page-heading ref-heading"><div><h1>Hàng đợi</h1><p>Theo dõi thứ tự chạy và mở từng dự án để xử lý lỗi.</p></div><button className="button-primary" onClick={onNew}><Plus size={16}/> Dự án mới</button></div>
  <div className="ref-queue-summary"><div><Film size={18}/><span>Đang xử lý</span><strong>{queued.filter(p=>activeStatuses.has(p.status)&&p.status!=='queued').length}</strong></div><div><span>Đang chờ</span><strong>{queued.filter(p=>p.status==='queued').length}</strong></div><div><span>Cần kiểm tra</span><strong>{queued.filter(p=>['failed','needs_attention'].includes(p.status)).length}</strong></div><div><HardDrive size={18}/><span>Ổ lưu trữ</span><strong>{Number.isFinite(free)?`${(free/1024**3).toFixed(1)} GB trống`:'Chưa có dữ liệu'}</strong></div></div>
  <div className="ref-filter-tabs ref-queue-tabs">{filters.map(([id,title])=><button key={id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{title} <span>{queued.filter(p=>match(p,id)).length}</span></button>)}</div>
  <section className="ref-panel ref-queue-list"><div className="ref-queue-head"><span>Dự án</span><span>Tiến trình</span><span>Trạng thái</span></div>{visible.length?visible.map((p,index)=><button className="ref-queue-row" key={p.id} onClick={()=>open(p)}><span className="ref-queue-name"><span className={`ref-film-art art-${index%5}`}><Film size={18}/></span><span><strong>{p.name}</strong><small>{p.locale} · {(Number(p.duration)/60).toFixed(1)} phút</small></span></span><span className="ref-queue-stage">{activeStatuses.has(p.status)?<><ProductionSteps status={p.status} progress={p.progress||0}/>{p.progress_detail?.message&&<small className="queue-progress-detail">{p.progress_detail.message}</small>}</>:p.error?<span className="ref-queue-error">{p.error}</span>:<span className={'status '+p.status}>{statusLabel[p.status]||p.status}</span>}</span><span className="ref-queue-result"><strong>{p.progress||0}%</strong><span className={'status '+p.status}>{statusLabel[p.status]||p.status}</span><ChevronRight size={16}/></span></button>):<div className="ref-empty-inline"><span>Không có bản xuất ở trạng thái này.</span><button onClick={onNew}>Tạo dự án mới</button></div>}</section>
 </div>;
}
