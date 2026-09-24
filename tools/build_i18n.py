#!/usr/bin/env python3
"""Build translated copies of the site from the English source pages.

You only ever edit the English files (index.html, blog/*.html). This script:

  1. finds every translatable text segment in those pages and gives it a stable id
     (i18n/source.json  ->  {id: english text});
  2. applies i18n/<lang>.json ({id: translated text}) to produce <lang>/index.html,
     <lang>/blog/*.html, ...;
  3. adds the nav language picker, canonical + hreflang tags to every page, and
     rewrites sitemap.xml with per-language alternates.

A language is only published once it has a translation for every segment, so a
half-finished file never ships a half-English page.

Usage:
  python3 tools/build_i18n.py               build everything
  python3 tools/build_i18n.py --todo es     write i18n/todo.es.json (segments still missing)
  python3 tools/build_i18n.py --merge       fold i18n/<lang>.*.json chunk files into <lang>.json
"""
import argparse, hashlib, html, json, posixpath, re, shutil, sys
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / 'i18n'
BASE = 'https://yevbas.github.io/PlateAI-Web'

# code -> (native name, og:locale). Order here = order in the picker.
LANGS = {
    'en': ('English', 'en_US'),
    'es': ('Español', 'es_ES'),
    'de': ('Deutsch', 'de_DE'),
    'fr': ('Français', 'fr_FR'),
    'pt': ('Português', 'pt_BR'),
    'it': ('Italiano', 'it_IT'),
    'pl': ('Polski', 'pl_PL'),
    'uk': ('Українська', 'uk_UA'),
}
DEFAULT = 'en'

INLINE = {'a', 'strong', 'em', 'b', 'i', 'span', 'code', 'br', 'sup', 'sub', 'small', 'u', 'mark', 'abbr', 'wbr', 'kbd', 's'}
SKIP = {'script', 'style', 'svg', 'noscript', 'template'}
ATTRS = ('aria-label', 'alt', 'title', 'placeholder')
META_TEXT = {('name', 'description'), ('name', 'twitter:title'), ('name', 'twitter:description'),
             ('property', 'og:title'), ('property', 'og:description')}
URL_ATTRS = ('href', 'src')

PICKER_CSS = """
.lang-picker{position:relative;flex-shrink:0}
.lang-picker summary{list-style:none;cursor:pointer;height:38px;min-width:38px;padding:0 11px;border-radius:999px;border:1px solid var(--line-strong);background:var(--paper);color:var(--ink);display:flex;align-items:center;justify-content:center;gap:6px;font:700 12.5px/1 -apple-system,system-ui,sans-serif;transition:border-color .25s ease,color .25s ease}
.lang-picker summary::-webkit-details-marker{display:none}
.lang-picker summary svg{width:17px;height:17px;flex-shrink:0}
.lang-picker summary:hover,.lang-picker[open] summary{border-color:var(--flame);color:var(--flame)}
.lang-picker ul{position:absolute;right:0;top:46px;margin:0;padding:6px;list-style:none;min-width:168px;max-height:70vh;overflow:auto;background:var(--paper);border:1px solid var(--line-strong);border-radius:14px;box-shadow:0 14px 34px rgba(0,0,0,.16);z-index:60}
.lang-picker li{margin:0}
.lang-picker a{display:block;padding:9px 12px;border-radius:9px;color:var(--ink);font-weight:600;font-size:14px;white-space:nowrap}
.lang-picker a:hover{background:var(--paper-soft)}
.lang-picker a[aria-current="true"]{color:var(--flame)}
@media (max-width:560px){.lang-picker summary{padding:0;width:38px}.lang-picker .lang-code{display:none}}
""".strip()

GLOBE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
         'stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/>'
         '<path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>')

PICKER_JS = ("<script>(function(){var d=document.currentScript.previousElementSibling;if(!d)return;"
             "d.querySelectorAll('a').forEach(function(a){a.addEventListener('click',function(){"
             "try{a.href=a.getAttribute('href').split('#')[0]+location.hash;}catch(e){}});});"
             "d.addEventListener('toggle',function(){var u=d.querySelector('ul');u.style.left='';u.style.right='';"
             "if(d.open&&u.getBoundingClientRect().left<8){u.style.left='0';u.style.right='auto';}});"
             "document.addEventListener('click',function(e){if(d.open&&!d.contains(e.target))d.open=false;});"
             "document.addEventListener('keydown',function(e){if(e.key==='Escape')d.open=false;});})();</script>")


