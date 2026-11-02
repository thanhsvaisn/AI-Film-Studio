import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {pairBatch} from './batch.js';

const f=(name,size=1,relative=name)=>({name,size,webkitRelativePath:relative});
test('pairs 100 named videos and translated SRTs in natural order',()=>{
  const files=[];
  for(let i=1;i<=100;i++)files.push(f(`film${i}.mp4`,10),f(`film${i}.vi-VN.srt`,2));
  const result=pairBatch(files);
  assert.equal(result.pairs.length,100);
  assert.equal(result.issues.length,0);
  assert.equal(result.totalBytes,1200);
  assert.equal(result.pairs[1].name,'film2');
});
test('reports missing pairs and preserves folder identity',()=>{
  const result=pairBatch([f('same.mp4',10,'A/same.mp4'),f('same.srt',1,'A/same.srt'),
    f('same.mp4',10,'B/same.mp4'),f('orphan.srt',1,'B/orphan.srt')]);
  assert.equal(result.pairs.length,1);
  assert.equal(result.issues.length,2);
});
test('separate locale tracks do not appear as missing files for another locale',()=>{
  const files=[f('film.mp4',10),f('film.th-TH.srt'),f('film.id-ID.srt')];
  const thai=pairBatch(files,'th-TH'),indo=pairBatch(files,'id-ID');
  assert.equal(thai.pairs.length,1);
  assert.equal(indo.pairs.length,1);
  assert.deepEqual(thai.issues,[]);
  assert.deepEqual(indo.issues,[]);
});
test('a generic SRT is not reused across two target languages',()=>{
  const files=[f('film.mp4',10),f('film.srt')];
  assert.equal(pairBatch(files,'ja-JP',true).pairs.length,0);
  assert.equal(pairBatch(files,'ko-KR',true).pairs.length,0);
});
test('Spain and Mexico receive separate Spanish tracks',()=>{
  const files=[f('film.mp4',10),f('film.es-ES.srt'),f('film.es-MX.srt')];
  const spain=pairBatch(files,'es-ES',true),mexico=pairBatch(files,'es-MX',true);
  assert.equal(spain.pairs[0].subtitles.name,'film.es-ES.srt');
  assert.equal(mexico.pairs[0].subtitles.name,'film.es-MX.srt');
  assert.deepEqual(spain.issues,[]);
  assert.deepEqual(mexico.issues,[]);
});
