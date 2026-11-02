import React from 'react';
import {Check} from 'lucide-react';

export const activeStatuses=new Set(['queued','translation','tts','audio_mixing','qa','mux']);
export const statusLabel={draft:'Bản nháp',queued:'Đang chờ',translation:'Đang dịch',tts:'Tạo giọng đọc',audio_mixing:'Ghép âm',qa:'Kiểm tra',mux:'Xuất MP4',completed:'Hoàn tất',needs_attention:'Cần kiểm tra',failed:'Có lỗi',paused:'Tạm dừng',canceled:'Đã hủy'};
const stages=[['translation','Dịch'],['tts','Giọng đọc'],['audio_mixing','Ghép âm'],['qa','Kiểm tra'],['mux','Xuất MP4']];

export default function ProductionSteps({status,progress=0}){
 const position=stages.findIndex(([id])=>id===status);
 const complete=status==='completed';
 return <div className="ref-steps" aria-label={`Tiến độ: ${statusLabel[status]||status}, ${progress}%`}>{stages.map(([id,title],index)=>{
  const done=complete||(position>=0&&index<position);
  const current=index===position;
  return <span className={`ref-step ${done?'done':current?'current':''}`} key={id}><i/><small>{done&&<Check size={11}/>} {title}{current?` ${progress}%`:''}</small></span>;
 })}</div>;
}
