import {chromium} from 'playwright';

const base='http://127.0.0.1:8765';
const projects=[
 {id:'one',name:'Trùng sinh năm 1998, tập 12',locale:'th-TH',duration:522,status:'tts',progress:63,audio_mode:'voxcpm',channel_ids:['thai-1'],warnings:[],segments:[{id:1,start:0,end:3,text:'Xin chào'},{id:2,start:3,end:6,text:'Mời vào'}]},
 {id:'two',name:'Hoàng hậu xuyên không, tập 3',locale:'id-ID',duration:665,status:'audio_mixing',progress:82,audio_mode:'voxcpm',channel_ids:['indo-1'],warnings:[],segments:[]},
 {id:'three',name:'Đêm trước ngày lên sàn, tập 5',locale:'vi-VN',duration:620,status:'needs_attention',progress:41,audio_mode:'approved',channel_ids:[],warnings:['Dòng 41 cần rút ngắn'],error:'Dòng 41 cần rút ngắn',segments:[]},
 {id:'four',name:'Ván cờ cuối cùng, tập 8',locale:'vi-VN',duration:552,status:'completed',progress:100,audio_mode:'voxcpm',channel_ids:['thai-1'],warnings:[],segments:[]},
];
let channels=[{id:'thai-1',name:'Drama Thai Daily',country:'Thái Lan',locale:'th-TH',configured:true,youtube_channel_id:'UCSAMPLE1'},{id:'indo-1',name:'Drama Indo Pagi',country:'Indonesia',locale:'id-ID',configured:true,youtube_channel_id:'UCSAMPLE2'}];
const health={tts:{installed:true,model_ready:true},ffmpeg:true,ffprobe:true,disk_free_bytes:500_000_000_000,delivery_root:'F:\\Tools\\Deliveries'};
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/api/**',route=>{
 const path=new URL(route.request().url()).pathname;
 let body={};
 if(path==='/api/projects')body=projects;
 else if(path==='/api/health')body=health;
 else if(path==='/api/channels')body=channels;
 else if(path==='/api/channels/thai-1'&&route.request().method()==='PUT'){const updated={...channels[0],...JSON.parse(route.request().postData()||'{}')};channels=[updated,...channels.slice(1)];body=updated;}
 else if(/^\/api\/projects\/(one|two|three|four)$/.test(path))body=projects.find(p=>p.id===path.split('/').at(-1));
 else if(path==='/api/youtube/status')body={configured:true,public_api_key_configured:true,redirect_uri:'http://127.0.0.1:8765/api/youtube/callback'};
 else if(path==='/api/projects/four/youtube')body=[{project_id:'four',channel_id:'thai-1',channel_name:'Drama Thai Daily',status:'draft',completed:true,proxy_enabled:true,proxy_display:'socks5://proxy.example:1080',upload_scope_granted:true,seo:{title:'Ván cờ cuối cùng',description:'',tags:[],category_id:'24',privacy:'private',made_for_kids:false,synthetic_media:false}}];
 else if(path.endsWith('/youtube'))body=[];
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
});
await page.goto(base);
await page.getByRole('heading',{name:'Tổng quan'}).waitFor();
await page.locator('.ref-production-row').first().waitFor();
await page.screenshot({path:'../preview-reference-dashboard.png',fullPage:true});
await page.getByRole('button',{name:'Nhập hàng loạt'}).click();
await page.getByRole('heading',{name:'Nhập hàng loạt'}).waitFor();
await page.screenshot({path:'../preview-reference-batch.png',fullPage:true});
await page.getByRole('button',{name:'Đóng'}).click();
await page.getByRole('button',{name:'Dự án',exact:true}).click();
await page.getByRole('heading',{name:'Dự án',exact:true}).waitFor();
await page.locator('.ref-project-card').first().waitFor();
await page.screenshot({path:'../preview-reference-projects.png',fullPage:true});
await page.locator('.ref-project-card').first().click();
await page.locator('.ref-line-editor').waitFor();
await page.screenshot({path:'../preview-reference-studio.png',fullPage:true});
await page.getByRole('button',{name:/Hàng đợi/}).click();
await page.getByRole('heading',{name:'Hàng đợi',exact:true}).waitFor();
await page.getByRole('button',{name:'Kênh YouTube',exact:true}).click();
await page.getByRole('heading',{name:'Kênh YouTube'}).waitFor();
await page.screenshot({path:'../preview-reference-channels.png',fullPage:true});
await page.getByRole('button',{name:'Cấu hình',exact:true}).last().click();
await page.getByRole('button',{name:'Mở cấu hình kênh'}).click();
await page.getByRole('combobox',{name:'Quốc gia'}).selectOption('Indonesia');
await page.getByRole('button',{name:'Lưu cấu hình'}).click();
await page.getByText('Đã lưu cấu hình kênh.').waitFor();
await page.getByRole('button',{name:'Tổng quan',exact:true}).click();
await page.getByRole('button',{name:/Ván cờ cuối cùng/}).first().click();
await page.getByRole('button',{name:'Đăng YouTube'}).click();
await page.getByRole('heading',{name:'SEO & đăng YouTube'}).waitFor();
await page.getByRole('button',{name:'Đăng video qua proxy'}).waitFor();
await page.setViewportSize({width:390,height:844});
await page.getByRole('button',{name:'Tổng quan',exact:true}).click();
if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile overflow');
await page.screenshot({path:'../preview-reference-mobile.png',fullPage:true});
if(errors.length)throw Error(errors.join('\n'));
console.log('Reference UI smoke passed: dashboard, batch, library, studio, queue, channel settings, YouTube SEO, mobile.');
await browser.close();
