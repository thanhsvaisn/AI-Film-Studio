import React,{useEffect,useState} from 'react';

async function request(url,options={}){
 const response=await fetch(url,options);
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'YouTube không nhận yêu cầu. Kiểm tra lại thông tin.');
 return data;
}

function PublisherCard({row,onRefresh}){
 const [seo,setSeo]=useState(row.seo),[tags,setTags]=useState(row.seo.tags.join(', ')),[image,setImage]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const base=`/api/projects/${row.project_id}/youtube/${row.channel_id}`;
 const editable=!row.youtube_video_id&&!['uploading','setting_thumbnail','uploaded'].includes(row.status);
 async function saveDraft(){
  const data={...seo,tags:tags.split(',').map(x=>x.trim()).filter(Boolean)};
  await request(base+'/seo',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  setSeo(data);
 }
 async function perform(publish){setBusy(true);setError('');setMessage('');try{
  if(!row.youtube_video_id)await saveDraft();
  if(image){const body=new FormData();body.append('image',image);await request(base+'/thumbnail',{method:'POST',body});}
  if(publish){await request(base+'/publish',{method:'POST'});setMessage('Đã đưa video vào hàng đợi đăng YouTube.');}
  else setMessage('Đã lưu SEO và ảnh bìa.');
  await onRefresh();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 const state={draft:'Chưa đăng',uploading:`Đang tải ${row.progress||0}%`,setting_thumbnail:'Đang đặt ảnh bìa',uploaded:'Đã đăng',failed:'Có lỗi'}[row.status]||row.status;
 return <div className="ref-publisher-grid"><div className="ref-panel publisher-card"><div className="section-title"><h3>SEO cho {row.channel_name}</h3><span className={'status '+row.status}>{state}</span></div>
  {row.youtube_video_id&&<p><a href={`https://www.youtube.com/watch?v=${row.youtube_video_id}`} target="_blank" rel="noreferrer">Xem video trên YouTube ↗</a></p>}
  <div className="publisher-fields"><label>Tiêu đề · {seo.title.length}/100<input maxLength="100" disabled={!editable||busy} value={seo.title} onChange={e=>setSeo({...seo,title:e.target.value})}/></label>
  <label>Mô tả<textarea disabled={!editable||busy} value={seo.description} onChange={e=>setSeo({...seo,description:e.target.value})} rows="4" placeholder="Tóm tắt nội dung, lời mời đăng ký, liên kết liên quan…"/></label>
  <label>Thẻ tìm kiếm, ngăn cách bằng dấu phẩy<input disabled={!editable||busy} value={tags} onChange={e=>setTags(e.target.value)} placeholder="phim, phim ngắn, drama…"/></label>
  <div className="form-row"><label>Danh mục<select disabled={!editable||busy} value={seo.category_id} onChange={e=>setSeo({...seo,category_id:e.target.value})}><option value="24">Giải trí</option><option value="1">Phim & hoạt hình</option><option value="22">Con người & blog</option></select></label>
  <label>Chế độ hiển thị<select disabled={!editable||busy} value={seo.privacy} onChange={e=>setSeo({...seo,privacy:e.target.value})}><option value="private">Riêng tư</option><option value="unlisted">Không công khai</option><option value="public">Công khai</option></select></label></div>
  <label>Ảnh bìa PNG/JPEG, tối đa 50 MB<input type="file" accept="image/png,image/jpeg" disabled={row.status==='uploaded'||row.status==='uploading'||row.status==='setting_thumbnail'||busy} onChange={e=>setImage(e.target.files[0]||null)}/></label>
  <label className="checkbox"><input type="checkbox" disabled={!editable||busy} checked={seo.made_for_kids} onChange={e=>setSeo({...seo,made_for_kids:e.target.checked})}/>Nội dung dành cho trẻ em</label>
  <label className="checkbox"><input type="checkbox" disabled={!editable||busy} checked={seo.synthetic_media} onChange={e=>setSeo({...seo,synthetic_media:e.target.checked})}/>Có nội dung AI/biến đổi trông như thật</label></div>
  <p className="note">SEO và ảnh bìa lưu riêng cho kênh này.</p>
  {row.error&&<p className="error">{row.error}</p>}{error&&<p className="error">{error}</p>}{message&&<p role="status">{message}</p>}
  <div className="actions"><button disabled={!editable||busy} onClick={()=>perform(false)}>Lưu SEO</button><button className="primary" disabled={row.status==='uploaded'||row.status==='uploading'||row.status==='setting_thumbnail'||busy||!row.completed||!row.proxy_enabled||!row.upload_scope_granted||(!row.youtube_video_id&&!seo.title.trim())} onClick={()=>perform(true)}>{row.youtube_video_id?'Thử lại ảnh bìa':row.status==='failed'?'Thử đăng lại':'Đăng video qua proxy'}</button></div>
 </div><aside className="ref-publisher-side"><section className="ref-panel ref-publisher-preview"><h3>Xem trước trên YouTube</h3><div className="ref-publisher-art"><span>{row.project_name?.slice(0,1)||'▶'}</span></div><strong>{seo.title||'Chưa đặt tiêu đề'}</strong><small>{row.channel_name}</small></section><section className="ref-panel ref-publisher-status"><div className="section-title"><h3>Trạng thái đăng</h3><span className={'status '+row.status}>{state}</span></div><strong>{row.progress||0}%</strong><progress max="100" value={row.progress||0}/><p>{row.status==='uploaded'?'Video đã đăng thành công.':row.status==='uploading'?'Đang tải video lên YouTube.':'Video sẽ được đăng khi bản MP4 hoàn tất và kênh sẵn sàng.'}</p><ul><li>{row.completed?'✓':'○'} Bản xuất MP4</li><li>{row.upload_scope_granted?'✓':'○'} Quyền đăng video</li><li>{row.proxy_enabled?'✓':'○'} Proxy của kênh</li><li>{seo.title.trim()?'✓':'○'} Tiêu đề SEO</li></ul><small>Proxy: {row.proxy_enabled?row.proxy_display:'Chưa đặt'}</small></section></aside></div>;
}

export default function YouTubePublisher({project}){
 const [rows,setRows]=useState([]),[error,setError]=useState(''),[currentId,setCurrentId]=useState('');
 async function refresh(){try{setRows(await request(`/api/projects/${project.id}/youtube`));setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{refresh();const timer=setInterval(refresh,3000);return()=>clearInterval(timer)},[project.id]);
 if(!project.channel_ids?.length)return <div className="ref-panel ref-empty-state"><h2>Chưa chọn kênh nhận</h2><p>Dự án này chưa có kênh YouTube để đăng.</p></div>;
 const current=rows.find(r=>r.channel_id===currentId)||rows[0];
 return <div className="ref-publisher-page"><div className="ref-heading"><div><h1>Đăng lên YouTube</h1><p>Một MP4 cho nhiều kênh. SEO, ảnh bìa và trạng thái đăng được lưu riêng cho từng kênh.</p></div>{project.status==='completed'&&<a className="button-secondary" href={`/api/projects/${project.id}/files/video`}>Tải video.mp4</a>}</div>{error&&<p className="error">{error}</p>}<div className="ref-publisher-channels">{rows.map(row=><button key={row.channel_id} className={current?.channel_id===row.channel_id?'selected':''} onClick={()=>setCurrentId(row.channel_id)}><span className="ref-channel-avatar">{row.channel_name?.slice(0,1)||'Y'}</span><span><strong>{row.channel_name}</strong><small>{project.locale}</small></span><span className={'status '+row.status}>{row.status==='uploaded'?'Đã đăng':row.status==='uploading'?`Đang tải ${row.progress||0}%`:'Chưa đăng'}</span></button>)}</div>{current&&<PublisherCard key={current.channel_id} row={current} onRefresh={refresh}/>}</div>;
}