# ---------------------------------------------------------------- source pages
def source_pages():
    return ['index.html'] + sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'blog').glob('*.html'))


def clean_source(text):
    """Strip everything this script generates so it can be re-inserted idempotently."""
    text = re.sub(r'<!-- i18n:head -->.*?<!-- /i18n:head -->\n?', '', text, flags=re.S)
    text = re.sub(r'<!-- i18n:picker -->.*?<!-- /i18n:picker -->\n?\s*', '', text, flags=re.S)
    text = re.sub(r'<link rel="canonical"[^>]*>\n?', '', text)
    text = re.sub(r'<meta property="og:(url|locale|locale:alternate)"[^>]*>\n?', '', text)
    return text


def page_url(page, lang):
    prefix = '' if lang == DEFAULT else f'{lang}/'
    if page == 'index.html':
        return f'{BASE}/{prefix}'
    return f'{BASE}/{prefix}{page}'


def rel_link(from_page, from_lang, to_page, to_lang):
    """Relative URL from one generated page to another (works under any base path)."""
    start = posixpath.dirname(('' if from_lang == DEFAULT else f'{from_lang}/') + from_page) or '.'
    target = ('' if to_lang == DEFAULT else f'{to_lang}/') + ('' if to_page == 'index.html' else to_page)
    is_dir = to_page == 'index.html'
    target = target.rstrip('/') or '.'
    rel = posixpath.relpath(target, start)
    if is_dir:
        rel = rel.rstrip('/') + '/' if rel != '.' else './'
    return rel


def head_block(page, lang, live):
    url = page_url(page, lang)
    out = ['<!-- i18n:head -->', f'<link rel="canonical" href="{url}">', f'<meta property="og:url" content="{url}">',
           f'<meta property="og:locale" content="{LANGS[lang][1]}">']
    if len(live) > 1:
        for other in live:
            if other != lang:
                out.append(f'<meta property="og:locale:alternate" content="{LANGS[other][1]}">')
        for code in live:
            out.append(f'<link rel="alternate" hreflang="{code}" href="{page_url(page, code)}">')
        out.append(f'<link rel="alternate" hreflang="x-default" href="{page_url(page, DEFAULT)}">')
        out.append(f'<style>{PICKER_CSS}</style>')
    out.append('<!-- /i18n:head -->')
    return '\n'.join(out) + '\n'


def picker_block(page, lang, live):
    if len(live) < 2:
        return ''
    items = []
    for code in live:
        cur = ' aria-current="true"' if code == lang else ''
        items.append(f'<li><a href="{rel_link(page, lang, page, code)}" hreflang="{code}" lang="{code}" translate="no"{cur}>{LANGS[code][0]}</a></li>')
    return ('<!-- i18n:picker -->\n'
            f'<details class="lang-picker"><summary aria-label="Language">{GLOBE}<span class="lang-code" translate="no">{lang.upper()}</span></summary>'
            f'<ul>{"".join(items)}</ul></details>{PICKER_JS}\n'
            '<!-- /i18n:picker -->\n')


def with_blocks(clean, page, lang, live):
    if '</head>' not in clean:
        raise SystemExit(f'{page}: no </head>')
    text = clean.replace('</head>', head_block(page, lang, live) + '</head>', 1)
    marker = '<button type="button" class="theme-toggle"'
    pk = picker_block(page, lang, live)
    if pk:
        if marker not in text:
            raise SystemExit(f'{page}: no theme toggle to anchor the language picker')
        text = text.replace(marker, pk + marker, 1)
    return text


# ---------------------------------------------------------------- segments
def norm(s):
    return ' '.join(s.split())


def seg_id(key):
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]


def has_text(s):
    return type(s) is NavigableString and re.search(r'[^\W\d_]', s) is not None


def translatable(key):
    if not re.search(r'[^\W\d_]', re.sub(r'<[^>]+>', '', key)):
        return False
    plain = html.unescape(re.sub(r'<[^>]+>', '', key)).strip()
    if plain in ('PlateAI',) or re.fullmatch(r'\S+@\S+', plain) or plain.startswith(('http://', 'https://')):
        return False
    return True


