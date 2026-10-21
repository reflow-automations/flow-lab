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
- Laat geschikte woordcorrecties na dictatie lokaal leren, met voorstellen en ongedaan maken.

### Tekstvelden in verschillende apps

Flow Lab herkent het actieve tekstveld via Windows-toegankelijkheid, zonder
een lijst met appnamen. Ook editors binnen een groter venster kunnen worden
herkend. Als Windows tijdelijk alleen het buitenste venster doorgeeft, volgt
voor de opname een korte hercontrole binnen hetzelfde actieve venster.

Niet elke app geeft tekst en cursor voldoende door aan Windows. Bij een
onbekend of gewijzigd doel plakt Flow Lab niet automatisch. Het resultaat
blijft beschikbaar in de app om te kopieren of bewust opnieuw te plaatsen.
Wachtwoordvelden en alleen-lezenvelden zijn uitgesloten. Compatibiliteit met
iedere app is niet gegarandeerd; een geslaagde proef bewijst het geteste veld.

## Spellinghints na een correctie

Met automatisch leren ingeschakeld kan een geschikte stabiele woordcorrectie
een klein voorstelkaartje tonen. Kies **Onthouden** of **Niet leren**. Het kaartje
neemt geen toetsenbordfocus over en sluit na ongeveer tien seconden. Niets doen
keurt niets goed: het voorstel blijft beschikbaar bij **Geleerd**. Verder wijzigen,
een ander tekstveld of een nieuwe dictatie maakt het oude kaartje ongeldig.

Een nieuwe klein geschreven term wordt uitsluitend na bevestiging een
**spellinghint**, zonder vaste vervanging van het oorspronkelijk herkende woord.
Het bestaande opmaakmodel krijgt het gewenste woord mee en mag het alleen bij
duidelijke zinscontext toepassen. Bij twijfel hoort het oorspronkelijke woord te
blijven staan. Dit is geen modeltraining en garandeert geen foutloze herkenning.
Bekende namen behouden hun bestaande leerregels; het kaartje vermeldt wanneer
het om een vaste vervanging gaat. Hints en correcties zijn te beheren en ongedaan
te maken in Geleerd en Woordenboek. Niet iedere wijziging is een leerkandidaat.

Deze uitbreiding gebruikt dezelfde opmaakaanvraag, zonder extra AI-aanroep.
Bij lokale opmaak blijven de hints op de pc; bij gekozen cloudopmaak gaan alleen
bevestigde hints met die aanvraag mee. Letterlijke opmaak gebruikt deze hints niet.
De bevestigingskaart en deze hintopslag zijn voor Windows. De telefoonexport
laat deze hints weg zolang Android ze nog niet als hint kan behandelen.

## Standaard lokale spraakruntime op Windows

Als Windows Code Integrity een bestand van NeMo-Speech.cpp blokkeert, schakel dan
geen beveiliging uit en probeer diezelfde DLL niet met een andere loader te laden.
De standaardroute is Parakeet v3 via ONNX ASR en Microsoft ONNX
Runtime. Deze route gebruikt andere modelbestanden en geen NeMo-Speech.exe of ggml.dll.

