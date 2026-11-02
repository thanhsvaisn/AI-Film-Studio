import {pairBatch} from './batch.js';

export function planBatch(files, channels, selectedIds, assignment, mode='per-channel') {
  const chosen=channels.filter(c=>selectedIds.includes(c.id) && c.youtube_channel_id);
  const videos=files.filter(f=>f.name.toLowerCase().endsWith('.mp4'));
  const paths=videos.map(f=>(f.webkitRelativePath||f.name).replaceAll('\\','/'));
  const locales=[...new Set(chosen.map(c=>c.locale))];
  const paired=new Map(locales.map(locale=>[locale,pairBatch(files,locale,locales.length>1)]));
  const jobs=[], issues=[];
  for(const path of paths){
    const targets=mode==='per-channel' ? chosen.filter(c=>c.id===assignment[path]) : chosen;
    if(!targets.length){issues.push(`${path}: chưa chọn kênh`);continue;}
    for(const locale of [...new Set(targets.map(c=>c.locale))]){
      const pair=paired.get(locale).pairs.find(p=>p.path===path);
      if(!pair){issues.push(`${path}: thiếu SRT cho ${locale}`);continue;}
      jobs.push({...pair,locale,channelIds:targets.filter(c=>c.locale===locale).map(c=>c.id)});
    }
  }
  return {jobs,issues,videoCount:paths.length,totalBytes:jobs.reduce((n,j)=>n+j.video.size+j.subtitles.size,0)};
}
