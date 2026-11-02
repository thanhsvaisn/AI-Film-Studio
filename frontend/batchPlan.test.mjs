import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {planBatch} from './batchPlan.js';

const file=(name)=>({name,size:10,webkitRelativePath:''});
const channels=[
 {id:'th1',locale:'th-TH',youtube_channel_id:'YT_TH1'},
 {id:'th2',locale:'th-TH',youtube_channel_id:'YT_TH2'},
 {id:'id1',locale:'id-ID',youtube_channel_id:'YT_ID1'},
 {id:'id2',locale:'id-ID',youtube_channel_id:'YT_ID2'},
];

test('one source for two Thai and two Indonesian channels renders only two masters',()=>{
 const files=[file('film.mp4'),file('film.th-TH.srt'),file('film.id-ID.srt')];
 const plan=planBatch(files,channels,channels.map(c=>c.id),{},'all-markets');
 assert.equal(plan.videoCount,1);
 assert.equal(plan.jobs.length,2);
 assert.deepEqual(plan.jobs.map(j=>j.channelIds),[['th1','th2'],['id1','id2']]);
 assert.deepEqual(plan.issues,[]);
});

test('ten sources across three locales create thirty masters, not one per channel',()=>{
 const extra={id:'vi1',locale:'vi-VN',youtube_channel_id:'YT_VI1'};
 const files=[];
 for(let i=1;i<=10;i++)files.push(file(`film${i}.mp4`),file(`film${i}.th-TH.srt`),file(`film${i}.id-ID.srt`),file(`film${i}.vi-VN.srt`));
 const plan=planBatch(files,[...channels,extra],[...channels.map(c=>c.id),'vi1'],{},'all-markets');
 assert.equal(plan.jobs.length,30);
 assert.equal(plan.issues.length,0);
});

test('per-channel mode requires an explicit assignment',()=>{
 const files=[file('film.mp4'),file('film.th-TH.srt')];
 assert.equal(planBatch(files,channels,['th1'],{},'per-channel').jobs.length,0);
 const plan=planBatch(files,channels,['th1'],{'film.mp4':'th1'},'per-channel');
 assert.equal(plan.jobs.length,1);
 assert.deepEqual(plan.jobs[0].channelIds,['th1']);
});
