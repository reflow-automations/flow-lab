# Flow Lab

Een experimentele Windows-app voor dicteren, opmaken en invoegen in het actieve
tekstvak. Met lokale spraakherkenning, een compact opnamebalkje, snippets,
een woordenboek en lokale geschiedenis.

Flow Lab opent nu als een eigen Windows-programmavenster. Dicteren, geschiedenis,
woordenboek, snippets en instellingen staan in dezelfde app. De lokale HTTP-server
is een intern verwerkingsonderdeel; voor normaal desktopgebruik is geen browser nodig.

**Status: ontwikkelversie 0.2.0.** De app werkt vanuit een projectmap. Het lokale
installatiescript maakt snelkoppelingen op het bureaublad en in het Startmenu.
Er is nog geen ondertekende alles-in-een-installer of automatische updater.
Flow Lab is een zelfstandige implementatie, bevat geen Wispr Flow-broncode of
merkassets en is niet verbonden aan Wispr Flow.

## Mogelijkheden

- Houd je instelbare sneltoets ingedrukt om te spreken; laat los om te verwerken.
- Druk twee keer snel om de opname vast te zetten; nogmaals drukken stopt.
- Bekijk het echte microfoonniveau in een compacte balk van 156 bij 36 pixels.
- Laat tekst met interpunctie en alinea's in het oorspronkelijke veld plakken.
- Plak het laatste bewaarde resultaat opnieuw met Alt+Shift+Z.
- Beheer eigen woorden, spellingregels en exacte snippets met herkenningsvarianten.
- Zoek en kopieer transcripties uit de afgelopen 30 dagen.

## Gebruikt dit Ollama?

Nee. Flow Lab start zelf lokale modelservers als subprocessen:

| Taak | Model | Uitvoering |
| --- | --- | --- |
| Lokale spraakherkenning | NVIDIA Parakeet TDT 0.6B v3 | NeMo-Speech.cpp, CUDA |
| Lokale tekstopmaak | Qwen3-4B-Instruct-2507, Q4_K_M | llama.cpp, Vulkan |
| Alternatieve lokale herkenning | Whisper large-v3-turbo, Q5 | whisper.cpp, CUDA |
| Optionele cloudopmaak | GPT-4.1 mini | Eigen OpenAI API-account |
| Optionele cloudherkenning | OpenAI-transcriptiemodellen | Eigen OpenAI API-account |

`llama.cpp` is de uitvoersoftware, niet het gebruikte taalmodel. Voor lokale
opmaak is het model Qwen. Ollama hoeft niet geïnstalleerd te worden.
Revisies en hashes staan in [model-lock.json](model-lock.json).

### Hulp bij kiezen

Bij de verwerkingskeuze staat een korte uitleg. Klik in de app op **Welke modellen
kies ik?** voor snelheid, kwaliteit, privacy en API-kosten. De optionele browser-
interface toont ook uitleg bij elke herkenner en formatter. De informatie komt
voor beide interfaces uit `web/model-guide.json`.

Begin met Parakeet + GPT-4.1 mini-opmaak als nette tekst het belangrijkst is.
Kies Parakeet + lokale Qwen als alles op de pc moet blijven en je geen API-kosten
wilt. De lokale formatter is experimenteel en kan inhoud wijzigen. Whisper is
een lokaal alternatief om met dezelfde opname te vergelijken, geen bewezen
algemene kwaliteitswinnaar.

Een kleine synthetische proef op één GPU-pc gaf na einde audio, inclusief opmaak,
warme medianen van 0,55 s (Parakeet + Qwen, 3 runs), 0,70 s (Whisper + Qwen,
3 runs) en 1,02 s (Parakeet + GPT-4.1 mini, 6 runs). De volledige cloudroutes
met GPT-4.1 mini-opmaak zaten rond 3,74 tot 4,39 s mediaan (3 runs per route).
Dit is geen voorspelling voor een andere pc, langere teksten of jouw stem;
opstarten en model laden vallen buiten die tijden. De eerste start kan veel
langer duren. Live tussentijdse tekst is niet hetzelfde als de snelste eindtekst.

