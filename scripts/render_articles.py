#!/usr/bin/env python3
"""Render self-contained article readers with embedded figures and references.

Optional --repository-url rewrites project evidence links to a verified public
repository. Without it, the linked local evidence is embedded as an appendix.
"""
from pathlib import Path
import argparse, base64, hashlib, html, json, mimetypes, re
import markdown2

ROOT=Path(__file__).resolve().parents[1]
CSS='''
:root{color-scheme:light}body{margin:0;background:#f3f5f6;color:#203342;font-family:Georgia,"Noto Serif CJK SC","Songti SC",serif;line-height:1.75}
main{max-width:900px;margin:32px auto;padding:44px 54px;background:#fff;border-top:6px solid #166e82;box-shadow:0 3px 24px #2033420b}
.meta{font-family:Arial,"Noto Sans CJK SC",sans-serif;font-size:12px;letter-spacing:.08em;color:#607887;text-transform:uppercase}
h1,h2,h3,summary{font-family:Arial,"Noto Sans CJK SC","Microsoft YaHei",sans-serif;line-height:1.3}h1{font-size:36px;letter-spacing:-.025em;margin:18px 0 28px}h2{font-size:25px;margin:44px 0 16px;padding-top:12px;border-top:1px solid #dfe7eb}h3{font-size:20px}
p,li{font-size:17px}a{color:#12697f;text-decoration-thickness:1px;text-underline-offset:3px}strong{font-weight:700}img{max-width:100%;height:auto;margin:12px 0}table{width:100%;border-collapse:collapse;font-family:Arial,"Noto Sans CJK SC",sans-serif;font-size:13px;line-height:1.55;margin:24px 0}th{text-align:left;background:#edf3f6;color:#203342}td,th{padding:10px 12px;border-bottom:1px solid #dce5ea;vertical-align:top}tr:nth-child(even)td{background:#f8fafb}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,monospace;background:#f4f7f8;padding:18px;max-height:620px;overflow:auto}code{font-size:.9em}details{margin:16px 0;border:1px solid #dce5ea;padding:14px}summary{cursor:pointer;font-size:15px}footer{margin-top:40px;font:13px/1.7 Arial,sans-serif;color:#607887}.table-wrap{overflow-x:auto}
@media(max-width:700px){main{margin:0;padding:26px 20px}h1{font-size:29px}h2{font-size:22px}p,li{font-size:16px}td,th{padding:8px;font-size:12px}}
@media print{body{background:#fff}main{box-shadow:none;margin:0;max-width:none;padding:0}details{break-inside:avoid}h2{break-after:avoid}img{break-inside:avoid}a{color:#203342}}
'''

def render(source, output, repo_url=None):
    refs={};embedded_images=0
    body=markdown2.markdown(source.read_text(),extras=['tables','fenced-code-blocks','strike'])
    def replace(match):
        nonlocal embedded_images
        attr,value=match.group(1),html.unescape(match.group(2))
        if value.startswith(('https://','http://','mailto:','#','data:')):return match.group(0)
        path=(source.parent/value.split('#',1)[0]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('Broken or external project reference: '+value)
        kind=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if attr=='src' or (kind.startswith('image/') and not repo_url):
            embedded_images+=1
            return attr+'="data:'+kind+';base64,'+base64.b64encode(path.read_bytes()).decode()+'"'
        if repo_url:
            return attr+'="'+html.escape(repo_url.rstrip('/')+'/blob/main/'+path.relative_to(ROOT).as_posix(),quote=True)+'"'
        key='evidence-'+hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()[:12]
        refs[key]=path
        return attr+'="#'+key+'"'
    body=re.sub(r'(href|src)="([^"]+)"',replace,body)
    body=body.replace('<table>','<div class="table-wrap"><table>').replace('</table>','</table></div>')
    zh=source.name.endswith('.zh.md')
    appendix=''
    if refs:
        appendix='<section id="evidence"><h2>'+('随文证据' if zh else 'Embedded evidence')+'</h2><p>'+('以下项目文件随本文保存；完整代码与数据重建材料见项目压缩包。' if zh else 'These linked project files are embedded for offline review. The project archive contains the full code and reconstruction materials.')+'</p>'
        for key,path in refs.items():
            appendix+='<details id="'+key+'"><summary>'+html.escape(path.relative_to(ROOT).as_posix())+'</summary><pre>'+html.escape(path.read_text())+'</pre></details>'
        appendix+='</section>'
    title=source.read_text().splitlines()[0].removeprefix('# ')
    document='<!doctype html><html lang="'+('zh-CN' if zh else 'en')+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style></head><body><main><div class="meta">Open Birth Chart Study · R8 · 26 November 2026</div><article id="article">'+body+'</article>'+appendix+'<footer>Open Birth Chart Study · Original project prose and figures: CC BY 4.0. Third-party sources retain their own terms. Structural model analysis; no mortality forecast validation.</footer></main></body></html>'
    output.write_text(document)
    return {'file':output.name,'bytes':output.stat().st_size,'embedded_images':embedded_images,'embedded_evidence_files':len(refs),'external_scripts':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--repository-url');a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    r=[]
    for lang in ['en','zh']:
        r.append(render(ROOT/'articles'/f'substack.{lang}.md',out/f'Open_Birth_Chart_Study_R8_{lang}.html',a.repository_url))
    print(json.dumps(r,ensure_ascii=False))

if __name__=='__main__':main()