def collect(soup):
    """Return [(kind, node, attr, key)] for everything translatable, in document order."""
    segs = []

    def add(kind, node, attr, key):
        if translatable(key):
            segs.append((kind, node, attr, key))

    def walk(el):
        if getattr(el, 'attrs', None) is not None:
            if el.get('translate') == 'no':
                return
            for a in ATTRS:
                if a in el.attrs and isinstance(el[a], str):
                    add('attr', el, a, norm(el[a]))
            if el.name == 'meta' and el.get('content') is not None:
                for k, v in META_TEXT:
                    if el.get(k) == v:
                        add('attr', el, 'content', norm(el['content']))
        kids = list(getattr(el, 'children', []))
        elems = [c for c in kids if hasattr(c, 'name') and c.name]
        direct = [c for c in kids if has_text(c)]
        if direct and all(c.name in INLINE and c.name not in SKIP for c in elems) and el.name not in ('[document]',):
            add('inner', el, None, norm(el.decode_contents(formatter='minimal')))
            for c in elems:  # translatable attributes on inline children (e.g. <a title>)
                for a in ATTRS:
                    if a in c.attrs and isinstance(c[a], str):
                        add('attr', c, a, norm(c[a]))
            return
        for c in kids:
            if hasattr(c, 'name') and c.name:
                if c.name in SKIP:
                    continue
                walk(c)
            elif has_text(c):  # mixed content: translate the bare text node on its own
                add('text', c, None, norm(str(c)))

    walk(soup)
    return segs


def tag_signature(s):
    return sorted(re.findall(r'<[^>]+>', s))


def apply(kind, node, attr, tr):
    if kind == 'attr':
        node[attr] = html.unescape(tr)
    elif kind == 'inner':
        node.clear()
        frag = BeautifulSoup(tr, 'html.parser')
        for n in list(frag.contents):
            node.append(n)
    else:
        raw = str(node)
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        node.replace_with(NavigableString(lead + html.unescape(tr) + trail))


# ---------------------------------------------------------------- output helpers
def relativize(soup, page, lang, translated):
    """Language pages live one folder deeper; re-point relative links that leave the translated set."""
    src_dir = posixpath.dirname(page)
    out_dir = posixpath.dirname(f'{lang}/{page}')
    for el in soup.find_all(True):
        for a in URL_ATTRS:
            v = el.get(a)
            if not isinstance(v, str):
                continue
            sp = urlsplit(v)
            if sp.scheme or sp.netloc or not sp.path or v.startswith(('#', '/')):
                continue
            if el.find_parent('details', class_='lang-picker'):
                continue
            target = posixpath.normpath(posixpath.join(src_dir, sp.path))
            if target in translated:
                continue
            new = posixpath.relpath(target, out_dir or '.')
            el[a] = new + (f'?{sp.query}' if sp.query else '') + (f'#{sp.fragment}' if sp.fragment else '')


def fix_jsonld(soup, page, lang, by_key, tr):
    for s in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(s.string)
        except Exception:
            continue
        for field in ('headline', 'description'):
            if field in data:
                key = norm(html.escape(data[field], quote=False))
                sid = seg_id(key)
                if sid in tr:
                    data[field] = html.unescape(tr[sid])
        data['inLanguage'] = lang
        data['mainEntityOfPage'] = page_url(page, lang)
        s.string = json.dumps(data, ensure_ascii=False)


def load_translations(lang):
    tr = {}
    if not I18N.exists():
        return tr
    for f in sorted(I18N.glob(f'{lang}.json')) + sorted(I18N.glob(f'{lang}.*.json')):
        if f.name.startswith('todo.'):
            continue
        tr.update(json.loads(f.read_text(encoding='utf-8')))
    return tr