## Benodigdheden

- Windows 10/11 x64. Getest op één Windows-pc, niet op een brede hardwarematrix.
- [CPython 3.12, 64-bit](https://www.python.org/downloads/windows/), inclusief Python Launcher en Tcl/Tk.
- Voor de huidige lokale herkenningsroute: NVIDIA-GPU en passende CUDA-driver.
  Qwen gebruikt Vulkan. CPU-only, AMD en Intel voor lokale herkenning zijn niet
  uitgewerkt of geverifieerd in deze configuratie.
- Meerdere gigabytes vrije schijfruimte voor modellen, runtimes en downloadarchieven.
  De benodigde GPU-capaciteit hangt af van de gekozen route.
- Microfoon en voor de browserinterface een actuele Chromium-browser.
- Internet voor installatie/download. Daarna vraagt offlinegebruik geen API-sleutel.
  Cloudopties vragen een eigen sleutel en kunnen geld kosten.

## Installeren vanuit broncode

Pak de broncode uit in een eigen map en open PowerShell in die map:

```powershell
# Python-pakketten in een eigen .venv installeren.
.\Setup-FlowLab.ps1

# Modellen en Windows-runtimes ophalen, dit zijn grote downloads.
.\Setup-FlowLab.ps1 -DownloadModels

# Maak een Flow Lab-icoon op het bureaublad en in het Startmenu.
.\Install-FlowLab.ps1

# Eigen Windows-appvenster en lokale verwerking starten.
.\Start-FlowLab.cmd
```

Setup gebruikt `py -3.12` voor een nieuwe omgeving en daarna de interpreter in
`.venv`. Een bestaande `.venv` wordt hergebruikt. De modeldownloads komen van
GitHub en Hugging Face, worden gecontroleerd met SHA-256 en verschijnen in
`model-manifest.json`. Een mislukte download geeft een foutstatus. Tijdens
offlinegebruik worden ontbrekende modellen niet automatisch online opgehaald.

Blokkeert Windows of organisatiebeleid een script/executable, bekijk de concrete
melding. Flow Lab schakelt geen beveiliging of execution policy uit.

Voor alleen cloudherkenning in de browser kun je modeldownloads overslaan.
De desktophelper gebruikt lokale audioherkenning en heeft de lokale herkenner nodig.

### Optionele cloudfuncties

Kopieer `.env.example` naar `.env.local` en vul lokaal je eigen `OPENAI_API_KEY` in.
Overschrijf geen bestaande configuratie. Deel het bestand en de sleutel niet.
De voorbeeldfile bevat geen sleutel; een leeg bestand activeert de cloud niet.
Voor volledig lokaal gebruik is `.env.local` niet nodig.

### Openen en afsluiten

- Open **Flow Lab** via het bureaublad of Startmenu: dit opent het eigen appvenster.
- Het kruisje verbergt het venster naar het systeemvak; dictatie blijft actief.
- **Flow Lab volledig afsluiten**, in het venster of systeemvak, stopt de helper,
  lokale server en bijbehorende modelprocessen van deze versie.
- Alleen helper en server: `Start-FlowLab-Desktop.cmd`.
- Hele app en bijbehorende modelprocessen stoppen: `Stop-FlowLab.ps1`.
- Optionele ontwikkelinterface: [http://127.0.0.1:17865](http://127.0.0.1:17865).

Een browsertab sluiten stopt de server niet. Er wordt geen Windows-login-autostart
toegevoegd. De launchers en helper verwachten poort 17865, de modelservers 17866-17868.
De server draait zolang Flow Lab actief is, ook als het eigen venster verborgen is.
Hij draait niet meer nadat **Flow Lab volledig afsluiten** succesvol is afgerond.

Na `Install-FlowLab.ps1` kun je dubbelklikken op **Flow Lab** op het bureaublad,
of Windows indrukken, **Flow Lab** typen en Enter drukken. Dit opent de app en
hergebruikt een al draaiende server/helper. De installatie is voor je eigen
Windows-account, zonder administratorrechten. De snelkoppelingen verwijzen naar
deze projectmap: verplaats of verwijder die map niet. Wil je de koppelingen weg,
verwijder dan de twee Flow Lab-snelkoppelingen; je persoonlijke data blijft staan.

## Dicteren en sneltoetsen

1. Klik in het gewenste tekstvak, eventueel met een selectie om te vervangen.
2. Houd **Ctrl+Shift+Spatie** ingedrukt en spreek.
3. Laat los. Flow Lab verwerkt de audio en probeert tekst op dezelfde plek te plaatsen.

Twee korte drukken zetten de opname vast; een slotje toont dat. Een volgende druk
of de rechterknop stopt en verwerkt. Esc of het kruisje annuleert. Een korte eerste
tik van maximaal 250 ms krijgt na loslaten 320 ms om een tweede druk te herkennen.
Een langere hold stopt direct bij loslaten. Maximaal 5 minuten per opname.

**Sneltoets wijzigen:** open het tabblad **Instellingen** in de app, kies je
combinatie en klik **Sneltoets opslaan**. Sneltoetsen pauzeren alleen als het
instellingenvenster zelf op de voorgrond staat. Het systeemvak-
item **Sneltoets instellen...** opent hetzelfde tabblad, geen losse browserpagina.
Ctrl+Windows zonder extra toets wordt ondersteund. Sluit andere dicteerapps zelf
af als die dezelfde combinatie gebruiken. Een geweigerde registratie laat de
vorige instelling actief. F12 is niet beschikbaar.

**Laatste tekst opnieuw plaatsen:** Alt+Shift+Z haalt het nieuwste resultaat uit
de eigen geschiedenis, ook na herstart. Als Windows die combinatie bezet meldt,
probeert de helper Ctrl+Alt+Shift+Z. De actuele combinatie staat in de tooltip van
het systeemvakicoon. Geen nieuwe opname, opmaak of dubbele geschiedenisregel.

Blijf tijdens verwerking in hetzelfde veld. Automatisch plakken wordt tegengehouden
bij gewijzigd venster, cursor/selectie of tekst, wachtwoordvelden, een opmaakwaarschuwing
of ontbrekende cursorinformatie. Kopieer het resultaat dan zelf. Er wordt geen Enter
verstuurd. Het klembord wordt hersteld zolang een andere toepassing het niet heeft
gewijzigd. Niet alle tekstvakken, terminals en verhoogde apps worden ondersteund.

**Plaatsingsstatus en snelheid:** het vak **Kopie van laatste resultaat** toont
altijd een kopie, ook wanneer invoegen niet lukt. De status erboven vermeldt of
plaatsing bevestigd is, met de tijd vanaf stoppen/loslaten tot die bevestiging.
Dit is iets anders dan alleen de rekentijd van herkenning en opmaak. De
desktophelper laadt de gekozen lokale modellen direct bij het starten op de
achtergrond, zodat de eerste opname niet op het laden wacht. Een model dat even
niet gebruikt is, wordt tijdens het spreken alvast gewekt. De lokale opmaak
gebruikt n-gram speculative decoding van llama.cpp: de opgemaakte tekst lijkt
sterk op de invoer, dus het model kan stukken vooruit voorspellen. Met
temperatuur 0 blijft de uitkomst gelijk; in een kleine synthetische proef was
opmaken twee tot drie keer sneller. Duurt laden toch langer, dan verschijnt een
laadmelding; de opname blijft ondertussen in geheugen.

Een leeg chatveld met hinttekst (zoals "Antwoord...") geeft die hinttekst soms
als inhoud door. Staat na het plakken precies de dictatie in het veld, dan meldt
Flow Lab **Ingevoegd in leeg tekstvak**. Plakken kan geen tekst wissen die niet
geselecteerd was.
Foutmeldingen blijven 15 seconden in het balkje staan en zijn daarna terug te
lezen in de app, ook na herstart. Alleen de nieuwste plaatsingsdiagnose en
tijdsmetingen worden lokaal bewaard in `logs/desktop-last-insertion.json`;
die diagnose bevat geen dictaattekst of klembordinhoud.
Sommige chatvelden melden via Windows extra hinttekst. Flow Lab controleert
daarom apart of de volledige dictatie exact terug te lezen is. Als dat lukt maar
de bestaande tekst rondom de cursor niet klopt met de verwachting, meldt de app
dat de dictatie compleet is en vraagt zij de eventuele bestaande tekst te controleren.
Er wordt dan niet opnieuw geplakt en niet onnodig op dezelfde controle gewacht.

## Snippets, woordenboek en geschiedenis

Gebruik de gelijknamige tabbladen in de eigen app. Daar kun je zoeken, selecteren,
toevoegen, wijzigen, uitschakelen en kopiëren. Instellingen bevat daarnaast lokale
of cloudopmaak, alinea-indeling en schrijfstijl. Het systeemvakmenu opent deze
tabbladen in hetzelfde appvenster. De volgende browserlinks zijn alleen een
optionele alternatieve ontwikkelinterface:

- [Snippets](http://127.0.0.1:17865/#snippets): naam, herkenningsvarianten (één per
  regel) en de volledige vaste tekst. Klik een item om het aan te passen.
- [Woordenboek](http://127.0.0.1:17865/#dictionary): juiste spelling en varianten die
  gecorrigeerd moeten worden. Spellinghints verschillen van expliciete vervangregels.
- [Geschiedenis](http://127.0.0.1:17865/#history): zoeken, teruglezen en kopiëren.

Een nieuw broncodepakket bevat geen persoonlijke snippets of transcripties. De
beginwoordenlijst bevat enkele generieke technische voorbeelden. Snippettekst
wordt letterlijk hersteld, inclusief witregels, en niet als opdracht uitgevoerd.
Inline snippetinhoud wordt afgeschermd voor het opmaakmodel.

**Woordenboeklabels:** Actief is de aan/uit-status. Een expliciete correctieregel
vervangt een opgegeven herkenningsvariant door de gewenste spelling. Een geïmporteerde
Spellinghint is een woord zonder vaste vervangregel. Die hints worden momenteel alleen
meegegeven aan cloud-spraakherkenning, binnen de limiet van de hints-lijst. Ze worden
niet gebruikt door lokale Parakeet/Whisper, ook niet bij lokale audio met cloudopmaak.
Gewone correctieregels werken wel in de lokale en hybride route. Flow Lab leert nog
niet automatisch van tekst die je na het plakken in andere programma's corrigeert.
Een hint zelf opslaan in de editor maakt er een expliciete correctieregel van.

### Optionele import uit je eigen Wispr-installatie

Alleen als je daar zelf voor kiest, vanuit de projectmap:

```powershell
# Eerst controleren, zonder Flow Lab-items te wijzigen.
& .\.venv\Scripts\python.exe .\check_wispr_library.py
# Ontbrekende items/varianten toevoegen, conflicten niet overschrijven.
& .\.venv\Scripts\python.exe .\check_wispr_library.py --apply
```

De bron is `%APPDATA%/Wispr Flow/flow.sqlite`, uitsluitend actieve Dictionary-regels.
De bron wordt read-only geopend. Wispr-history, accounts en tokens worden niet
geïmporteerd. Het rapport staat in `data/wispr-library-audit.json`. Bij toevoegen
wordt eerst een library-only backup gemaakt. Dit is geen officiële Wispr-API;
het lokale schema kan wijzigen.

## Privacy en keuzes

| Keuze | Wat verlaat deze pc? |
| --- | --- |
| Parakeet/Whisper + lokale Qwen | Geen audio of transcriptietekst voor modelverwerking |
| Lokale herkenning + cloudopmaak | Herkende tekst naar OpenAI, audio blijft lokaal |
| Cloudherkenning | Audio naar OpenAI; opmaak hangt af van de formatter |

Desktop start standaard lokaal. Browservoorkeuren staan apart en kunnen hybride/cloud
selecteren: controleer de keuzelijsten. Geen automatische cloudterugval bij offlinekeuze.

Microfoonaudio blijft standaard in geheugen. Voltooide tekst en metadata staan
maximaal 30 dagen in `data/flow-lab.sqlite`. Opruimen gebeurt bij opstarten,
lezen/opslaan en periodiek tijdens gebruik. De database is niet door Flow Lab
versleuteld; je Windows-account en schijfbeveiliging bepalen de lokale toegang.
Snippets en woordenboek blijven staan totdat je ze wijzigt/verwijdert.

De HTTP-server bindt aan 127.0.0.1. Zet deze proef niet publiek achter een proxy:
dit is geen geauthenticeerde multi-userdienst. API-sleutels blijven server-side.

## Ontwikkelen en testen

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
# Optioneel met Node.js: audio-worklet-buffercontrole.
node .\test_recorder.cjs
```

Tests gebruiken tijdelijke data en mocks, geen microfoon. Windows-invoegen en
sneltoetsen vragen daarnaast een fysieke praktijktest. De interne `--self-test`
vraagt een aparte synthetische fixture die niet in dit pakket zit; dit is geen
normale installatie- of gebruiksstap.

Belangrijke bestanden: `app.py` (API), `engines.py` (modellen), `desktop_helper.py`
(desktop), `native_app.py` (eigen appvenster en instellingen), `desktop_windows.py` (Windows), `dictation_gesture.py` (bediening),
`compact_overlay.py` (balk), `personalization.py` (opmaak/snippets), `storage.py`
(gegevens), `web/` (beheer).

Bekende grenzen: lokale opmaak kan woorden wijzigen; controleer belangrijke tekst.
Niet elk tekstvak ondersteunt cursorcontrole. Geen brede hardwaretest, ondertekende
installer, AI-commandfunctie, teamomgeving of Ollama-integratie. Snelheidsmetingen
op één pc zijn geen prestatiegarantie.

## OpenRouter en gratis modellen (optioneel)

Ga in de app naar **Instellingen > OpenRouter instellen**, of naar het tabblad
**OpenRouter**. Plak je eigen OpenRouter-sleutel in het gemaskeerde veld en kies
**Sleutel veilig opslaan**. De app bewaart die met Windows DPAPI versleuteld voor
je Windows-account in de uitgesloten map `data/`. De sleutel wordt niet teruggetoond.
Een alternatief is `OPENROUTER_API_KEY` in de lokale `.env.local`; dat bestand is
dan gewone tekst en blijft uitgesloten van Git. Gebruik geen OpenAI-sleutel.

1. Klik **Gratis modellen ophalen**. Alleen actuele gratis tekstmodellen met
   voldoende context en nultarief worden aangeboden; geen moderatiemodellen.
2. Kies een vast model en klik **Modelkeuze opslaan**.
3. Controleer de sleutel en je actuele dagquotum met **Sleutel / quotum controleren**.
4. Gebruik **Snelheid testen met voorbeeldtekst**. Dit verstuurt alleen een vaste
   fictieve tekst, opent geen microfoon en maakt geen geschiedenisregel.
5. Kies pas daarna **Lokale audio, OpenRouter gratis** als verwerkingsoptie.
   Alleen instellen of testen schakelt de standaard niet om; die blijft lokaal.

Gratis betekent niet lokaal: de herkende tekst gaat via OpenRouter naar de gekozen
provider. Flow Lab vraagt standaard providers zonder gegevensverzameling. Dit kan
gratis modellen onbeschikbaar maken. Je kunt deze voorkeur zelf uitzetten en opslaan;
dan kunnen providers tekst bewaren of voor training gebruiken volgens hun voorwaarden.
Je accountbeleid bij OpenRouter blijft ook gelden en wordt door Flow Lab niet gewijzigd.

Er is geen willekeurige gratis router en geen automatische betaalde terugval. De app
controleert `:free`, nultarieven en stuurt een prijsplafond van nul voor input, output
en verzoekkosten. Er worden geen betaalde tools/plugins ingeschakeld. Bij een fout,
quotum of timeout blijft tijdens dicteren de herkende tekst behouden met een melding.
Eén lang dictaat kan door tekstsegmenten meerdere gratis verzoeken kosten.

Gratis capaciteit kan druk zijn. Een catalogusvermelding garandeert geen beschikbare
provider, snelheid of goede Nederlandse opmaak. Vergelijk met dezelfde voorbeeldtekst
en houd volledig lokaal als betrouwbare uitwijkkeuze op je eigen pc.
Bronnen: [gratis router en beperkingen](https://openrouter.ai/docs/guides/routing/routers/free-router),
[limieten en actuele quotumcontrole](https://openrouter.ai/docs/api/reference/limits),
[provider- en privacyfilters](https://openrouter.ai/docs/guides/routing/provider-selection).

## Open source en delen

Publieke updates bevatten uitsluitend algemeen bruikbare code en verzonnen
testvoorbeelden. Persoonlijke gegevens, voorkeuren en bibliotheken blijven lokaal.
Zie [PUBLICATION.md](PUBLICATION.md) voor de verplichte inhoudelijke controle en
de Git-checks. Installeer lokale commit/pushchecks in een broncodecheckout met
`git config core.hooksPath .githooks`.

De eigen code valt onder de [MIT-licentie](LICENSE). Afhankelijkheden en modellen
behouden hun eigen voorwaarden: [THIRD_PARTY.md](THIRD_PARTY.md). Met name pystray
is LGPLv3 en Parakeet CC-BY-4.0; de MIT-licentie vervangt die niet.

```powershell
& .\.venv\Scripts\python.exe .\export_source.py
```

Deze export gebruikt een expliciete bestandslijst. Sleutels, database, persoonlijke
instellingen, sessieafbeeldingen, audio, modellen, native binaries, logs en lokale
onderzoeksnotities gaan niet mee. Deel niet zomaar een ZIP van de hele werkmap.
Het exportscript publiceert of uploadt niets.

## Vijf minuten en lokale standaard

De desktop en nieuwe browservoorkeuren starten volledig lokaal. Een bestaande browserkeuze blijft bewaard. De opnamelimiet is 300 seconden, begrensd op echte audiosamples zodat ook het laatste blok wordt behouden. Vijf minuten PCM-audio vraagt circa 14,4 MB buffer. De herkenning gebeurt momenteel aan het einde, dus langere dictaten kunnen meer wachttijd geven.

Lange tekst wordt op zinsgrenzen in kleinere opmaakverzoeken verdeeld. Daardoor passen ook langere dictaten binnen de lokale modelcontext. Bij mislukte opmaak of te sterke verkorting blijft de herkende tekst beschikbaar met een waarschuwing. Dit is een extra controle, geen garantie op perfecte herkenning of betekenisbehoud. WAV-upload ondersteunt maximaal 128 MB en vijf minuten; tekstinvoer maximaal 24.000 tekens.

Het onderzoek naar een cloudvervanger, inclusief een kleine echte vergelijking van GPT-6 Luna en GPT-4.1 mini, staat in [MODEL-RESEARCH.md](MODEL-RESEARCH.md). Lokaal blijft standaard; er is geen nieuwe provider automatisch geactiveerd.
