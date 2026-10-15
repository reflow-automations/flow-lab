"""Shared, offline-readable model explanations for desktop and web UI."""
import json
from pathlib import Path

def load_guide():
    return json.loads((Path(__file__).resolve().parent/'web/model-guide.json').read_text(encoding='utf-8'))

def guide_text(guide):
    lines=['Welke keuze past bij mij?',guide['intro'],'',guide['recommendation'],'',
           'Snelheid in de Flow Lab-proef',guide['caveat'],'']
    for row in guide['measurements']:
        lines.append(f"{row['route']}: {row['median']} (bereik {row['range']}; {row['runs']} runs)")
    for heading,group in [('Spraak herkennen','engines'),('Tekst opmaken','formatters')]:
        lines.extend(['',heading])
        for item in guide[group].values():lines.extend(['',item['title'],item['text']])
    lines.extend(['','Bronnen (modeldoel en relatieve cloudkosten, gecontroleerd 15 oktober 2026)'])
    lines.extend(s['title']+': '+s['url'] for s in guide['sources'])
    return '\n'.join(lines)
