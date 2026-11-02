import {localeOptions} from './locales.js';

const knownLocales = new Set(localeOptions.map(([code]) => code.toLowerCase()));

export function pairBatch(files, locale='vi-VN', requireTagged=false) {
  const videos = new Map(), subtitles = new Map(), issues = [];
  for (const file of files) {
    const path = (file.webkitRelativePath || file.name).replaceAll('\\', '/');
    const lower = path.toLowerCase();
    const isVideo = lower.endsWith('.mp4');
    const isSubtitle = lower.endsWith('.srt');
    if (!isVideo && !isSubtitle) continue;
    const stem = lower.slice(0, lower.lastIndexOf('.'));
    const map = isVideo ? videos : subtitles;
    if (map.has(stem)) issues.push(`Tệp trùng tên: ${path}`);
    else map.set(stem, {file, path});
  }
  const pairs = [];
  for (const [stem, video] of videos) {
    const srt = subtitles.get(stem + '.' + locale.toLowerCase()) || (!requireTagged && subtitles.get(stem));
    if (!srt) {
      issues.push(`Thiếu SRT đã dịch cho ${video.path}`);
      continue;
    }
    pairs.push({video: video.file, subtitles: srt.file, path: video.path,
      name: video.path.replaceAll('\\', '/').split('/').pop().replace(/\.mp4$/i, '')});
  }
  for (const [stem, srt] of subtitles) {
    const bare = stem.endsWith('.' + locale.toLowerCase()) ? stem.slice(0, -locale.length - 1) : stem;
    if (bare === stem && knownLocales.has(stem.split('.').pop())) continue;
    if (!videos.has(bare)) issues.push(`Thiếu MP4 cho ${srt.path}`);
  }
  pairs.sort((a,b)=>a.path.localeCompare(b.path, undefined, {numeric:true}));
  return {pairs, issues, totalBytes:pairs.reduce((sum,p)=>sum+p.video.size+p.subtitles.size,0)};
}