Voor Windows x64 met de project-Python 3.12:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.asr-onnx.txt
.\.venv\Scripts\python.exe setup_asr_onnx.py --enable
```

De installatie haalt ongeveer 670 MB vastgepinde Parakeet-ONNX-modelgegevens op,
controleert hashes en op Windows de Microsoft-handtekeningen van de drie native
ONNX Runtime-bestanden. Een afwijking verhindert activering. Start Flow Lab daarna
opnieuw via het normale afsluit- en startmenu. De keuze staat uitsluitend in de
lokale, van Git uitgesloten `data/local-asr-runtime.json`.

Nieuwe installaties stellen deze route automatisch in met
`Setup-FlowLab.ps1 -DownloadModels`. Ook zonder expliciet ASR-configuratiebestand
kiest Parakeet ONNX. Een ontbrekend model geeft installatie-uitleg.

Deze uitvoering draait op de CPU en blijft volledig lokaal. Tijdens dicteren
wordt niets gedownload en bestaat geen automatische uitwijk naar cloud of naar de
geblokkeerde runtime. Qwen-opmaak, woordenboek, snippets en sneltoets blijven behouden.
Audio tot vijf minuten wordt in aaneensluitende delen van maximaal 24 seconden
verwerkt, met voorkeur voor rustige knippunten. Elk sample gaat precies eenmaal
naar de herkenner; herkenningskwaliteit rond een knippunt blijft iets om te testen.

Op een enkele ontwikkel-pc kostte een warme fictieve proef van 4,5 seconden circa
0,25 seconde voor herkenning, en circa 0,48 seconde inclusief lokale opmaak.
Een synthetisch vijfminutenbestand kostte circa elf seconden voor herkenning.
Dit zijn geen plaatsingstijden of garanties voor andere pc's. De eerste keer
laden van herkenning en opmaak kan duidelijk langer duren.

## Gebruikt dit Ollama?

Ja. Lokale Qwen-opmaak gebruikt een gecontroleerde Ollama-installatie en een eigen
modelcache (`data/local-runtime.json`). Installeer vooraf de officiële
[Windows-versie van Ollama](https://ollama.com/download/windows). Setup controleert
de uitgevershandtekening en importeert het vastgepinde Qwen-model. De uitvoering
blijft lokaal; een Ollama-cloudaccount is niet nodig. Parakeet draait via ONNX in
het Python-proces. Ontbreekt de Qwen-configuratie, dan volgt installatie-uitleg.

| Taak | Model | Uitvoering |
| --- | --- | --- |
| Lokale spraakherkenning | NVIDIA Parakeet TDT 0.6B v3, ONNX INT8 | Microsoft ONNX Runtime, CPU |
| Lokale tekstopmaak | Qwen3-4B-Instruct-2507, Q4_K_M | Ondertekende Ollama, eigen modelcache |
| Experimentele alternatieve herkenning | Whisper large-v3-turbo, Q5 | Legacy whisper.cpp, CUDA, niet standaard geinstalleerd |
| Optionele cloudopmaak | GPT-4.1 mini | Eigen OpenAI API-account |
| Optionele cloudherkenning | OpenAI-transcriptiemodellen | Eigen OpenAI API-account |

Voor lokale opmaak is Qwen het model en Ollama de uitvoersoftware. Revisies en
hashes staan in [model-lock.json](model-lock.json) en [asr-onnx-lock.json](asr-onnx-lock.json).

### Hulp bij kiezen

Bij de verwerkingskeuze staat een korte uitleg. Klik in de app op **Welke modellen
kies ik?** voor snelheid, kwaliteit, privacy en API-kosten. De optionele browser-
interface toont ook uitleg bij elke herkenner en formatter. De informatie komt
voor beide interfaces uit `web/model-guide.json`.

Standaard is Parakeet + lokale Qwen actief, zonder API-kosten. GPT-4.1 mini is een
bewuste optionele cloudkeuze. De lokale formatter is experimenteel en kan inhoud wijzigen. Whisper is
een lokaal alternatief om met dezelfde opname te vergelijken, geen bewezen
algemene kwaliteitswinnaar.

Een historische synthetische proef van 15 oktober met de eerdere GPU-runtimes gaf na einde audio, inclusief opmaak,
warme medianen van 0,55 s (Parakeet + Qwen, 3 runs), 0,70 s (Whisper + Qwen,
3 runs) en 1,02 s (Parakeet + GPT-4.1 mini, 6 runs). De volledige cloudroutes
met GPT-4.1 mini-opmaak zaten rond 3,74 tot 4,39 s mediaan (3 runs per route).
Dit is geen voorspelling voor een andere pc, langere teksten of jouw stem;
opstarten en model laden vallen buiten die tijden. De eerste start kan veel
langer duren. Live tussentijdse tekst is niet hetzelfde als de snelste eindtekst.

## Benodigdheden

- Windows 10/11 x64. Getest op één Windows-pc, niet op een brede hardwarematrix.
- [CPython 3.12, 64-bit](https://www.python.org/downloads/windows/), inclusief Python Launcher en Tcl/Tk.
- Voor lokale Qwen-opmaak: een actuele officiële Windows-installatie van Ollama.
  Setup controleert de uitgever en importeert het vastgepinde Qwen-model.
- Parakeet-herkenning gebruikt de CPU en vereist geen CUDA. Een geschikte GPU kan
  Qwen versnellen. Andere hardware is nog niet breed praktisch getest.
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

# Parakeet-ONNX en Qwen ophalen en lokaal instellen.
# Installeer vooraf de officiële Windows-versie van Ollama.
.\Setup-FlowLab.ps1 -DownloadModels

# Maak een Flow Lab-icoon op het bureaublad en in het Startmenu.
.\Install-FlowLab.ps1

# Eigen Windows-appvenster en lokale verwerking starten.
.\Start-FlowLab.cmd
```

