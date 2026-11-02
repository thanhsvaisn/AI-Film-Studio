import React,{useState} from 'react';

export default function ProxyEditor({channel,onSaved}){
 const [url,setUrl]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 async function save(e){e.preventDefault();setBusy(true);setMessage('');try{
  const r=await fetch(`/api/youtube/channels/${channel.id}/proxy`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  const data=await r.json();if(!r.ok)throw Error(data.detail||'Không lưu được proxy.');
  setUrl('');setMessage(data.proxy_enabled?'Đã lưu proxy.':'Đã bỏ proxy.');onSaved();
 }catch(e){setMessage(e.message)}finally{setBusy(false)}}
 async function test(){setBusy(true);setMessage('');try{
  const r=await fetch(`/api/youtube/channels/${channel.id}/proxy/test`,{method:'POST'});
  const data=await r.json();if(!r.ok)throw Error(data.detail||'Proxy chưa hoạt động.');
  setMessage(`Proxy kết nối được kênh ${data.channel}.`);
 }catch(e){setMessage(e.message)}finally{setBusy(false)}}
 return <div className="proxy-editor"><form onSubmit={save}><label>Proxy của kênh · {channel.proxy_display||'chưa đặt'}<input value={url} onChange={e=>setUrl(e.target.value)} type="password" autoComplete="off" placeholder="http://user:pass@host:port hoặc socks5://…"/></label><button disabled={busy} type="submit">{url?'Lưu proxy':'Bỏ proxy'}</button><button disabled={busy||!channel.proxy_enabled} type="button" onClick={test}>Thử kết nối</button></form>{message&&<p role="status">{message}</p>}</div>;
}
