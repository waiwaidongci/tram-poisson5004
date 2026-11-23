import {feedback, field} from '../components/common/fields.js';
import {empty, panel} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, h, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

export async function inputs(route, refresh) {
  const {spec,datasets} = workspace;
  const selected = datasets.find(item => item.id === route.id) || datasets[0];
  const error = feedback();
  const sample = button('下载示例 CSV', {class:'quiet',onClick:event=>handler(sample,error,()=>workspace.download('/template',spec.sample_name))(event)});
  const outageSample = button('下载停测单示例', {class:'quiet',onClick:event=>handler(outageSample,error,()=>workspace.download('/outages-template',spec.outage_sample_name))(event)});
  const detail = selected && await workspace.getDataset(selected.id,route.offset);
  const columns = spec.fields.map(field => ({key:field.key,label:field.label}));
  const outageColumns = spec.outage_fields.map(field => ({key:field.key,label:field.label}));
  const preview = detail ? panel('批次明细', el('div',{class:'actions'},
    el('label',{for:'dataset-id',class:'sr'}, '选择数据批次'),
    el('select',{id:'dataset-id','aria-label':'选择数据批次',onChange:event=>{location.hash=`#inputs/${event.target.value}`;}},
      datasets.map(item=>el('option',{value:item.id,selected:item.id === selected.id}, item.name))),
    link('使用此批次运行',`#run/${detail.id}`,{class:'quiet'})),
    p(`${detail.filename} · ${detail.row_count} 行 · ${detail.outage_count} 条停测记录 · ${date(detail.created_at)}`,'filename'),
    table(columns,detail.rows,{caption:'批次明细',pageSize:16}),
    el('div',{class:'pagination'},
      route.offset > 0 && link('上一批明细',`#inputs/${detail.id}/${Math.max(0,route.offset-16)}`,{class:'quiet'}),
      p(`${detail.rows.length ? route.offset+1 : route.offset}–${route.offset+detail.rows.length} / ${detail.row_count}`),
      route.offset+16 < detail.row_count && link('下一批明细',`#inputs/${detail.id}/${route.offset+16}`,{class:'quiet'})),
    h(3,'信号台停测单'),
    detail.outages?.length ? table(outageColumns,detail.outages,{caption:'信号台停测单'})
      : p('本批次未导入停测单，全部窗口按有效观测处理。','subtle'))
    : empty('没有可用的批次。请导入示例或业务 CSV。');
  const submit = button('校验并导入', {type:'submit',class:'primary'});
  const upload = session.canWrite && el('form',{class:'fields',onSubmit:handler(submit,error,async event=>{
    const data = new FormData(event.target);
    const file = data.get('source');
    if (!file?.size) throw new Error('请选择一个 CSV 文件');
    if (file.size > 2_000_000) throw new Error('CSV 最多 2 MB');
    const notice = data.get('notices');
    if (notice?.size > 1_000_000) throw new Error('停测单 CSV 最多 1 MB');
    const item = await workspace.upload({name:data.get('batch_name'),filename:file.name,csv_text:await file.text(),
      outages_csv:notice?.size ? await notice.text() : ''});
    const target = `#inputs/${item.id}`;
    if (location.hash === target) await refresh();
    else location.hash = target;
  })},field({key:'batch_name',label:'批次名称',type:'string',max_length:120}),
    el('label',{class:'field',for:'source'}, el('span',{},'业务 CSV'),el('input',{id:'source',type:'file',name:'source',accept:'.csv,text/csv',required:true})),
    el('label',{class:'field',for:'notices'}, el('span',{},'信号台停测单 CSV（可空）'),el('input',{id:'notices',type:'file',name:'notices',accept:'.csv,text/csv'}),
      el('small',{},'停测窗会与逐窗观测对账并剔除，不计为零阻断。')), submit);
  return el('div',{class:'two-col'},el('div',{class:'wide-panel'},preview),el('aside',{class:'sidebar-panel'},
    panel('数据导入',p('观测与停测单一起入库并保留校验指纹；任一更新都会产生新版本，旧结论立即失效。','subtle'),sample,outageSample,upload,error),
    panel('字段说明',el('dl',{class:'dictionary'},spec.fields.map(item=>el('div',{},el('dt',{},item.label),
      el('dd',{},item.key,item.required === false ? ' · 可空' : ' · 必填',item.options ? ` · ${item.options.join(' / ')}` : ''))))),
    panel('停测单字段',el('dl',{class:'dictionary'},spec.outage_fields.map(item=>el('div',{},el('dt',{},item.label),
      el('dd',{},item.key,item.required === false ? ' · 可空' : ' · 必填',item.options ? ` · ${item.options.join(' / ')}` : ''))))))));
}