Setup gebruikt `py -3.12` voor een nieuwe omgeving en daarna de interpreter in
`.venv`. Een bestaande `.venv` wordt hergebruikt; ontbrekende pip wordt met de
standaard Python-bootstrap hersteld. ONNX-pakketten worden ook geïnstalleerd.
Met `-DownloadModels` controleert setup eerst de Ollama-uitgever. Daarna haalt setup
Parakeet-ONNX en het vastgepinde Qwen-GGUF op, controleert hashes/signaturen en
importeert Qwen in een eigen cache. Die import gebruikt een tijdelijk eigen
loopbackproces. De bestaande globale Ollama-service blijft buiten die installatie.
NeMo/llama.cpp-runtimes worden standaard niet gedownload. Een mislukte controle
stopt setup. Tijdens offlinegebruik worden ontbrekende modellen niet opgehaald.

Blokkeert Windows of organisatiebeleid een script/executable, bekijk de concrete
melding. Flow Lab schakelt geen beveiliging of execution policy uit.

Voor alleen cloudherkenning in de browser kun je modeldownloads overslaan.
De desktophelper gebruikt lokale audioherkenning en heeft de lokale herkenner nodig.

### Bestaande installatie bijwerken

Haal de nieuwe broncode op en behoud je eigen `data/`, `.env.local` en modellen.
Sluit Flow Lab eerst volledig via het appmenu en voer opnieuw uit:

```powershell
.\Setup-FlowLab.ps1 -DownloadModels
.\Start-FlowLab.cmd
```

Dit migreert naar ONNX en de gecontroleerde lokale Ollama-route. Een ongewijzigde
modelcache wordt hergebruikt. Woordenboek, snippets, geschiedenis, sneltoetsen en
API-sleutels worden niet door voorbeelddata vervangen. Als Ollama niet automatisch
wordt gevonden, geef de exacte geinstalleerde `ollama.exe` mee met `-OllamaPath`.
Deze versie heeft geen automatische updater: een GitHub-update installeert
zichzelf niet op andere computers.

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

De snelkoppeling start rechtstreeks de Python-windowlauncher. Tijdens opstarten
verschijnt een klein laadvenster. Herhaald klikken deelt dezelfde start; er wordt
geen tweede server gestart. Bestaande processen worden hergebruikt. Opstartstappen
en doorlooptijden staan zonder sleutels in `logs/launcher-last-run.json` en de
afzonderlijke `logs/launcher-*.json`-bestanden. Een vastgelopen start krijgt een
begrensde wachttijd en een zichtbare foutmelding. Voer na een update eenmaal
`Install-FlowLab.ps1` uit om oudere PowerShell-snelkoppelingen bij te werken.

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
achtergrond. De eerste opname kan desondanks op modelinitialisatie wachten.
Een model dat even niet gebruikt is, wordt tijdens het spreken alvast gewekt.
De standaardopmaak gebruikt lokale Ollama. De oudere metingen met llama.cpp en
n-gram speculative decoding beschrijven die eerdere ontwikkelroute, niet de
huidige standaard. Duurt laden langer, dan verschijnt een laadmelding;
de opname blijft ondertussen bewaard voor verwerking.

Een leeg chatveld met hinttekst (zoals "Antwoord...") geeft die hinttekst soms
als inhoud door. Staat na het plakken precies de dictatie in het veld, dan meldt
Flow Lab **Ingevoegd in leeg tekstvak**. Plakken kan geen tekst wissen die niet
geselecteerd was.
Na de plaatsingscontrole verdwijnen meldingen bij een verstuurd plakcommando
na 0,7 seconde, ook als Windows de plaatsing niet volledig kon bevestigen.
De volledige status blijft in de app beschikbaar. Fouten die het plaatsen
verhinderen blijven 15 seconden in het balkje staan en zijn daarna terug te
lezen in de app, ook na herstart. Alleen de nieuwste plaatsingsdiagnose en
tijdsmetingen worden lokaal bewaard in `logs/desktop-last-insertion.json`;
die diagnose bevat geen dictaattekst of klembordinhoud.
Daarnaast bewaart `logs/desktop-insertions.jsonl` een beperkte geschiedenis per
plaatsingspoging, met het opname-ID, de foutfase en de herstelstatus van het
klembord. Zo verdwijnt een mislukking niet achter een latere geslaagde poging.
Het log wordt begrensd op circa 30 dagen, maximaal 5.000 recente regels en een
begrensd leesvenster van 8 MB. Het bevat geen transcriptie- of klembordinhoud.
Een kort bezet klembord wordt vóór de ene plakpoging maximaal 0,5 seconde
opnieuw geopend; er wordt geen tweede plakcommando verstuurd.
Sommige chatvelden melden via Windows extra hinttekst. Flow Lab controleert
daarom apart of de volledige dictatie exact terug te lezen is. Als dat lukt maar
de bestaande tekst rondom de cursor niet klopt met de verwachting, meldt de app
dat de dictatie compleet is en vraagt zij de eventuele bestaande tekst te controleren.
Er wordt dan niet opnieuw geplakt en niet onnodig op dezelfde controle gewacht.

