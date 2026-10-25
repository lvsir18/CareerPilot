(markers) => {
  const visible = el => !!el && !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  const txt = el => visible(el) ? (el.innerText || '').trim() : '';
  const normalize = text => text.replace(/[\s：:【】\[\]]/g, '').toLowerCase();
  const names = new Set(markers.map(normalize));
  const isHeading = el => names.has(normalize(txt(el)));
  const all = [...document.querySelectorAll('div,section,article,main,td,table,p,span,strong,h1,h2,h3,h4,li')];
  // Count sections, not the size of the first matching paragraph. Their common
  // container retains sibling responsibilities, qualifications and benefits.
  const headings = all.filter(el => isHeading(el) &&
    ![...el.children].some(child => isHeading(child)));
  const detailPattern = /\/(?:detail|job-info|job-details)(?:[/?#-]|$)|\/(?:job|position|positions)\/(?!list(?:[/?#]|$))[^/?#]+/i;
  const detailLinks = new Set([...document.querySelectorAll('a[href]')]
    .filter(visible).map(a => a.href).filter(href => detailPattern.test(href)));
  const isList = !detailPattern.test(location.href) && detailLinks.size > 1;
  const candidates = all.filter(el => /^(DIV|SECTION|ARTICLE|MAIN|TD|TABLE)$/.test(el.tagName))
    .map(el => ({ el, text: txt(el), sections: new Set(headings.filter(h => el.contains(h)).map(h => normalize(txt(h)))).size }))
    .filter(c => c.text.length >= 80 && c.sections > 0)
    .sort((a, b) => b.sections - a.sections || a.text.length - b.text.length);
  const chosen = !isList ? candidates[0] : null;
  let description = chosen ? chosen.text : null;
  if (description) {
    // Remove navigation / apply controls if the common container is broad.
    const lines = description.split('\n');
    const start = lines.findIndex(line => names.has(normalize(line)));
    if (start >= 0) description = lines.slice(start).join('\n');
    const stop = description.search(/\n(?:投递|申请|部门意向|立即投递|投递简历|简历投递|申请职位|立即申请|关注我们|Copyright|版权所有|©|法律声明)(?:\s|$)/i);
    if (stop >= 0) description = description.slice(0, stop).trim();
  }
  const firstText = selectors => {
    for (const selector of selectors) {
      for (const el of document.querySelectorAll(selector)) {
        const text = txt(el);
        if (text && text.length <= 300) return text;
      }
    }
    return '';
  };
  const title = firstText([
    '.position-title', '.job-name', '.job-info-container .base-info .header .title',
    '[class*="CampusPositionDetail--name--"]', '[class*="STJobNameLeft"]',
    '[class*="job-detail-title"]', '[class*="job-name"]', '[class*="jobTitle"]',
    '[class*="job-title"]', '[class*="title-"][title]',
    '[class*="page-job-detail"] [class*="job-name"]',
    'h1', 'h2'
  ]);
  // Only job-header metadata may supply a city/type. The body can mention
  // offices unrelated to this role, and the navigation mentions other programs.
  const metadataSelectors = [
    '.position-meta', '.job-desc', '[class*="tagsLine"]', '.job-info-container .base-info .label-list',
    '.job-info-container .base-info', '.location-time',
    '[class*="CampusPositionDetail--basicInfo--"]', '[class*="STJobInfo-"]',
    '[class*="page-job-detail"] [class*="job-info"]',
    '.job-info', '[class*="jobDetail"] [class*="location"]',
    '[class*="job-detail"] [class*="location"]',
    '[class*="affix"] [class*="info-"]', '.job-header', '.basic-info',
  ];
  const metadata = [...new Set(metadataSelectors.flatMap(s => [...document.querySelectorAll(s)].map(txt))
    .filter(t => t && t.length < 1000))].join('\n').slice(0, 3000);
  return {
    title: title || (document.querySelector('meta[property="og:title"]') || {}).content || document.title || '',
    description: description && description.length >= 80 ? description : null,
    metadata, sections: chosen ? [...new Set(headings.filter(h => chosen.el.contains(h)).map(h => txt(h)))] : [],
    siteName: (document.querySelector('meta[property="og:site_name"]') || {}).content || '',
    isList,
  };
}
