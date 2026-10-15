# Cloudopmaak na GPT-4.1 mini

Onderzoek van 15 oktober 2026. Scope: Nederlandse transcriptietekst opmaken,
zonder inhoud te verzinnen. Spraakherkenning blijft lokaal. Dit document wijzigt
geen provider, API-sleutel of actieve instelling.

## Voorkeur

**Eerste vervanger om verder te testen: GPT-6 Luna met reasoning.effort=none.**
Deze keuze heeft lage tarieven, past bij de bestaande OpenAI-koppeling en is in
een kleine echte API-proef op dezelfde Nederlandse opmaakprompt vergeleken met
GPT-4.1 mini. Dit is een onderbouwde eerste kandidaat, geen bewezen winnaar over
alle providers. Volledig lokaal met Parakeet en Qwen blijft de standaard.

**Alternatief voor de laagste prijs en hoge uitvoersnelheid: GPT-OSS 20B op Groq.**
Daarna GPT-OSS 120B of Claude Haiku 5.5 vergelijken als de Nederlandse redactie
van 20B onvoldoende is. Die providers zijn hier nog niet live gebenchmarkt.

## Prijsvergelijking

Standaard on-demand USD per miljoen tokens, zonder cachekorting. Rekenvoorbeeld:
1.000 inputtokens inclusief instructies en 300 outputtokens. Werkelijke tokenisatie
verschilt per model. Extra reasoningtokens, chunking, regionale toeslagen en belasting
zijn niet meegenomen. Voor lange dictaten kan de prompt per tekstdeel terugkomen.

| Provider / model | Input | Output | 1.000 voorbeeldverzoeken | Beoordeling voor deze taak |
| --- | ---: | ---: | ---: | --- |
| OpenAI GPT-4.1 mini, huidige vergelijking | $0,40 | $1,60 | $0,88 | Wordt uitgefaseerd |
| OpenAI GPT-6 Luna | $0,10 | $0,50 | $0,25 | Eerste kandidaat; echte kleine proef gedaan |
| Groq GPT-OSS 20B | $0,075 | $0,30 | $0,165 | Goedkoopste kandidaat in deze shortlist; kwaliteit nog testen |
| Groq GPT-OSS 120B | $0,15 | $0,60 | $0,33 | Interessante tweede Groq-kandidaat |
| Anthropic Claude Haiku 5.5 | $0,10 | $0,50 | $0,25 | Sterke kandidaat op papier; niet live getest |
| Google Gemini 3.1 Flash-Lite | $0,25 | $1,50 | $0,70 | Niet goedkoper dan Luna in dit voorbeeld |
| Google Gemini 3.5 Flash-Lite | $0,30 | $2,50 | $1,05 | Voor eenvoudige opmaak geen duidelijke prijsreden |
| DeepSeek V4.1 Flash, daluren | $0,15 | $0,60 | $0,33 | Prijs interessant, geen eigen latency-/kwaliteitstest |
| DeepSeek V4.1 Flash, piekuren | $0,30 | $1,20 | $0,66 | Tijdafhankelijk tarief |