## Een mislukte opname opnieuw verwerken

Onder **Dicteren > Opnames van de afgelopen 24 uur** staan desktopopnames, ook
als de eerste verwerking geslaagd is. Kies een
opname en klik **Opnieuw verwerken**. Er wordt geen nieuwe microfoonopname gestart.
Het oorspronkelijke modelprofiel wordt gebruikt; een oorspronkelijk gekozen
cloudformatter kan dus opnieuw tekst naar diezelfde provider sturen.

Bij een netwerkfout tijdens het spreken blijft Flow Lab lokaal opnemen totdat je
stopt. Bij stoppen wordt een herstelkopie versleuteld met Windows DPAPI opgeslagen
onder `data/recovery/`. Deze is alleen onder hetzelfde Windows-account te lezen.
De audio blijft 24 uur vanaf opname-einde beschikbaar, ook na succes of herstart.
Daarna wordt ze bij actief gebruik (ongeveer elke minuut) of de volgende start
automatisch opgeruimd. Een lopende herstelpoging wordt niet onderbroken.
Er is maximaal 500 MB audio-opslag. Voor een nieuwe opname wordt ruimte voor
de volle vijf minuten gereserveerd; bij volle opslag moet je eerst zelf iets
verwijderen. Opnames binnen de bewaartermijn worden niet overschreven.
Ongecomprimeerde audio is circa 2,9 MB per minuut of 14,4 MB voor vijf minuten,
plus een kleine versleutelingsoverhead. Bij opslagproblemen
blijft een kopie alleen in geheugen en waarschuwt de app om nog niet af te sluiten.

Een herstelde tekst komt in de app en geschiedenis. Kies daarna zelf het gewenste
tekstvak en druk Alt+Shift+Z, of kopieer de tekst. De oude cursorpositie wordt niet
automatisch opnieuw gebruikt. Een herhaalde herstelpoging met hetzelfde opname-ID
haalt bij een verloren antwoord een al bewaard resultaat op en maakt geen dubbele
geschiedenisregel. Kies je na een geslaagd resultaat bewust opnieuw verwerken,
dan wordt de bewaarde audio echt opnieuw verwerkt en verschijnt een nieuw resultaat.
Een expliciet geannuleerde opname wordt niet bewaard. Dit herstelt geen audio die
door een oudere versie al verloren is gegaan. De herstelroute geldt voor de
desktophelper; de optionele browserrecorder heeft deze audiobewaring niet.

## Snippets, woordenboek en geschiedenis

De opmaak van berichten en notities redigeert behoudend: geen samenvatting of
vrijere formulering die vragen, voorwaarden of onzekerheid verandert. Een kleine
contextregel herstelt de bekende verspreking `ik heb gebetaald` naar `ik heb betaald`.
Geciteerde voorbeeldwoorden, spellingbesprekingen en de stijl **letterlijk** vallen
buiten die regel. Dit is geen algemene spellingscontrole en geen garantie dat het
taalmodel iedere verspreking of betekeniswijziging correct herkent.

Engelse woorden en uitdrukkingen in Nederlandse spraak moeten in het Engels
blijven, ook gewone tussenzinnen zoals `let's go`, `no worries` en `makes sense`.
De opmaakinstructie verbiedt ook gedeeltelijke vertaling; hoofdletters en
interpunctie mogen wel worden verzorgd.

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
Gewone correctieregels werken wel in de lokale en hybride route.
Een hint zelf opslaan in de editor maakt er een expliciete correctieregel van.

