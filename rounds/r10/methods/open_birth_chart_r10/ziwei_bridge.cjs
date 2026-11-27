/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Pinned Ziwei natal/cycle calculation and registered structural clauses.
 * JSON-lines protocol; no network, no outcomes. */
'use strict';
const path = require('node:path');
const readline = require('node:readline');
const iztro = process.env.OBS_NODE_MODULES ? require(path.join(process.env.OBS_NODE_MODULES,'iztro')) : require('iztro');
if (iztro.version !== '2.6.5') throw Error('iztro 2.6.5 is required');
const VERSION='OBS-R8-ZW-1.0';
const CONFIG={language:'zh-CN',yearDivide:'normal',horoscopeDivide:'normal',ageDivide:'normal',dayDivide:'forward',algorithm:'default',mutagens:{},brightness:{}};
const SHA=new Set(['擎羊','陀罗','火星','铃星','地空','地劫']);
const BENEFIC=new Set(['紫微','天府','文昌','文曲','左辅','右弼','天魁','天钺','禄存']);
const FAVORABLE_MAJOR=new Set(['紫微','天府','天同','太阳','太阴','天梁']);
const LONGEVITY=new Set(['紫微','天同','天梁','贪狼']);
const QISHA_RESCUE=new Set(['紫微','天相','禄存']);
const FOCUS=new Set(['命宫','疾厄']);
const chartCache=new Map();
const around=i=>[0,4,6,8].map(d=>(i+d)%12);
const pickStar=s=>Object.fromEntries(['name','type','scope','brightness','mutagen'].filter(k=>s[k]!==undefined).map(k=>[k,s[k]]));
const allStars=p=>[...p.majorStars,...p.minorStars,...p.adjectiveStars];
function parseBirth(row,shift){
  if (String(row.calendar||'gregorian').toLowerCase()!=='gregorian') throw Error('Gregorian source date required');
  const m=/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/.exec(row.birth_local||'');
  if(!m) throw Error('Complete source local date and clock required');
  const [y,mo,d,hh,mm,ss]=m.slice(1).map(x=>Number(x||0));
  const t=new Date(Date.UTC(y,mo-1,d,hh,mm,ss));
  if(y<1880||y>2025||t.getUTCFullYear()!==y||t.getUTCMonth()!==mo-1||t.getUTCDate()!==d||hh>23||mm>59||ss>59) throw Error('Invalid or out-of-scope date');
  if(typeof shift!=='number'||!Number.isFinite(shift)) throw Error('Invalid clock shift');
  const sex=row.sex||row.sex_resolved;
  if(!['M','F'].includes(sex)) throw Error('Recorded M/F required for traditional cycle direction');
  const shifted=new Date(t.getTime()+shift*60000);
  return {label:shifted.toISOString().slice(0,19),date:shifted.toISOString().slice(0,10),hour:shifted.getUTCHours(),sex,study_id:String(row.study_id||'')};
}
function natalJson(c){
  return {engine:VERSION,library_version:iztro.version,config:CONFIG,fix_leap:true,
    solar_date:c.solarDate,lunar_date:c.lunarDate,chinese_date:c.chineseDate,raw_lunar_date:c.rawDates.lunarDate,
    soul:c.soul,body:c.body,soul_branch:c.earthlyBranchOfSoulPalace,body_branch:c.earthlyBranchOfBodyPalace,five_elements_class:c.fiveElementsClass,
    palaces:c.palaces.map(p=>({index:p.index,name:p.name,is_body_palace:p.isBodyPalace,is_original_palace:p.isOriginalPalace,
      heavenly_stem:p.heavenlyStem,earthly_branch:p.earthlyBranch,major_stars:p.majorStars.map(pickStar),minor_stars:p.minorStars.map(pickStar),
      adjective_stars:p.adjectiveStars.map(pickStar),decadal:p.decadal,ages:p.ages,changsheng12:p.changsheng12,boshi12:p.boshi12,suiqian12:p.suiqian12,jiangqian12:p.jiangqian12})),
    complete_traditional_interpretation:false,death_probability:null};
}
function starLocations(c){
  const map=new Map();for(const p of c.palaces) for(const s of allStars(p)){if(!map.has(s.name))map.set(s.name,[]);map.get(s.name).push(p.index);}return map;
}
function scopeInfo(c,h,scope,locations){
  const s=h[scope];
  if(!s||!Number.isInteger(s.index)||s.index<0||s.index>11||!Array.isArray(s.palaceNames)||s.palaceNames.length!==12||!Array.isArray(s.mutagen)||s.mutagen.length!==4)
    return {status:'unavailable',scope};
  const focus=s.palaceNames.map((n,i)=>FOCUS.has(n)?i:-1).filter(i=>i>=0);
  if(focus.length!==2)throw Error('Scope life/health map is incomplete');
  const mapped=s.mutagen.map((name,i)=>({transformation:['禄','权','科','忌'][i],star:name,palaces:locations.get(name)||[]}));
  if(mapped.some(x=>x.palaces.length!==1))throw Error('Four-transformation target star is not uniquely located');
  const focusStars=focus.flatMap(i=>allStars(c.palaces[i]));
  const surround=[...new Set(focus.flatMap(around))];
  const surroundStars=surround.flatMap(i=>allStars(c.palaces[i]));
  const flowStars=focus.flatMap(i=>(s.stars||[])[i]||[]);
  const ji=mapped[3].palaces[0];
  return {scope,status:'computed',index:s.index,heavenly_stem:s.heavenlyStem,earthly_branch:s.earthlyBranch,palace_names:s.palaceNames,
    transformations:mapped,focus_indices:focus,ji_in_focus:focus.includes(ji),
    positive_transformations_in_focus:mapped.slice(0,3).filter(x=>focus.includes(x.palaces[0])).length,
    native_six_malefics_in_focus:focusStars.filter(x=>SHA.has(x.name)).map(x=>x.name),
    native_benefics_in_focus:focusStars.filter(x=>BENEFIC.has(x.name)).map(x=>x.name),
    fallen_majors_in_focus:focus.flatMap(i=>c.palaces[i].majorStars.filter(x=>x.brightness==='陷').map(x=>x.name)),
    native_six_malefics_in_surroundings:surroundStars.filter(x=>SHA.has(x.name)).map(x=>x.name),
    native_benefics_in_surroundings:surroundStars.filter(x=>BENEFIC.has(x.name)).map(x=>x.name),
    transit_stars_in_focus:flowStars.map(pickStar),all_transit_stars:(s.stars||[]).map(a=>a.map(pickStar)),
    nominal_age:s.nominalAge===undefined?null:s.nominalAge,net_fortune_verdict:null};
}
function clauses(c,h,locations,decadal,yearly){
  const natalLife=c.palaces.find(p=>p.name==='命宫');
  const natalAround=around(natalLife.index);
  const dpal=c.palaces[decadal.index];
  const dmaj=dpal.majorStars;
  const dnative=allStars(dpal);
  const dsha=dnative.filter(s=>SHA.has(s.name));
  const dji=decadal.transformations[3].palaces[0]===decadal.index;
  const dtrans=((h.decadal.stars||[])[decadal.index]||[]).filter(s=>s.type==='tough');
  const ytrans=((h.yearly.stars||[])[yearly.index]||[]).filter(s=>s.type==='tough');
  const ynative=allStars(c.palaces[yearly.index]).filter(s=>SHA.has(s.name));
  const ap=(h.age&&Number.isInteger(h.age.index)&&h.age.index>=0&&h.age.index<12)?c.palaces[h.age.index]:null;
  const aminor=ap?allStars(ap).filter(s=>SHA.has(s.name)):null;
  const longRescue=allStars(natalLife).filter(s=>LONGEVITY.has(s.name)).map(s=>s.name);
  const supportive=dmaj.length>0&&dmaj.every(s=>FAVORABLE_MAJOR.has(s.name)&&['庙','旺'].includes(s.brightness))&&dsha.length===0&&!dji&&dtrans.length===0;
  const adversePremise=dmaj.some(s=>s.brightness==='陷')&&(dsha.length+dtrans.length>0||dji)&&(ytrans.length+ynative.length>0)&&aminor!==null&&aminor.length>0;
  const qishaLoc=(locations.get('七杀')||[]).find(i=>natalAround.includes(i));
  const flowYT=natalAround.flatMap(i=>((h.yearly.stars||[])[i]||[]).filter(s=>['流羊','流陀'].includes(s.name)).map(s=>({palace:i,star:s.name})));
  const qisha=qishaLoc===undefined?null:allStars(c.palaces[qishaLoc]).find(s=>s.name==='七杀');
  const qrescue=qishaLoc===undefined?[]:around(qishaLoc).flatMap(i=>allStars(c.palaces[i]).filter(s=>QISHA_RESCUE.has(s.name)).map(s=>({palace:i,star:s.name})));
  const duplicate=[];
  for(const i of natalAround)for(const [native,flow]of [['擎羊','流羊'],['陀罗','流陀']]){
    if(allStars(c.palaces[i]).some(s=>s.name===native)&&((h.yearly.stars||[])[i]||[]).some(s=>s.name===flow))duplicate.push({palace:i,natal:native,yearly:flow});
  }
  const qiMatch=qisha!==null&&flowYT.length>0;
  const lifeContexts=[decadal,yearly].map(s=>{
    const stars=allStars(c.palaces[s.index]);
    return {scope:s.scope,index:s.index,
      adverse:stars.some(x=>SHA.has(x.name))||s.transformations[3].palaces[0]===s.index,
      supportive:stars.some(x=>BENEFIC.has(x.name))||s.transformations.slice(0,3).some(x=>x.palaces.includes(s.index))};
  });
  const mixed=lifeContexts.some(s=>s.adverse&&s.supportive);
  return {version:'OBS-R8-ZW-CLAUSES-1.0',source:'Ziwei Doushu Quanshu, volume 3',clauses:[
    {rule:'ZWC01',classification:'supportive_decadal_palace_premises',structural_match:supportive,unresolved:['All textual fortune claims remain unvalidated']},
    {rule:'ZWC02',classification:'multi_cycle_adverse_premises',structural_match:adversePremise,longevity_star_rescue_in_natal_life:longRescue,unresolved:['Effective rescue hierarchy','Full month/day timing not tested']},
    {rule:'ZWC03',classification:'qisha_repetition_with_transit_yang_tuo',structural_match:qiMatch,qisha_brightness:qisha?qisha.brightness:null,temple_mitigation:qisha?['庙','旺'].includes(qisha.brightness):false,rescue_context:qrescue,unresolved:['Many beneficial stars has no unique numeric threshold']},
    {rule:'ZWC04',classification:'yang_tuo_duplicate',structural_match:duplicate.length>0,duplicate_locations:duplicate,unresolved:['Net fortune after other clauses']},
    {rule:'ZWC05',classification:'mixed_support_and_adversity',structural_match:mixed,life_palace_contexts:lifeContexts,unresolved:['No numeric cancellation imposed']}
  ],minor_age_palace_available:ap!==null,complete_traditional_interpretation:false,net_fortune_verdict:null};
}
function evaluate(request){
  const row=request.row||request;
  const years=request.years||[];
  const shift=request.shift_minutes||0;
  try{
    const input=parseBirth(row,shift);
    const timeIndex=Math.floor((input.hour+1)/2);
    const key=[input.date,timeIndex,input.sex].join('|');
    let cached=chartCache.get(key);
    if(!cached){
      const chart=iztro.astro.withOptions({type:'solar',dateStr:input.date,timeIndex,gender:input.sex==='M'?'男':'女',fixLeap:true,language:'zh-CN',config:CONFIG});
      cached={chart,locations:starLocations(chart)};
      if(chartCache.size>=512)chartCache.delete(chartCache.keys().next().value);
      chartCache.set(key,cached);
    }
    const c=cached.chart;
    if(c.palaces.length!==12||c.palaces.reduce((n,p)=>n+p.majorStars.length,0)!==14)throw Error('Incomplete natal palace/major-star chart');
    const locations=cached.locations;
    const annual=years.map(year=>{
      if(!Number.isInteger(year)||year<1880||year>2200)throw Error('Unsupported snapshot year');
      const snapshot=`${year}-07-01`;
      if(snapshot<input.date)return {year,status:'before_birth',score:null};
      const h=c.horoscope(snapshot,6);
      const d=scopeInfo(c,h,'decadal',locations),y=scopeInfo(c,h,'yearly',locations);
      if(d.status!=='computed'||y.status!=='computed')return {year,status:'outside_registered_decadal_interval',score:null};
      const interp=clauses(c,h,locations,d,y);
      const result={year,status:'computed_for_registered_conventions',score:(Number(d.ji_in_focus)+Number(y.ji_in_focus))/2,
        score_name:'hua_ji_focus_mean',score_is_event_probability:false,decadal_index:d.index,yearly_index:y.index,
        yearly_ji_in_focus:y.ji_in_focus,decadal_ji_in_focus:d.ji_in_focus,
        matched_interpretive_rules:interp.clauses.filter(r=>r.structural_match).map(r=>r.rule),death_probability:null};
      if(request.detailed){result.snapshot_local=snapshot+'T12:00:00';result.decadal=d;result.yearly=y;result.interpretive_clauses=interp;result.other_cycles={age:h.age,monthly:h.monthly,daily:h.daily,hourly:h.hourly};}
      return result;
    });
    const out={study_id:input.study_id,engine:VERSION,status:'computed_for_registered_conventions',birth_clock_label:input.label,time_index:timeIndex,annual};
    if(request.include_chart)out.chart=natalJson(c);
    return out;
  }catch(e){return {study_id:String(row.study_id||''),engine:VERSION,status:'abstain',reason:e.message,annual:years.map(year=>({year,status:'abstain',score:null}))};}
}
module.exports={evaluate,parseBirth,scopeInfo,clauses,CONFIG,VERSION};
if(require.main===module){
  const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  input.on('line',line=>{
    if(!line.trim())return;
    try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(line)))+'\n');}
    catch(e){process.stdout.write(JSON.stringify({status:'protocol_error',reason:e.message})+'\n');}
  });
}
