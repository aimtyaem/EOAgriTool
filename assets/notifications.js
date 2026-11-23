/* Build notifications only from data actually returned by the app APIs and field storage. */
(() => {
  const $ = id => document.getElementById(id);
  const stateKey = 'eoagri-notification-state-v1';
  const regions = {nile_delta:'Nile Delta',sahel:'Sahel',mediterranean:'Mediterranean',southeast_asia:'SE Asia'};
  let alerts = [];
  let loading = false;

  function loadState(){return EOAgri.read(stateKey,{read:[],dismissed:[]})||{read:[],dismissed:[]};}
  function saveState(state){EOAgri.write(stateKey,state);}
  function number(value){const n=Number(value);return Number.isFinite(n)?n:null;}
  function round(value,digits=1){return Number(value).toFixed(digits);}
  function sourceHref(category){return EOAgri.pageUrl(category==='fields'?'fields':category==='water'?'water':'climate');}
  function addAlert(list,alert){list.push({...alert,id:`${alert.category}:${alert.rule}:${alert.region||'farm'}`});}

  function buildAlerts(climateResult,waterResult,fields,region,horizon){
    const list=[];
    if(climateResult.ok&&climateResult.data){
      const data=climateResult.data,temps=(data.temperature||[]).map(number).filter(v=>v!==null),rains=(data.rainfall||[]).map(number).filter(v=>v!==null),winds=(data.wind||[]).map(number).filter(v=>v!==null);
      const tempMax=temps.length?Math.max(...temps):null,windMax=winds.length?Math.max(...winds):null,rainTotal=rains.length?rains.reduce((sum,v)=>sum+v,0):null;
      if(tempMax!==null&&tempMax>=35)addAlert(list,{category:'climate',priority:'critical',rule:'heat',title:'High-temperature stress in forecast',description:`Forecast temperatures reach ${round(tempMax)}°C during the selected ${horizon} outlook for ${regions[region]||region}. Review crop-specific heat precautions.`,source:`Open-Meteo forecast · ${regions[region]||region} · ${climateResult.stale?'stale reading':'refreshed '+EOAgri.formatRefreshedAt(climateResult.fetched_at)}`,region});
      if(rainTotal!==null&&rains.length&&rainTotal<=0.5)addAlert(list,{category:'climate',priority:'warning',rule:'low-rain',title:'Very low rainfall in forecast',description:`The available forecast totals ${round(rainTotal)} mm of precipitation over ${rains.length} hourly readings (${horizon}) for ${regions[region]||region}. Check field conditions before changing irrigation plans.`,source:`Open-Meteo forecast · ${regions[region]||region} · ${climateResult.stale?'stale reading':'refreshed '+EOAgri.formatRefreshedAt(climateResult.fetched_at)}`,region});
      if(windMax!==null&&windMax>=10)addAlert(list,{category:'climate',priority:'warning',rule:'wind',title:'High wind in forecast',description:`Forecast wind reaches ${round(windMax)} m/s in the selected ${horizon} outlook. Consider local conditions when scheduling spraying or irrigation.`,source:`Open-Meteo forecast · ${regions[region]||region} · ${climateResult.stale?'stale reading':'refreshed '+EOAgri.formatRefreshedAt(climateResult.fetched_at)}`,region});
      if(data.stale||climateResult.stale)addAlert(list,{category:'data',priority:'warning',rule:'climate-stale',title:'Climate data may be out of date',description:`The climate endpoint returned a cached/stale reading (${EOAgri.formatRefreshedAt(climateResult.fetched_at)}). Treat forecast alerts as advisory until a fresh reading is available.`,source:'Climate data status',region});
    }else addAlert(list,{category:'data',priority:'info',rule:'climate-unavailable',title:'Climate data unavailable',description:`No climate forecast was returned for ${regions[region]||region}. Climate alerts are not simulated without source data. Use Refresh data to try again.`,source:climateResult.error||'Climate endpoint unavailable',region});

    if(waterResult.ok&&waterResult.data){
      const data=waterResult.data,deficit=number(data.irrigation_deficit_mm),soil=number(data.soil_moisture_avg),rain=number(data.rain_total_mm),et0=number(data.et0_total_mm);
      if(deficit!==null&&deficit>30)addAlert(list,{category:'water',priority:'warning',rule:'deficit',title:'Elevated irrigation deficit indicator',description:`The reported 7-day ET₀-minus-rainfall indicator is ${round(deficit)} mm (ET₀ ${et0===null?'unavailable':round(et0)+' mm'}; rainfall ${rain===null?'unavailable':round(rain)+' mm'}). This is a regional proxy, not a crop-specific irrigation prescription.`,source:`Open-Meteo water data · ${regions[region]||region} · ${waterResult.stale?'stale reading':'refreshed '+EOAgri.formatRefreshedAt(waterResult.fetched_at)}`,region});
      if(data.stale||waterResult.stale)addAlert(list,{category:'data',priority:'warning',rule:'water-stale',title:'Water data may be out of date',description:`The water endpoint returned a cached/stale reading (${EOAgri.formatRefreshedAt(waterResult.fetched_at)}). Verify conditions before acting on the indicator.`,source:'Water data status',region});
      if(deficit===null&&soil===null&&rain===null&&et0===null)addAlert(list,{category:'data',priority:'info',rule:'water-incomplete',title:'Water metrics are incomplete',description:'The water endpoint responded, but did not include usable water balance values. No water-risk alert was inferred.',source:'Water data status',region});
    }else addAlert(list,{category:'data',priority:'info',rule:'water-unavailable',title:'Water data unavailable',description:`No water metrics were returned for ${regions[region]||region}. Water alerts are not simulated without source data. Use Refresh data to try again.`,source:waterResult.error||'Water endpoint unavailable',region});

    fields.forEach((field,index)=>{
      const name=String(field?.name||`Field ${index+1}`),health=String(field?.health||'').toLowerCase();
      if(health==='poor')addAlert(list,{category:'fields',priority:'warning',rule:`poor-health-${index}`,title:`Field health needs review: ${name}`,description:`The locally saved record marks ${name} (${field.crop||'crop not specified'}) as poor health. Review the field record and assess on site.`,source:'Locally stored field record',field:name});
      else if(health==='fair')addAlert(list,{category:'fields',priority:'info',rule:`fair-health-${index}`,title:`Monitor field condition: ${name}`,description:`The locally saved record marks ${name} (${field.crop||'crop not specified'}) as fair health. Recheck the field and update its record if conditions change.`,source:'Locally stored field record',field:name});
    });
    if(!fields.length)addAlert(list,{category:'fields',priority:'info',rule:'no-fields',title:'No fields are registered in this browser',description:'Add field records to include their recorded crop and health status in the notification center.',source:'Local field storage'});
    if(!list.length)addAlert(list,{category:'data',priority:'info',rule:'no-current-alerts',title:'No threshold alerts from the available readings',description:'The latest available sources did not meet the notification thresholds. This does not confirm field conditions; continue regular monitoring.',source:`Climate and water readings · ${regions[region]||region}`});
    return list;
  }

  function text(tag,className,value){const node=document.createElement(tag);if(className)node.className=className;node.textContent=value;return node;}
  function render(){
    const state=loadState(),category=$('categoryFilter').value,priority=$('priorityFilter').value;
    const visible=alerts.filter(item=>!state.dismissed.includes(item.id)&&(category==='all'||item.category===category)&&(priority==='all'||item.priority===priority));
    const active=alerts.filter(item=>!state.dismissed.includes(item.id));
    $('activeCount').textContent=active.filter(item=>item.rule!=='no-current-alerts').length;
    $('unreadCount').textContent=active.filter(item=>!state.read.includes(item.id)&&item.rule!=='no-current-alerts').length;
    $('fieldCount').textContent=EOAgri.fields().length;
    $('sourceCount').textContent=[...new Set(alerts.filter(item=>item.category!=='data').map(item=>item.category))].length;
    $('resultsLabel').textContent=`Showing ${visible.length} of ${active.length} active notifications`;
    const container=$('alertsList');container.replaceChildren();container.setAttribute('aria-busy',String(loading));
    if(!visible.length){const empty=text('div','alert-empty','');empty.append(text('strong','',active.length?'No notifications match these filters':'No active notifications'),document.createTextNode(active.length?'Try changing the selected filters.':'Refresh to check the latest available farm data.'));container.append(empty);return;}
    visible.forEach(item=>{
      const card=document.createElement('article');card.className=`alert-card${state.read.includes(item.id)?'':' is-unread'}`;card.dataset.priority=item.priority;
      card.append(text('span','alert-indicator',''));
      const content=text('div','alert-content',''),meta=text('div','alert-meta','');
      meta.append(text('span','alert-category',item.category==='data'?'Data status':item.category),text('span','alert-priority',item.priority));
      content.append(meta,text('h3','',item.title),text('p','',item.description),text('small','alert-source',item.source));
      if(['climate','water','fields'].includes(item.category)){const link=document.createElement('a');link.className='alert-link';link.href=sourceHref(item.category);link.textContent=`Open ${item.category} →`;content.append(link);}
      const actions=text('div','alert-controls',''),readButton=document.createElement('button'),dismissButton=document.createElement('button');
      readButton.type=dismissButton.type='button';readButton.textContent=state.read.includes(item.id)?'Mark unread':'Mark read';dismissButton.textContent='Dismiss';
      readButton.addEventListener('click',()=>{const current=loadState();current.read=current.read.includes(item.id)?current.read.filter(id=>id!==item.id):[...current.read,item.id];saveState(current);render();});
      dismissButton.addEventListener('click',()=>{const current=loadState();if(!current.dismissed.includes(item.id))current.dismissed.push(item.id);saveState(current);render();});
      actions.append(readButton,dismissButton);card.append(content,actions);container.append(card);
    });
  }

  async function refresh(){
    if(loading)return;loading=true;render();
    const region=$('regionSelect').value,horizon=$('horizonSelect').value,refreshButton=$('refreshAlerts'),freshness=$('alertsFreshness');
    refreshButton.disabled=true;refreshButton.innerHTML='<span class="spinner"></span> Refreshing';freshness.removeAttribute('data-kind');freshness.textContent='Checking climate and water sources and reading locally saved fields…';
    const [climateResult,waterResult]=await Promise.all([
      EOAgri.fetchJSON(`/climate_data?region=${encodeURIComponent(region)}&horizon=${encodeURIComponent(horizon)}`),
      EOAgri.fetchJSON(`/water_data?region=${encodeURIComponent(region)}`)
    ]);
    const fields=EOAgri.fields();alerts=buildAlerts(climateResult,waterResult,fields,region,horizon);
    const successes=[climateResult,waterResult].filter(result=>result.ok&&result.data).length;
    const stale=[climateResult,waterResult].some(result=>result.ok&&result.stale);
    if(successes===0){freshness.dataset.kind='error';freshness.textContent=`Live climate and water data could not be loaded. Field alerts use browser-local records only. ${climateResult.error||waterResult.error||'The API may be unavailable on this static hosting origin.'}`;}
    else if(stale){freshness.dataset.kind='stale';freshness.textContent=`${successes} live source${successes===1?'':'s'} returned data; at least one reading is stale. Review data-status alerts before acting.`;}
    else freshness.textContent=`Updated ${new Date().toLocaleString()} · ${successes} live source${successes===1?'':'s'} checked · ${fields.length} local field record${fields.length===1?'':'s'} read.`;
    loading=false;refreshButton.disabled=false;refreshButton.textContent='Refresh data';render();
  }

  document.addEventListener('DOMContentLoaded',()=>{
    ['categoryFilter','priorityFilter'].forEach(id=>$(id).addEventListener('change',render));
    ['regionSelect','horizonSelect'].forEach(id=>$(id).addEventListener('change',refresh));
    $('refreshAlerts').addEventListener('click',refresh);
    $('markAllRead').addEventListener('click',()=>{const state=loadState();state.read=[...new Set([...state.read,...alerts.map(item=>item.id)])];saveState(state);render();});
    $('clearDismissed').addEventListener('click',()=>{const state=loadState();state.dismissed=[];saveState(state);render();});
    window.addEventListener('eoagri:fields',()=>{alerts=buildAlerts({ok:false,error:'Field records changed; refresh live sources to update.'},{ok:false,error:'Field records changed; refresh live sources to update.'},EOAgri.fields(),$('regionSelect').value,$('horizonSelect').value);render();});
    window.addEventListener('storage',event=>{if(event.key==='fieldData'){alerts=buildAlerts({ok:false,error:'Field records changed in another tab.'},{ok:false,error:'Field records changed in another tab.'},EOAgri.fields(),$('regionSelect').value,$('horizonSelect').value);render();}});
    refresh();
  });
})();
