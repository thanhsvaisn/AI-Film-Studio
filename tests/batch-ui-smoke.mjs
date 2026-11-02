import {chromium} from 'playwright';
import {readFileSync} from 'node:fs';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1365,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8765');
await page.getByRole('button',{name:/Nhập hàng loạt/}).click();
await page.locator('.batch-picker.secondary input').setInputFiles([
  {name:'film01.mp4',mimeType:'video/mp4',buffer:readFileSync('ai-film-studio/tool2/data/voice-fixture.mp4')},
  {name:'film01.vi-VN.srt',mimeType:'text/plain',buffer:Buffer.from('1\n00:00:00,500 --> 00:00:08,500\nXin chào, đây là giọng đọc mặc định.\n\n2\n00:00:10,000 --> 00:00:19,000\nHẹn gặp lại trong bộ phim tiếp theo.\n')}
]);
await page.getByText('1 video nguồn · 1 bản xuất').waitFor();
await page.getByRole('button',{name:'Đưa 1 bản vào hàng đợi'}).click();
await page.getByText('Đã đưa các bản hợp lệ vào hàng đợi.',{exact:false}).waitFor({timeout:30000});
const projects=await (await page.request.get('http://127.0.0.1:8765/api/projects')).json();
let project=projects.find(p=>p.source_filename==='film01.mp4'&&p.batch_id);
if(!project)throw Error('Batch project not persisted');
const deadline=Date.now()+180000;
while(Date.now()<deadline&&project.status!=='completed'&&project.status!=='failed'){
  await page.waitForTimeout(2000);
  project=await (await page.request.get(`http://127.0.0.1:8765/api/projects/${project.id}`)).json();
}
if(project.status!=='completed')throw Error(JSON.stringify(project));
if(!project.report?.delivery_folder)throw Error('Batch delivery folder missing');
for(const file of ['video.mp4','subtitles.srt','report.json'])
  if(!(await import('node:fs')).existsSync(`${project.report.delivery_folder}/${file}`))throw Error(`Missing delivery ${file}`);
if(errors.length)throw Error(errors.join('\n'));
console.log('Batch UI upload passed');
await browser.close();
