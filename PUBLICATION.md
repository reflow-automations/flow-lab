# Publicatiebeleid

Deze repository bevat uitsluitend algemeen bruikbare Flow Lab-code en documentatie.
De persoonlijke installatie van een gebruiker is geen publicatiebron voor gegevens.

## Geschikt voor een publieke update

- Algemene functies, bugfixes, toegankelijkheid, prestaties en documentatie.
- Instellingen als instelbare opties met algemene standaardwaarden.
- Verzonnen testvoorbeelden die geen echte gesprekken of klantgegevens reproduceren.
- Gedocumenteerde afhankelijkheden, modelrevisies en licenties.

## Niet publiceren

- API-sleutels, tokens, accounts, privé-e-mailadressen en lokale gebruikerspaden.
- Persoonlijke snippets, woordenboeken, correcties, voorkeuren en transcripties.
- Opnames, screenshots van echte gesprekken, logs, databases, backups of lokale notities.
- Klantspecifieke instructies of persoonlijke afspraken als standaardgedrag voor iedereen.

## Voor iedere update

1. Beoordeel de inhoudelijke geschiktheid: heeft deze wijziging algemene waarde en
   bevat deze geen persoonlijke informatie? Technische checks kunnen dit niet volledig bepalen.
2. Gebruik uitsluitend de bestandslijst in `export_source.py`. Een nieuw bestand
   vraagt een expliciete inhoudelijke review voordat het op die lijst komt.
3. Bekijk de volledige Git-diff, ook tests, documentatie en commitmetadata.
4. Run `py publication_guard.py --staged` en de relevante tests vóór de commit.
5. Run `py publication_guard.py --git-ref HEAD` vóór pushen. De meegeleverde lokale
   hooks voeren deze checks ook uit wanneer `core.hooksPath=.githooks` is ingesteld.
6. Controleer het gepubliceerde commit-ID, de bestandslijst en de CI-uitkomst.

De GitHub-workflow controleert wijzigingen na push/PR. Dat kan een reeds gepusht
geheim niet terughalen. De afzonderlijke schone publicatiemap en de pre-pushcheck
zijn daarom belangrijk. Hooks kunnen technisch omzeild worden; doe dat niet.
Geen automatische upload of synchronisatie van de persoonlijke installatie.

De eigen MIT-code en de apart gedocumenteerde licenties van derden blijven van kracht.
