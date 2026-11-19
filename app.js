const PAGE_SIZE = 50;
let bikes = [];
let currentPage = 1;
const $ = id => document.getElementById(id);
const LINE_URL = $('lineAddFriend').href;
const money = n => Number.isFinite(Number(n)) && n !== null ? "NT$ " + Number(n).toLocaleString("zh-TW") : "價格請洽詢";
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function marketplaceUrl(value, origin) {
  try {
    const url = new URL(value);
    if (url.protocol === 'http:') url.protocol = 'https:';
    return url.origin === origin && !url.username && !url.password ? url.href : '';
  } catch {
    return '';
  }
}
const imageUrl = value => marketplaceUrl(value, 'https://cdn.store-assets.com');
const brandLabels = new Map([...$('brandFilter').options].map(option => [option.value, option.text]));
const filterIds = ['search', 'storeFilter', 'brandFilter', 'categoryFilter', 'warrantyFilter', 'sortFilter'];
const filterForm = $('filterForm');
const filterDrawer = $('filterDrawer');
const filterToggle = $('openFilters');
const readFilters = () => Object.fromEntries(filterIds.map(id => [id, $(id).value.trim()]));
const defaultFilters = readFilters();
let activeFilters = { ...defaultFilters };
function vehicleCategories(bike, brand, model) {
  if (Array.isArray(bike.categories) && bike.categories.length) return bike.categories;
  const groups = [];
  const cc = bike.cc;
  if (brand === 'GOGORO' || /\b(?:EC-?0[25]|EMOVING|IONEX|UR1|AI-?[134])\b|電動車/i.test(model)) {
    groups.push('electric');
  } else if (Number.isFinite(cc) && cc > 0) {
    groups.push(cc <= 50 ? 'green-50' : cc <= 125 ? 'up-to-125' : cc <= 150 ? '126-150' : cc < 250 ? '151-249' : 'heavy');
  }
  if (brand === 'VESPA') groups.push('vespa');
  return groups;
}
function setOptions(id, values, defaultLabel) {
  const el = $(id), old = el.value;
  el.replaceChildren(new Option(defaultLabel, ''));
  values.filter(Boolean).sort((a,b)=>a.localeCompare(b,'zh-Hant')).forEach(v => el.add(new Option(v,v)));
  if ([...el.options].some(o=>o.value===old)) el.value=old;
}
function updateFilters() {
  setOptions(
    'storeFilter',
    [...new Set(bikes.map(b => b.store))],
    '全部門市'
  );
}
function filtered() {
  const q = activeFilters.search.toLowerCase();
  const {storeFilter: store, brandFilter: brand, categoryFilter: category, warrantyFilter: warranty, sortFilter: sort} = activeFilters;
  const result = bikes.filter(b =>
    (!q || b.searchText.includes(q)) &&
    (!store || b.store === store) &&
    (!brand || b.brand === brand) &&
    (!category || b.categories.includes(category)) &&
    (!warranty || b.warrantyStatus === warranty)
  );
  if(sort==='low')result.sort((a,b)=>(a.price??Infinity)-(b.price??Infinity));
  if(sort==='high')result.sort((a,b)=>(b.price??-1)-(a.price??-1));
  return result;
}
function render(reset=false) {
  if(reset) currentPage=1;
  const result=filtered(), totalPages=Math.max(1,Math.ceil(result.length/PAGE_SIZE));
  currentPage=Math.min(currentPage,totalPages);
  const pageBikes=result.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
  $('resultCount').textContent=result.length;
  $('pageInfo').textContent=`第 ${currentPage} / ${result.length?totalPages:0} 頁 · 每頁最多 50 台`;
  $('empty').hidden = result.length > 0;
  $('cards').innerHTML=pageBikes.map(b=>{
    const image=imageUrl(b.image_url);
    const img=image?`<img src="${escapeHTML(image)}" alt="${escapeHTML(b.model)} 車輛照片" loading="lazy">`:'<div class="no-image">暫無照片</div>';
    return `<article class="bike-card" tabindex="0" role="button" data-id="${escapeHTML(b.id)}" aria-label="查看 ${escapeHTML(b.model)}">
    <div class="bike-img">${img}</div>
    <div class="card-body"><div class="store-name">${escapeHTML(b.store||'門市待確認')}</div><div class="card-title">${escapeHTML(b.original_name||b.model)}</div>
    <div class="specs"><span>${b.year??'年份未提供'} 年</span><span>編號 ${escapeHTML(b.stock_number||'未提供')}</span></div>
    <div class="price-row"><div class="price">${money(b.price)}</div><span class="details-link">查看車輛 ↗</span></div></div></article>`;
  }).join('');
  $('cards').querySelectorAll('.bike-card').forEach(el=>{el.addEventListener('click',()=>openDetail(el.dataset.id));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openDetail(el.dataset.id)}})});
  renderPages(totalPages,result.length);
}
function renderPages(total,count) {
  const holder=$('pagination');holder.replaceChildren();if(count<=PAGE_SIZE)return;
  function btn(label,page,disabled=false,active=false) {
    const el=document.createElement('button');el.textContent=label;el.disabled=disabled;el.className=active?'active':'';
    el.addEventListener('click',()=>{currentPage=page;render();$('inventory').scrollIntoView();});holder.appendChild(el);
  }
  btn('上一頁',currentPage-1,currentPage===1);
  const candidates=new Set([1,total,currentPage-2,currentPage-1,currentPage,currentPage+1,currentPage+2]);
  let prev=0;
  [...candidates].filter(n=>n>=1&&n<=total).sort((a,b)=>a-b).forEach(n=>{if(n-prev>1){const s=document.createElement('span');s.textContent='…';holder.appendChild(s)}btn(String(n),n,false,n===currentPage);prev=n});
  btn('下一頁',currentPage+1,currentPage===total);
}
function openDetail(id) {
  const b=bikes.find(x=>x.id===id);if(!b)return;
  const image=imageUrl(b.image_url);
  $('modalContent').innerHTML=`<div class="modal-photo">${image?`<img src="${escapeHTML(image)}" alt="${escapeHTML(b.model)}">`:'<div class="no-image">暫無照片</div>'}</div>
  <div class="modal-info"><div class="eyebrow">${escapeHTML(b.store||'門市待確認')}</div><h2 id="modalTitle">${escapeHTML(b.original_name||b.model)}</h2>
  <div class="price">${money(b.price)}</div><div class="detail-grid"><div class="detail-cell"><small>年份</small><strong>${b.year??'未提供'}</strong></div><div class="detail-cell"><small>車輛編號</small><strong>${escapeHTML(b.stock_number||'未提供')}</strong></div><div class="detail-cell"><small>門市</small><strong>${escapeHTML(b.store||'待確認')}</strong></div><div class="detail-cell"><small>里程／保固</small><strong>請洽阿人車庫</strong></div></div>
  <p>車況、里程、保固及實際庫存，歡迎透過 LINE 向阿人車庫確認。</p>
  <a class="line-btn line-action" href="${escapeHTML(LINE_URL)}" target="_blank" rel="noopener noreferrer">透過 LINE 詢問 ↗</a></div>`;
  $('modal').classList.add('open');
  document.body.classList.add('modal-lock');
}
function closeModal() {
  $('modal').classList.remove('open');
  document.body.classList.remove('modal-lock');
}
function showMissingImage(event) {
  if (!(event.target instanceof HTMLImageElement)) return;
  const empty = document.createElement('div');
  empty.className = 'no-image';
  empty.textContent = '暫無照片';
  event.target.replaceWith(empty);
}
$('cards').addEventListener('error', showMissingImage, true);
$('modalContent').addEventListener('error', showMissingImage, true);
$('closeModal').addEventListener('click',closeModal);
$('modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && $('modal').classList.contains('open')) closeModal();
});