def merge():
    for lang in LANGS:
        if lang == DEFAULT:
            continue
        chunks = [f for f in sorted(I18N.glob(f'{lang}.*.json')) if not f.name.startswith('todo.')]
        if not chunks:
            continue
        tr = load_translations(lang)
        (I18N / f'{lang}.json').write_text(json.dumps(tr, ensure_ascii=False, indent=0, sort_keys=True) + '\n', encoding='utf-8')
        for f in chunks:
            f.unlink()
        print(f'merged {len(chunks)} chunk(s) into i18n/{lang}.json ({len(tr)} segments)')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--todo', metavar='LANG')
    ap.add_argument('--merge', action='store_true')
    args = ap.parse_args()
    if args.merge:
        return merge()

    pages = source_pages()
    cleaned = {p: clean_source((ROOT / p).read_text(encoding='utf-8')) for p in pages}

    # pass 1: collect segments from the English pages (blocks included so picker text counts)
    source, used_by = {}, {}
    probe_live = list(LANGS)  # any list with >1 entries yields the same segments
    for p in pages:
        soup = BeautifulSoup(with_blocks(cleaned[p], p, DEFAULT, probe_live), 'html.parser')
        for kind, node, attr, key in collect(soup):
            sid = seg_id(key)
            if sid in source and source[sid] != key:
                raise SystemExit(f'id collision: {sid}')
            source[sid] = key
            used_by.setdefault(sid, []).append(p)
    I18N.mkdir(exist_ok=True)
    (I18N / 'source.json').write_text(json.dumps(source, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')

    # which languages are complete?
    live, translations = [DEFAULT], {}
    for lang in LANGS:
        if lang == DEFAULT:
            continue
        tr = load_translations(lang)
        bad = [i for i, v in tr.items() if i in source and tag_signature(v) != tag_signature(source[i])]
        for i in bad:
            print(f'  [{lang}] tag mismatch in {i}: {source[i][:70]!r}')
        missing = [i for i in source if i not in tr or i in bad]
        stale = [i for i in tr if i not in source]
        status = 'LIVE' if not missing else f'{len(missing)} missing'
        print(f'{lang}: {len(tr) - len(stale)}/{len(source)} segments, {status}' + (f', {len(stale)} stale' if stale else ''))
        if args.todo == lang:
            (I18N / f'todo.{lang}.json').write_text(json.dumps({i: source[i] for i in missing}, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
            print(f'  wrote i18n/todo.{lang}.json')
        if not missing:
            live.append(lang)
            translations[lang] = tr
    live.sort(key=list(LANGS).index)
    if args.todo:
        return

    # pass 2: write English (in place, with generated blocks) and every live language
    translated = set(pages)
    for lang in LANGS:
        if lang != DEFAULT and (ROOT / lang).is_dir() and lang not in live:
            shutil.rmtree(ROOT / lang)  # generated folder for a language that is no longer complete
    for p in pages:
        text = with_blocks(cleaned[p], p, DEFAULT, live)
        (ROOT / p).write_text(text, encoding='utf-8')
        for lang in live:
            if lang == DEFAULT:
                continue
            tr = translations[lang]
            soup = BeautifulSoup(with_blocks(cleaned[p], p, lang, live), 'html.parser')
            for kind, node, attr, key in collect(soup):
                apply(kind, node, attr, tr[seg_id(key)])
            soup.html['lang'] = lang
            fix_jsonld(soup, p, lang, source, tr)
            relativize(soup, p, lang, translated)
            out = ROOT / lang / p
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(str(soup), encoding='utf-8')

    write_sitemap(pages, live)
    print(f'built: {", ".join(live)}  ({len(pages)} pages each)')


def write_sitemap(pages, live):
    def lastmod(p):
        m = re.search(r'"datePublished": "(\d{4}-\d{2}-\d{2})"', (ROOT / p).read_text(encoding='utf-8'))
        return m.group(1) if m else None
    dates = {p: lastmod(p) for p in pages}
    dates['index.html'] = max(d for d in dates.values() if d)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for p in sorted(pages, key=lambda x: (x != 'index.html', -int((dates[x] or '0').replace('-', '')))):
        for lang in live:
            lines.append('  <url>')
            lines.append(f'    <loc>{page_url(p, lang)}</loc>')
            if dates[p]:
                lines.append(f'    <lastmod>{dates[p]}</lastmod>')
            if len(live) > 1:
                for code in live:
                    lines.append(f'    <xhtml:link rel="alternate" hreflang="{code}" href="{page_url(p, code)}"/>')
                lines.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{page_url(p, DEFAULT)}"/>')
            lines.append('  </url>')
    for legal in ('privacy.html', 'terms.html'):
        lines.append(f'  <url><loc>{BASE}/{legal}</loc></url>')
    lines.append('</urlset>')
    (ROOT / 'sitemap.xml').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
