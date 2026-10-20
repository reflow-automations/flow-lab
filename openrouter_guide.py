"""Small, explicit starting shortlist. No requests, auto-selection or speed claims."""

# Suggestions checked against the public OpenRouter catalogue on 20 October 2026.
# Only display a suggestion if that exact free model is still in the live catalogue.
SUGGESTIONS={
    'google/gemma-4-26b-a4b-it:free':('Gemma 4 26B (eerste proef)',
        'Een instructiemodel om als eerste te proberen voor gewone tekstopmaak.'),
    'nvidia/nemotron-3.5-lightning:free':('Nemotron 3.5 Lightning (alternatief)',
        'Een alternatief om met dezelfde voorbeeldtekst te vergelijken.'),
    'google/gemma-4-31b-it:free':('Gemma 4 31B (groter alternatief)',
        'Een groter instructiemodel. Groter betekent niet automatisch beter of sneller voor dictatie.'),
}
LIMITS='Startpunten, geen gemeten ranglijst. Test snelheid en inhoud; gratis beschikbaarheid en je privacyvoorwaarden kunnen per model verschillen.'
SOURCES=('https://openrouter.ai/api/v1/models',
         'https://openrouter.ai/google/gemma-4-26b-a4b-it:free',
         'https://openrouter.ai/docs/guides/features/sovereign-ai')

def model_choices(models,saved='',show_all=False):
    available={m['id']:m for m in models if isinstance(m.get('id'),str) and m['id'].endswith(':free')}
    if show_all:ids=sorted(available,key=lambda key:available[key].get('name',key).casefold())
    else:
        ids=[key for key in SUGGESTIONS if key in available]
        if not ids:
            ids=[key for key in sorted(available) if not any(word in key for word in ('code','coder','coding'))][:3]
        if saved in available and saved not in ids:ids.append(saved)
    result=[]
    for key in ids:
        label,hint=SUGGESTIONS.get(key,(available[key].get('name',key).replace(' (free)',''),
            'Overige keuze. Vergelijk de voorbeeldproef voordat je dit model voor dictatie gebruikt.'))
        if key==saved and key not in SUGGESTIONS:label='Huidige keuze: '+label
        result.append({'id':key,'label':label+' ['+key+']' if show_all else label,'hint':hint+' '+LIMITS})
    return result