function applyFilters() {
  activeFilters = readFilters();
  const hasFilters = filterIds.some(id => activeFilters[id] !== defaultFilters[id]);
  filterToggle.classList.toggle('has-filters', hasFilters);
  filterToggle.setAttribute('aria-label', hasFilters ? '篩選車款，已套用條件' : '篩選車款');
  render(true);
  $('inventory').scrollIntoView();
}
filterToggle.addEventListener('click', () => {
  for (const id of filterIds) $(id).value = activeFilters[id];
  filterDrawer.showModal();
  filterToggle.setAttribute('aria-expanded', 'true');
});
$('closeFilters').addEventListener('click', () => filterDrawer.close());
$('search').addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  event.preventDefault();
  filterDrawer.close();
});
filterDrawer.addEventListener('click', event => {
  if (event.target === filterDrawer && event.clientX < filterDrawer.getBoundingClientRect().left) filterDrawer.close();
});
filterDrawer.addEventListener('close', () => {
  filterToggle.setAttribute('aria-expanded', 'false');
  filterToggle.focus({ preventScroll: true });
});
filterForm.addEventListener('submit', event => {
  event.preventDefault();
  filterDrawer.close();
  applyFilters();
});
$('resetBtn').addEventListener('click', () => {
  filterForm.reset();
  applyFilters();
});
async function loadVehicles() {
  try {
    const response=await fetch('./vehicles.json?ts='+Date.now(),{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if(!Array.isArray(data))throw new Error('資料格式錯誤');
    bikes = data.map((b, i) => {
      const model = String(b.model || '');
      const name = String(b.original_name || model);
      const store = String(b.store || '門市待確認');
      const stockNumber = String(b.stock_number || '');
      const brand = /GOGORO|睿能/i.test(`${name} ${model}`) ? 'GOGORO' : String(b.brand || '其他').trim().toUpperCase();
      const asIs = b.as_is === true || `${name} ${model} ${b.description || ''}`.includes('現況');
      return {
        id: String(b.source_url || i),
        store, brand, model, original_name: name, stock_number: stockNumber,
        year: Number.isInteger(b.year) ? b.year : null,
        price: Number.isFinite(b.price) ? b.price : null,
        image_url: String(b.image_url || ''),
        categories: vehicleCategories(b, brand, model),
        warrantyStatus: asIs ? 'as-is' : b.warranty === true ? 'warranty' : '',
        searchText: [name, model, stockNumber, brandLabels.get(brand) || brand, store].join(' ').toLowerCase()
      };
    });
    updateFilters();render(true);
    $('syncStatus').textContent=`已載入 ${bikes.length} 筆公開商品資料。資料為定期更新，非即時庫存。`;
  } catch(error) {
    $('syncStatus').textContent='目前無法讀取車庫資料，請確認 vehicles.json 已上傳及自動同步流程正常。';
    $('empty').hidden = false;
    $('empty').textContent = '車庫資料尚未準備完成。';
    console.error('RenMotor load error:',error);
  }
}
loadVehicles();