### Automatisch leren van correcties

Zet onder **Instellingen** de optie **Automatisch leren van mijn woordcorrecties**
aan. Deze optie staat bij een nieuwe installatie standaard uit. Na een nieuwe
desktopdictatie volgt Flow Lab maximaal 60 seconden hetzelfde tekstvak. Verbeter
een woord gewoon op je eigen tempo. Ongeveer 1,5 seconde na de laatste tekstwijziging
wordt de correctie beoordeeld. Bij een ander veld, ander venster of nieuw dictaat
stopt het volgen. Het veld moet via Windows betrouwbaar uitleesbaar zijn.

- Een duidelijke variant van een al bekende naam wordt aan de bestaande regel toegevoegd.
- Een nieuwe naam midden in een zin vraagt dezelfde correctie in twee aparte dictaten.
- Korte, dubbelzinnige of sterk afwijkende varianten blijven een voorstel.
- Onder **Recent geleerd** kun je voorstellen onthouden of negeren en een geleerde
  wijziging gericht ongedaan maken. Het gewone woordenboek blijft bewerkbaar.

Dit leert lokale vervangregels voor volgende dictaten, geen nieuw spraakmodel.
Er zijn geen extra AI-aanroepen of API-kosten. Volledige veldinhoud wordt alleen
tijdelijk in geheugen vergeleken. Alleen het woordpaar, een willekeurig dictaat-ID
en de leerstatus worden lokaal opgeslagen. Open voorstellen en teruggenomen
correcties ouder dan 30 dagen worden bij het ophalen van de lijst opgeruimd;
geleerde regels en bewuste negeerkeuzes blijven behouden. De lijst toont de laatste
100 gevallen.

Snippets, de letterlijke schrijfstijl, herstelde opnames en opnieuw plaatsen via
Alt+Shift+Z doen niet mee. Toevoegingen alleen, grote herschrijvingen, getallen,
herkende code/URL's en geciteerde voorbeelden worden overgeslagen. De filters zijn
bewust terughoudend, maar zijn geen volledige inhoudelijke beoordeling. Niet alle
apps geven wijzigingen goed door. Bij een vastgelopen uitlezing stopt alleen het
leren tot de volgende appstart; dicteren en plaatsen blijven apart werken.

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

Desktopaudio wordt tijdens opname in geheugen gehouden; bij stoppen ontstaat een
versleutelde herstelkopie die 24 uur blijft staan, ook na succesvolle verwerking.
Handmatig verwijderen kan eerder; de audio-opslag is begrensd op 500 MB. Browseraudio
blijft in geheugen. Voltooide tekst en metadata staan
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
Daarna zie je **Sleutel toegevoegd** en zijn het invoerveld en Opslaan uitgeschakeld.
Via **Sleutel wijzigen** kun je bewust de ene actieve sleutel vervangen.
Een alternatief is `OPENROUTER_API_KEY` in de lokale `.env.local`; dat bestand is
dan gewone tekst en blijft uitgesloten van Git. Gebruik geen OpenAI-sleutel.

1. Klik **Modellen ophalen**. Alleen actuele gratis tekstmodellen met
   voldoende context en nultarief worden aangeboden; geen moderatiemodellen.
2. Begin met een van de enkele startpunten. Via **Alle gratis modellen tonen**
   kun je de volledige lijst bekijken. Je huidige model wordt niet automatisch vervangen.
   Kies een vast model en klik **Modelkeuze opslaan**.
3. Controleer de sleutel en je actuele dagquotum met **Sleutel / quotum controleren**.
4. Gebruik **Opgeslagen model testen met voorbeeldtekst**. Dit verstuurt alleen een vaste
   fictieve tekst, opent geen microfoon en maakt geen geschiedenisregel. Een nieuwe
   modelkeuze moet eerst zijn opgeslagen. Deze tijd meet alleen de opmaakproef,
   niet de hele route van spreken tot plaatsen.
5. Kies pas daarna **OpenRouter gebruiken voor dictatie** op dezelfde pagina,
   of **Lokale audio, OpenRouter gratis** bij Instellingen.
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
De startpunten zijn gebaseerd op het type model en de actuele catalogus, niet op
een bewezen ranglijst voor Nederlandse dictaten. Het eerste voorstel is alleen
zichtbaar zolang dat exacte gratis model nog in de catalogus staat.
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