Bronnen voor de tabel: [OpenAI GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Groq-productiemodellen](https://console.groq.com/docs/models),
[Claude-prijzen](https://platform.claude.com/docs/en/about-claude/pricing),
[Gemini-prijzen](https://ai.google.dev/gemini-api/docs/pricing),
[DeepSeek-prijzen](https://api-docs.deepseek.com/quick_start/pricing/).

## Snelheid en beperkingen

- GPT-6 Luna ondersteunt `none` voor de redeneerinspanning. Voor alleen redactie
  is een extra denkstap niet nodig als de kwaliteit zonder die stap voldoet.
  [Modeldocumentatie](https://developers.openai.com/api/docs/models/gpt-6-luna).
- Groq vermeldt ongeveer 1.000 tokens/s voor GPT-OSS 20B en 500 voor 120B.
  Dat is uitvoerdoorvoer, niet de volledige tijd inclusief netwerk, wachtrij,
  eerste token en reasoning. Begin daar met lage redeneerinspanning en meet
  de totale tijd; 'hidden reasoning' betekent niet dat de berekening wegvalt.
  [Groq-modelcatalogus](https://console.groq.com/docs/models),
  [20B-details](https://console.groq.com/docs/model/openai/gpt-oss-20b).
- Claude Haiku 5.5 is gericht op latencygevoelige taken. Adaptive thinking staat
  standaard aan; de nieuwe tokenizer kan voor dezelfde tekst meer tokens tellen.
  Daarom garandeert hetzelfde tokenbedrag niet dezelfde factuur of wachttijd.
  [Haiku 5.5-documentatie](https://platform.claude.com/docs/en/models/haiku-5-5/overview).
- De gratis Gemini-API is geen equivalent van lokaal: tekst gaat naar Google en
  de prijspagina onderscheidt productverbeteringsgebruik tussen gratis en betaald.
  Voor persoonlijke dictaten niet blind voor de gratis tier kiezen.
  [Gemini-prijzen en gegevensgebruik](https://ai.google.dev/gemini-api/docs/pricing).
- Cerebras is bekeken, maar de gelezen publieke prijspagina leverde geen
  verifieerbare modeltarieven op en positioneert de Developer-tier als evaluatie.
  Daarom geen ongefundeerde rangschikking op prijs.
  [Cerebras-prijzen](https://www.cerebras.ai/pricing).

## Werkelijk uitgevoerde proef

Zes API-aanroepen: drie verzonnen Nederlandse teksten, telkens GPT-4.1 mini en
GPT-6 Luna. Gevallen: gewoon bericht, bedrag/ontkenning/onzekerheid, en opsomming.
De bestaande systeemprompt is gebruikt. Geen persoonlijke transcripties verstuurd.

| Model | Tijden per verzoek | Mediaan | Controle |
| --- | --- | ---: | --- |
| GPT-4.1 mini | 3,161 / 1,055 / 2,655 s | 2,655 s | 3/3 automatische inhoudschecks goed |
| GPT-6 Luna, none | 1,980 / 1,653 / 1,838 s | 1,838 s | 3/3 automatische inhoudschecks goed |

De resultaten zijn ook gelezen: beide hielden de afspraak, ontkenning en bedragen
vast. Luna plaatste de afsluiting los en maakte een duidelijke lijst. Bij het bedrag
voegde Luna een duizendtalscheiding toe (1500 naar 1.500). Er zijn geen reasoningtokens
gerapporteerd in deze Luna-proef. Alle zes requests samen kosten op basis van
ongecachete tarieven minder dan $0,001; dit is een berekening uit tokengebruik,
geen controle van de uiteindelijke factuur.

Drie voorbeelden per model zijn te weinig voor p95, een algemene kwaliteitsclaim
of een winnaar tegen providers zonder eigen meting. De verzoeken waren niet
gerandomiseerd en meten alleen opmaak, geen audioherkenning. Het kortste individuele
verzoek kwam bovendien van GPT-4.1 mini. Geen automatische migratie uitgevoerd.

## Volgende evaluatie vóór een overstap

Gebruik dezelfde 20-30 synthetische gevallen met namen, bedragen, ontkenningen,
Engelse vaktermen, witregels, snippets en 1/3/5-minuut-equivalente teksten.
Controleer eerst betekenisbehoud, daarna totale mediane/p95-latency en werkelijk
tokengebruik inclusief eventuele redeneerstappen. Vergelijk minstens Luna none
en Groq 20B; voeg Haiku of Groq 120B toe als kwaliteitsalternatief.

De huidige GPT-4.1-mini-snapshot wordt volgens OpenAI op 14 januari 2027
uitgezet. Plan de evaluatie vóór die datum. Er is geen automatische migratie
of nieuwe provider ingesteld.
[Uitfaseringsbericht](https://developers.openai.com/api/docs/deprecations).

## Aanvulling: gratis OpenRouter-modellen

Op 15 oktober 2026 ook OpenRouter onderzocht. OpenRouter is een router naar meerdere
providers. Het gratis `openrouter/free` kiest willekeurig een geschikt gratis model;
voor consistente dicteeropmaak kiest Flow Lab daarom een vaste actuele `:free`-variant.
Gratis capaciteit kan wisselen en wachttijden kunnen tijdens drukte oplopen.
[Officiële uitleg](https://openrouter.ai/docs/guides/routing/routers/free-router).

De accountlimieten zijn opvraagbaar via `/api/v1/key`; de app toont de opgegeven
gratis dagruimte. Eén lang dictaat kan meerdere verzoeken gebruiken. Vermenigvuldig
de daglimiet dus niet zonder meer naar een aantal dictaten.
[Quotumdocumentatie](https://openrouter.ai/docs/api/reference/limits).

Er zijn echte pogingen met vaste fictieve tekst gedaan onder het standaardbeleid
zonder gegevensverzameling: Nemotron 3.5 Lightning en LFM2.5 kregen geen geschikte
provider; Gemma 4 26B kreeg een capaciteits-/limietmelding. Een extra diagnostische
aanroep bevestigde een privacybeleidsafwijzing voor LFM2.5. Geen betaalde terugval,
geen versoepeling van privacy om alsnog een benchmark te forceren. Er is dus geen
geldige end-to-end-snelheidsmeting van deze gratis modellen uit deze proef.

Conclusie: nuttig als optionele experimentroute, niet aangetoond als snellere of
betrouwbaardere vervanging van de lokale standaard. Dit is een momentopname en geen
bewijs dat alle gratis modellen te traag zijn. Providerkeuze, accountbeleid en
beschikbaarheid zijn bepalend. Flow Lab biedt een expliciete privacykeuze en een
synthetische testknop om dit later opnieuw te beoordelen.
